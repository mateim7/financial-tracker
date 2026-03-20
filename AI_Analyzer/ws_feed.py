"""
WebSocket News Feed for the NYSE Impact Screener.
"""

import os
import asyncio
import json
import time
import hashlib
import re


WS_NEWS_PROVIDERS = {
    "finnhub": {
        "name":        "Finnhub",
        "tier":        2,
        "url":         "wss://ws.finnhub.io?token={api_key}",
        "env_key":     "FINNHUB_API_KEY",
        "subscribe":   lambda ws: ws.send(json.dumps({"type": "subscribe-news"})),
        "doc":         "https://finnhub.io/docs/api/news-sentiment",
    },
    "benzinga": {
        "name":        "Benzinga Pro",
        "tier":        1,
        "url":         "wss://api.benzinga.com/api/v1/news/stream?token={api_key}",
        "env_key":     "BENZINGA_API_KEY",
        "subscribe":   None,
        "doc":         "https://docs.benzinga.io/benzinga/newsfeed-stream",
    },
    "polygon": {
        "name":        "Polygon.io",
        "tier":        2,
        "url":         "wss://delayed.polygon.io/news",
        "env_key":     "POLYGON_API_KEY",
        "subscribe":   lambda ws: ws.send(json.dumps({"action": "auth", "params": os.getenv("POLYGON_API_KEY", "")})),
        "doc":         "https://polygon.io/docs/stocks/ws_getting-started",
    },
}


class WebSocketNewsFeed:
    """
    Real-time news ingestion via WebSocket connections to financial data providers.
    Runs as a persistent background task, pushing items into an async queue
    that the main loop consumes alongside RSS.

    Supports: Finnhub, Benzinga Pro, Polygon.io (add more in WS_NEWS_PROVIDERS).
    """

    def __init__(self, providers: list[str] | None = None):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._seen_hashes: set = set()
        self._recent_articles: list = []
        self._tasks: dict[str, asyncio.Task] = {}
        self._connected: dict[str, bool] = {}
        self._stats: dict[str, dict] = {}  # per-provider stats

        # Auto-detect which providers have API keys configured
        if providers is None:
            providers = [
                name for name, cfg in WS_NEWS_PROVIDERS.items()
                if os.getenv(cfg["env_key"])
            ]
        self._providers = providers

    @staticmethod
    def _headline_hash(headline: str) -> str:
        normalized = re.sub(r'[^a-z0-9]', '', headline.lower())
        return hashlib.md5(normalized.encode()).hexdigest()

    # ── Per-provider message parsers ──────────────────────────────────────────

    def _parse_finnhub(self, raw: dict) -> dict | None:
        """Parse Finnhub news WebSocket message."""
        if raw.get("type") != "news":
            return None
        for item in raw.get("data", []):
            headline = item.get("headline", "").strip()
            if not headline:
                continue
            return {
                "source":      "Finnhub",
                "source_tier": 2,
                "headline":    headline,
                "body":        item.get("summary", ""),
                "link":        item.get("url", ""),
                "tickers":     item.get("related", "").split(",") if item.get("related") else [],
                "ws_source":   True,
            }
        return None

    def _parse_benzinga(self, raw: dict) -> dict | None:
        """Parse Benzinga Pro news stream message."""
        if raw.get("action") == "heartbeat":
            return None
        content = raw.get("data", raw)
        headline = content.get("title", content.get("headline", "")).strip()
        if not headline:
            return None
        tickers = []
        for sec in content.get("securities", content.get("stocks", [])):
            t = sec.get("symbol") if isinstance(sec, dict) else sec
            if t:
                tickers.append(str(t).upper())
        return {
            "source":      "Benzinga Pro",
            "source_tier": 1,
            "headline":    headline,
            "body":        content.get("body", content.get("teaser", ""))[:600],
            "link":        content.get("url", ""),
            "tickers":     tickers,
            "ws_source":   True,
        }

    def _parse_polygon(self, raw: dict) -> dict | None:
        """Parse Polygon.io news stream message."""
        if raw.get("ev") != "N" and raw.get("status") != "news":
            return None
        results = raw.get("results", [raw]) if "results" in raw else [raw]
        for item in results:
            headline = item.get("title", "").strip()
            if not headline:
                continue
            tickers = item.get("tickers", [])
            return {
                "source":      "Polygon.io",
                "source_tier": 2,
                "headline":    headline,
                "body":        item.get("description", "")[:600],
                "link":        item.get("article_url", item.get("url", "")),
                "tickers":     tickers if isinstance(tickers, list) else [],
                "ws_source":   True,
            }
        return None

    def _parse_generic(self, raw: dict) -> dict | None:
        """Fallback parser for custom/unknown providers."""
        headline = (raw.get("headline") or raw.get("title") or raw.get("subject") or "").strip()
        if not headline:
            return None
        return {
            "source":      raw.get("source", "WebSocket"),
            "source_tier": int(raw.get("tier", 2)),
            "headline":    headline,
            "body":        (raw.get("body") or raw.get("summary") or raw.get("description") or "")[:600],
            "link":        raw.get("url") or raw.get("link") or "",
            "tickers":     raw.get("tickers", []),
            "ws_source":   True,
        }

    _PARSERS = {
        "finnhub":  "_parse_finnhub",
        "benzinga": "_parse_benzinga",
        "polygon":  "_parse_polygon",
    }

    # ── Connection loop per provider ──────────────────────────────────────────

    async def _connect_provider(self, provider_name: str):
        """Maintain a persistent WebSocket connection to a single provider with auto-reconnect."""
        import websockets.client

        cfg = WS_NEWS_PROVIDERS[provider_name]
        api_key = os.getenv(cfg["env_key"], "")
        url = cfg["url"].format(api_key=api_key)
        parser_method = getattr(self, self._PARSERS.get(provider_name, "_parse_generic"))
        backoff = 1  # seconds, exponential backoff on failure

        self._stats[provider_name] = {"connected": False, "messages": 0, "errors": 0, "last_error": None}

        while True:
            try:
                print(f"  [WS-News] Connecting to {cfg['name']}...")
                async with websockets.client.connect(
                    url,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=2**20,  # 1 MB max message
                ) as ws:
                    self._connected[provider_name] = True
                    self._stats[provider_name]["connected"] = True
                    backoff = 1  # reset on successful connect
                    print(f"  [WS-News] ✓ Connected to {cfg['name']}")

                    # Send subscription message if required
                    if cfg.get("subscribe"):
                        await cfg["subscribe"](ws)
                        print(f"  [WS-News] Subscribed to {cfg['name']} news stream")

                    async for message in ws:
                        try:
                            raw = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        parsed = parser_method(raw)
                        if parsed is None:
                            continue

                        # Dedup by headline hash
                        h = self._headline_hash(parsed["headline"])
                        if h in self._seen_hashes:
                            continue
                        self._seen_hashes.add(h)

                        self._stats[provider_name]["messages"] += 1

                        # Non-blocking put; drop if queue full (backpressure)
                        try:
                            self._queue.put_nowait(parsed)
                        except asyncio.QueueFull:
                            pass  # drop oldest-unprocessed to avoid memory bloat

            except asyncio.CancelledError:
                print(f"  [WS-News] {cfg['name']} connection cancelled")
                break
            except Exception as e:
                self._connected[provider_name] = False
                self._stats[provider_name]["connected"] = False
                self._stats[provider_name]["errors"] += 1
                self._stats[provider_name]["last_error"] = str(e)
                print(f"  [WS-News] {cfg['name']} disconnected: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)  # cap at 60s

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Launch background connection tasks for all configured providers. Call once from main()."""
        for name in self._providers:
            if name in WS_NEWS_PROVIDERS:
                task = asyncio.create_task(self._connect_provider(name))
                self._tasks[name] = task
                print(f"  [WS-News] Launched background listener for {name}")
            else:
                print(f"  [WS-News] Unknown provider '{name}', skipping")

        if not self._tasks:
            print("  [WS-News] No providers configured — set FINNHUB_API_KEY, BENZINGA_API_KEY, or POLYGON_API_KEY")

    async def drain(self) -> list[dict]:
        """
        Drain all queued news items. Called each cycle alongside RSS fetch.
        Returns items in the same format as RSSFeed.fetch().
        """
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        self._recent_articles.extend(items)
        self._recent_articles = self._recent_articles[-600:]
        return items

    def stop(self):
        """Cancel all provider connections."""
        for name, task in self._tasks.items():
            task.cancel()
            print(f"  [WS-News] Stopped {name}")
        self._tasks.clear()

    @property
    def active_providers(self) -> list[str]:
        return [name for name, connected in self._connected.items() if connected]

    @property
    def stats(self) -> dict:
        return dict(self._stats)
