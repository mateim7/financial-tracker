"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     NYSE IMPACT NEWS SCREENER v2.0 — Advanced Multi-Sector Engine          ║
║                                                                             ║
║  Expanded coverage: 300+ tickers across 20 sectors                         ║
║  Features: Supply chain contagion, cross-sector propagation, volatility    ║
║            regime detection, earnings surprise calibration, macro regime    ║
║            awareness, multi-entity resolution, indirect exposure mapping   ║
║                                                                             ║
║  Demonstrates: Ingestion → NLP Scoring → Entity Extraction → Alerting     ║
║  Author: Senior Financial Software Architect & Quantitative AI Specialist  ║
║  NOTE: Uses simulated feed. Swap DummyFeed for Benzinga/Reuters WS        ║
║        in production.                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import uuid
import time
import re
import math
import random
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import websockets
import websockets.server
import sqlite3
import csv
import io
from aiohttp import web as aiohttp_web
from supabase_db import SupabaseDatabase
from backend.algorithm.NYSEImpactScreener import NYSEImpactScreener


# Global set of connected WebSocket clients
WS_CLIENTS: set = set()

async def ws_handler(websocket):
    """Register a client, send initial state, then listen for track/untrack commands."""
    WS_CLIENTS.add(websocket)
    try:
        # Send current market state immediately on connect
        if _LIVE_MARKET_STATE is not None:
            await websocket.send(json.dumps({"type": "market_state", **_LIVE_MARKET_STATE.state}))
        # Send current signal performance stats + tracked IDs
        if _SIGNAL_TRACKER_DB is not None:
            stats = _SIGNAL_TRACKER_DB.get_signal_stats()
            recent = _SIGNAL_TRACKER_DB.get_recent_outcomes(20)
            tracked = _SIGNAL_TRACKER_DB.get_tracked_ids()
            await websocket.send(json.dumps({
                "type": "signal_performance", "stats": stats, "recent": recent,
                "tracked_ids": tracked,
            }))
        # Listen for incoming commands from the dashboard
        async for message in websocket:
            try:
                msg = json.loads(message)
                if msg.get("action") == "track_signal" and _SIGNAL_TRACKER is not None:
                    await _SIGNAL_TRACKER.handle_track_request(msg)
                elif msg.get("action") == "untrack_signal" and _SIGNAL_TRACKER_DB is not None:
                    _SIGNAL_TRACKER_DB.remove_signal(msg.get("event_id"), msg.get("ticker"))
                    await _broadcast_signal_performance()
            except json.JSONDecodeError:
                pass
    finally:
        WS_CLIENTS.discard(websocket)


async def _ws_broadcast(payload: str):
    """Send payload to all connected WS clients in parallel using asyncio.gather.
    Removes disconnected clients automatically."""
    global WS_CLIENTS
    if not WS_CLIENTS:
        return
    async def _safe_send(ws):
        try:
            await ws.send(payload)
            return True
        except (websockets.ConnectionClosed, RuntimeError):
            return False
    results = await asyncio.gather(*(
        _safe_send(ws) for ws in WS_CLIENTS
    ), return_exceptions=True)
    # Remove failed clients
    alive = set()
    for ws, ok in zip(WS_CLIENTS, results):
        if ok is True:
            alive.add(ws)
    WS_CLIENTS = alive


async def _broadcast_signal_performance():
    """Helper to push updated signal stats to all clients."""
    if not WS_CLIENTS or _SIGNAL_TRACKER_DB is None:
        return
    stats = _SIGNAL_TRACKER_DB.get_signal_stats()
    recent = _SIGNAL_TRACKER_DB.get_recent_outcomes(20)
    tracked = _SIGNAL_TRACKER_DB.get_tracked_ids()
    payload = json.dumps({
        "type": "signal_performance", "stats": stats, "recent": recent,
        "tracked_ids": tracked,
    })
    await _ws_broadcast(payload)

# Global references set in main() so WS handler can send state on connect
_LIVE_MARKET_STATE: "LiveMarketState | None" = None
_SIGNAL_TRACKER_DB: "EventDatabase | None" = None
_SIGNAL_TRACKER: "SignalOutcomeTracker | None" = None


async def broadcast_market_state():
    """Push current market state (VIX, regime, SPY, etc.) to all WS clients."""
    if not WS_CLIENTS or _LIVE_MARKET_STATE is None:
        return
    payload = json.dumps({"type": "market_state", **_LIVE_MARKET_STATE.state})
    await _ws_broadcast(payload)


async def broadcast_event(event):
    """Serialize a ScoredEvent and push it to all connected WebSocket clients."""
    if not WS_CLIENTS:
        return
    payload = {
        "type":      "event",
        "id":        event.event_id,
        "ts":        event.timestamp * 1000,
        "headline":  event.headline,
        "source":    event.source,
        "tier":      event.source_tier,
        "type":      event.event_type.value,
        "direction": event.direction.value,
        "sentiment": event.sentiment,
        "score":     event.impact_score,
        "tickers":   event.affected_tickers,
        "sectors":   event.affected_sectors,
        "etfs":      event.affected_etfs,
        "latency":            event.latency_ms,
        "brief":              event.brief,
        "buy_signal":         event.buy_signal,
        "buy_confidence":     event.buy_confidence,
        "reasoning":          event.reasoning,
        "risk":               event.risk,
        "time_horizon":       event.time_horizon,
        "correlated_moves":   event.correlated_moves,
        "ticker_signals":     event.ticker_signals,
        "url":                event.url,
        "stock_availability": event.stock_availability,
        "price_data":         event.price_data,
        "momentum_context":   event.momentum_context,
        "insider_activity":   event.insider_activity,
        "insider_context":    event.insider_context,
        "ws_source":          event.ws_source,
    }
    await _ws_broadcast(json.dumps(payload))


async def http_handler(request):
    """Serves CSV or JSON download of all stored events."""
    fmt = request.match_info.get("fmt", "csv")
    db = request.app["db"]
    if fmt == "json":
        return aiohttp_web.Response(
            text=db.get_json(),
            content_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=nyse_events.json",
                "Access-Control-Allow-Origin": "*",
            },
        )
    return aiohttp_web.Response(
        text=db.get_csv(),
        content_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=nyse_events.csv",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def signals_handler(request):
    """Serves signal performance stats and recent outcomes as JSON."""
    db = request.app["db"]
    stats = db.get_signal_stats()
    recent = db.get_recent_outcomes(30)
    tracked = db.get_tracked_ids()
    return aiohttp_web.Response(
        text=json.dumps({"stats": stats, "recent": recent, "tracked_ids": tracked}, indent=2),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def events_handler(request):
    """Serves recent events from the DB for page reload / initial load."""
    db = request.app["db"]
    limit = int(request.query.get("limit", 100))
    max_age = int(request.query.get("max_age", 3600))  # default 1 hour
    events = db.get_recent_events(min(limit, 500), max_age_seconds=min(max_age, 86400))
    return aiohttp_web.Response(
        text=json.dumps(events),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )

async def start_http_server(db: "EventDatabase"):
    from backtesting_api import setup_backtesting_routes

    app = aiohttp_web.Application()
    app["db"] = db
    app.router.add_get("/download/{fmt}", http_handler)
    app.router.add_get("/download", http_handler)
    app.router.add_get("/api/signals", signals_handler)
    app.router.add_get("/api/events", events_handler)
    setup_backtesting_routes(app)
    runner = aiohttp_web.AppRunner(app)
    await runner.setup()
    await aiohttp_web.TCPSite(runner, "0.0.0.0", 8766).start()
    print("  HTTP server on http://localhost:8766/download")
    print("  Backtesting API on http://localhost:8766/api/backtesting/")


# ═══════════════════════════════════════════════════════════════════════════════
# RSS FEED SOURCE
# ═══════════════════════════════════════════════════════════════════════════════

RSS_SOURCES = [
    # ── Tier 1: Wire Services & Institutional (fastest, most reliable) ──────
    {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",     "name": "MarketWatch DJ",    "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",                "name": "WSJ Business",      "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                  "name": "WSJ Markets",       "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",                    "name": "WSJ World",         "tier": 1},
    {"url": "https://feeds.reuters.com/reuters/businessNews",                  "name": "Reuters Business",  "tier": 1},
    {"url": "https://feeds.reuters.com/reuters/companyNews",                   "name": "Reuters Companies", "tier": 1},
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml",                 "name": "BBC Business",      "tier": 1},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",      "name": "NYT Business",      "tier": 1},
    {"url": "https://feeds.ft.com/rss/companies/us",                          "name": "FT US Companies",   "tier": 1},
    {"url": "https://feeds.bloomberg.com/markets/news.rss",                   "name": "Bloomberg Mkts",    "tier": 1},

    # ── Tier 2: Professional Financial Media ─────────────────────────────────
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",          "name": "CNBC",              "tier": 2},
    {"url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",           "name": "CNBC Markets",      "tier": 2},
    {"url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",           "name": "CNBC Finance",      "tier": 2},
    {"url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",           "name": "CNBC Tech",         "tier": 2},
    {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",           "name": "CNBC Economy",      "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/",          "name": "MarketWatch",       "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/marketpulse/",         "name": "MW Pulse",          "tier": 2},
    {"url": "https://www.investing.com/rss/news.rss",                         "name": "Investing.com",     "tier": 2},
    {"url": "https://www.investing.com/rss/market_overview.rss",              "name": "Investing Mkt",     "tier": 2},
    {"url": "https://finance.yahoo.com/news/rssindex",                        "name": "Yahoo Finance",     "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EGSPC",          "name": "Yahoo S&P News",    "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EDJI",           "name": "Yahoo DJIA News",   "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EIXIC",          "name": "Yahoo Nasdaq News", "tier": 2},
    {"url": "https://seekingalpha.com/feed.xml",                              "name": "Seeking Alpha",     "tier": 2},
    {"url": "https://seekingalpha.com/feed/market-news.xml",                  "name": "SA Market News",    "tier": 2},
    {"url": "https://www.benzinga.com/feed",                                  "name": "Benzinga",          "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=Markets",       "name": "Nasdaq Markets",    "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=Earnings",      "name": "Nasdaq Earnings",   "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=IPOs",          "name": "Nasdaq IPOs",       "tier": 2},
    {"url": "https://www.barrons.com/feed",                                   "name": "Barron's",          "tier": 2},

    # ── Tier 2: Wire / PR (earnings releases, M&A, FDA) ─────────────────────
    {"url": "https://feeds.businesswire.com/rss/home/?rss=G1&rssid=1",       "name": "Business Wire",     "tier": 2},
    {"url": "https://www.globenewswire.com/RssFeed/subjectcode/17-Financial%20Markets", "name": "GlobeNewsWire", "tier": 2},
    {"url": "https://www.prnewswire.com/rss/news-releases-list.rss",          "name": "PR Newswire",       "tier": 2},
    {"url": "https://www.accesswire.com/rss/feed.aspx",                       "name": "AccessWire",        "tier": 2},

    # ── Tier 2: Macro / Geopolitical / Commodities ───────────────────────────
    {"url": "https://feeds.reuters.com/reuters/world-news",                    "name": "Reuters World",     "tier": 2},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",       "name": "NYT Economy",       "tier": 2},
    {"url": "https://feeds.feedburner.com/zaborskaya/oil-price",              "name": "Oil Price",         "tier": 2},
    {"url": "https://www.federalreserve.gov/feeds/press_all.xml",             "name": "Fed Reserve",       "tier": 1},

    # ── Tier 3: Sector-specific ──────────────────────────────────────────────
    {"url": "https://techcrunch.com/feed/",                                    "name": "TechCrunch",        "tier": 3},
    {"url": "https://www.theverge.com/rss/index.xml",                          "name": "The Verge",         "tier": 3},
    {"url": "https://arstechnica.com/feed/",                                   "name": "Ars Technica",      "tier": 3},
    {"url": "https://www.statnews.com/feed/",                                  "name": "STAT News",         "tier": 3},
    {"url": "https://www.fiercepharma.com/rss/xml",                            "name": "Fierce Pharma",     "tier": 3},
    {"url": "https://electrek.co/feed/",                                       "name": "Electrek",          "tier": 3},
    {"url": "https://www.spglobal.com/commodityinsights/en/rss-feed/oil",     "name": "S&P Oil",           "tier": 3},
]

# ── Per-ticker Yahoo Finance RSS — watches these stocks specifically ─────────
_TICKER_WATCH = [
    # Mega-cap (Big 7)
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA",
    # Semis
    "AMD", "INTC", "TSM", "AVGO", "QCOM", "ARM", "MU", "ASML",
    # AI / Cloud / SaaS
    "PLTR", "CRWD", "PANW", "NET", "SNOW", "DDOG", "NOW", "CRM", "ORCL",
    # Crypto-adjacent
    "COIN", "MSTR", "RIOT", "MARA", "HOOD", "SOFI",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "SQ", "SCHW",
    # Healthcare / Pharma
    "LLY", "MRNA", "ABBV", "UNH", "REGN", "VRTX",
    # Energy
    "XOM", "CVX", "OXY",
    # Consumer / Media
    "NFLX", "DIS", "NKE", "SBUX", "MCD",
    # EVs
    "RIVN", "LCID", "GM", "F",
    # Popular high-volume trades
    "SMCI", "SHOP", "SNAP", "RBLX", "LYFT", "DASH", "ROKU",
]
RSS_SOURCES += [
    {"url": f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US",
     "name": f"Yahoo/{t}", "tier": 2}
    for t in _TICKER_WATCH
]

class RSSFeed:
    def __init__(self):
        self._seen_ids: set = set()
        self._seen_headline_hashes: set = set()
        self._recent_articles: list = []

    @staticmethod
    def _headline_hash(headline: str) -> str:
        """Normalize headline and return an MD5 hash for cross-source deduplication."""
        normalized = re.sub(r'[^a-z0-9]', '', headline.lower())
        return hashlib.md5(normalized.encode()).hexdigest()

    async def fetch(self) -> list[dict]:
        import feedparser
        import aiohttp
        import email.utils

        cutoff = time.time() - 3600  # only articles from last 1 hour
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FinanceScreener/1.0)"}
        connector = aiohttp.TCPConnector(ssl=False)  # skip SSL cert verify for some feeds

        async def fetch_source(session: aiohttp.ClientSession, source: dict) -> list[dict]:
            items = []
            try:
                async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    text = await resp.text()
                feed = feedparser.parse(text)
                for entry in feed.entries:
                    uid = entry.get("id") or entry.get("link") or entry.get("title")
                    if not uid or uid in self._seen_ids:
                        continue
                    # ── 60-Minute Hard Stop: only process articles published within last hour ──
                    # Rule 1: Articles older than 60 minutes are discarded immediately
                    # Rule 2: Use the ORIGINAL publication timestamp, not scrape/index time
                    # Rule 3: If no valid publication date can be determined, discard the article
                    pub_ts = None
                    published = entry.get("published") or entry.get("updated")
                    if published:
                        try:
                            pub_ts = email.utils.parsedate_to_datetime(published).timestamp()
                        except Exception:
                            # Try feedparser's parsed time tuple as fallback
                            pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                            if pub_struct:
                                try:
                                    import calendar
                                    pub_ts = calendar.timegm(pub_struct)
                                except Exception:
                                    pass
                    else:
                        # No date string — try parsed structs directly
                        pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                        if pub_struct:
                            try:
                                import calendar
                                pub_ts = calendar.timegm(pub_struct)
                            except Exception:
                                pass

                    # STRICT: No valid publication timestamp → skip entirely
                    if pub_ts is None:
                        continue
                    # STRICT: Article older than 60 minutes → discard
                    if pub_ts < cutoff:
                        continue
                    # Guard against future timestamps (clock skew) — clamp to now
                    if pub_ts > time.time() + 300:  # allow 5min tolerance
                        continue
                    raw_title = entry.get("title", "").strip()
                    if not raw_title:
                        continue
                    # Strip HTML tags from title and body (some feeds embed raw HTML)
                    headline = re.sub(r'<[^>]+>', '', raw_title).strip()
                    headline = headline.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
                    if not headline:
                        continue
                    raw_body = entry.get("summary", entry.get("description", ""))
                    body = re.sub(r'<[^>]+>', '', raw_body).strip() if raw_body else ""
                    items.append({
                        "uid": uid,
                        "source": source["name"],
                        "source_tier": source["tier"],
                        "headline": headline,
                        "body": body,
                        "link": entry.get("link", ""),
                        "pub_ts": pub_ts,  # original publication timestamp
                    })
            except Exception as e:
                print(f"  [RSS] Failed to fetch {source['name']}: {e}")
            return items

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            results = await asyncio.gather(
                *[fetch_source(session, source) for source in RSS_SOURCES]
            )

        new_items = []
        for source_items in results:
            for item in source_items:
                uid = item.pop("uid")
                if uid in self._seen_ids:
                    continue
                self._seen_ids.add(uid)
                h = self._headline_hash(item["headline"])
                if h in self._seen_headline_hashes:
                    continue
                self._seen_headline_hashes.add(h)
                new_items.append(item)

        self._recent_articles.extend(new_items)
        self._recent_articles = self._recent_articles[-600:]
        return new_items


# ─── WebSocket News Feed Providers ────────────────────────────────────────────
# Configuration for each supported WebSocket news provider.
# Set your API key via environment variable or pass directly.
# To add a new provider, add an entry with: url, name, tier, auth, and parser.

import os

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

# ═══════════════════════════════════════════════════════════════════════════════
# LIVE MARKET STATE — Real-time VIX, SPY, pre-market detection, earnings season
# ═══════════════════════════════════════════════════════════════════════════════

class LiveMarketState:
    """
    Fetches live market context via yfinance:
      - VIX level and derived regime (calm / normal / volatile / crisis)
      - SPY daily change %
      - Pre-market / after-hours detection (ET timezone)
      - Earnings season heuristic (heavy reporting months)
    Refreshes on demand; callers should invoke update() periodically.
    """

    REFRESH_MARKET_HOURS = 60     # seconds — during trading hours (9:30–16:00 ET)
    REFRESH_EXTENDED_HOURS = 120  # seconds — pre-market / after-hours (4:00–9:30, 16:00–20:00)
    REFRESH_CLOSED = 600          # seconds — market closed (nights, weekends)

    # Months with heaviest earnings reporting (Jan, Apr, Jul, Oct)
    EARNINGS_MONTHS = {1, 4, 7, 10}

    def __init__(self):
        self.state: dict = {
            "vix": 18.5,
            "market_regime": "normal",
            "spy_change_pct": 0.0,
            "is_pre_market": False,
            "is_earnings_season": False,
            "market_open": False,
        }
        self._last_refresh: float = 0.0
        self._initialized = False

    def _get_refresh_interval(self) -> int:
        """Return adaptive refresh interval based on market hours."""
        try:
            import zoneinfo
            et = zoneinfo.ZoneInfo("America/New_York")
        except Exception:
            et = timezone(timedelta(hours=-5))
        now_et = datetime.now(et)
        # Weekends
        if now_et.weekday() >= 5:
            return self.REFRESH_CLOSED
        t = now_et.hour * 60 + now_et.minute
        if 570 <= t < 960:      # 9:30 AM – 4:00 PM ET
            return self.REFRESH_MARKET_HOURS
        elif 240 <= t < 570 or 960 <= t < 1200:  # 4:00–9:30 or 16:00–20:00
            return self.REFRESH_EXTENDED_HOURS
        return self.REFRESH_CLOSED

    def _determine_regime(self, vix: float) -> str:
        if vix < 15:
            return "calm"
        elif vix < 20:
            return "normal"
        elif vix < 30:
            return "volatile"
        else:
            return "crisis"

    def _detect_pre_market(self) -> bool:
        """Check if current time is pre-market (4:00–9:30 ET) or after-hours (16:00–20:00 ET)."""
        try:
            import zoneinfo
            et = zoneinfo.ZoneInfo("America/New_York")
        except Exception:
            # Fallback: approximate ET as UTC-5
            et = timezone(timedelta(hours=-5))
        now_et = datetime.now(et)
        hour, minute = now_et.hour, now_et.minute
        t = hour * 60 + minute
        # Pre-market: 4:00 AM – 9:30 AM ET
        return 240 <= t < 570

    def _is_market_open(self) -> bool:
        """Check if NYSE is currently in regular trading hours (9:30–16:00 ET, weekdays)."""
        try:
            import zoneinfo
            et = zoneinfo.ZoneInfo("America/New_York")
        except Exception:
            et = timezone(timedelta(hours=-5))
        now_et = datetime.now(et)
        if now_et.weekday() >= 5:
            return False
        t = now_et.hour * 60 + now_et.minute
        return 570 <= t < 960  # 9:30 AM – 4:00 PM

    def _detect_earnings_season(self) -> bool:
        """Earnings season = last 2 weeks of Jan/Apr/Jul/Oct + first 2 weeks of Feb/May/Aug/Nov."""
        now = datetime.now(timezone.utc)
        month, day = now.month, now.day
        # Late month of earnings quarter
        if month in self.EARNINGS_MONTHS and day >= 15:
            return True
        # Early month after earnings quarter
        if month in {m + 1 for m in self.EARNINGS_MONTHS} and day <= 15:
            return True
        return False

    async def update(self, force: bool = False) -> dict:
        """Fetch live VIX + SPY data. Adaptive refresh based on market hours."""
        now = time.time()
        interval = self._get_refresh_interval()
        if not force and (now - self._last_refresh) < interval:
            # Update time-sensitive fields without API call
            self.state["is_pre_market"] = self._detect_pre_market()
            return self.state

        import yfinance as yf

        def _fetch_vix_spy():
            vix_val, spy_pct = None, None
            try:
                vix_info = yf.Ticker("^VIX").fast_info
                vix_val = getattr(vix_info, "last_price", None)
            except Exception as e:
                print(f"  [MarketState] VIX fetch failed: {e}")
            try:
                spy_info = yf.Ticker("SPY").fast_info
                last = getattr(spy_info, "last_price", None)
                prev = getattr(spy_info, "previous_close", None)
                if last and prev and prev != 0:
                    spy_pct = round((last - prev) / prev * 100, 2)
            except Exception as e:
                print(f"  [MarketState] SPY fetch failed: {e}")
            return vix_val, spy_pct

        try:
            vix_val, spy_pct = await asyncio.to_thread(_fetch_vix_spy)

            if vix_val is not None:
                self.state["vix"] = round(vix_val, 2)
                self.state["market_regime"] = self._determine_regime(vix_val)

            if spy_pct is not None:
                self.state["spy_change_pct"] = spy_pct

            self.state["is_pre_market"] = self._detect_pre_market()
            self.state["is_earnings_season"] = self._detect_earnings_season()
            self.state["market_open"] = self._is_market_open()
            self._last_refresh = now
            self._initialized = True

            regime = self.state["market_regime"].upper()
            refresh_s = self._get_refresh_interval()
            print(f"  [MarketState] LIVE — VIX: {self.state['vix']:.2f} ({regime})  "
                  f"SPY: {self.state['spy_change_pct']:+.2f}%  "
                  f"Pre-market: {self.state['is_pre_market']}  "
                  f"Market open: {self.state['market_open']}  "
                  f"Earnings season: {self.state['is_earnings_season']}  "
                  f"Next refresh: {refresh_s}s")

            # Push to all connected dashboard clients
            await broadcast_market_state()

        except Exception as e:
            print(f"  [MarketState] Update failed, using last known values: {e}")

        return self.state


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

class EventDatabase:
    DB_PATH = "nyse_events.db"

    def __init__(self):
        self.con = sqlite3.connect(self.DB_PATH, check_same_thread=False)
        self._create_table()
        count = self.count()
        print(f"  [DB] Database ready: {self.DB_PATH} ({count} events stored)")

    def _create_table(self):
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id           TEXT PRIMARY KEY,
                timestamp          REAL,
                headline           TEXT,
                source             TEXT,
                source_tier        INTEGER,
                event_type         TEXT,
                direction          TEXT,
                sentiment          REAL,
                impact_score       INTEGER,
                urgency            TEXT,
                brief              TEXT,
                buy_signal         TEXT,
                buy_confidence     INTEGER,
                affected_tickers   TEXT,
                affected_sectors   TEXT,
                affected_etfs      TEXT,
                stock_availability TEXT,
                latency_ms         REAL
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                event_id           TEXT,
                ticker             TEXT,
                signal             TEXT,
                confidence         INTEGER,
                entry_price        REAL,
                entry_time         REAL,
                price_1h           REAL,
                price_4h           REAL,
                price_1d           REAL,
                price_1w           REAL,
                pct_1h             REAL,
                pct_4h             REAL,
                pct_1d             REAL,
                pct_1w             REAL,
                outcome_1h         TEXT,
                outcome_4h         TEXT,
                outcome_1d         TEXT,
                outcome_1w         TEXT,
                completed          INTEGER DEFAULT 0,
                PRIMARY KEY (event_id, ticker)
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_completed
            ON signal_outcomes(completed)
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events(timestamp)
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_impact_score
            ON events(impact_score)
        """)
        self.con.commit()

    def insert(self, event: "ScoredEvent"):
        try:
            self.con.execute(
                "INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.event_id, event.timestamp, event.headline,
                    event.source, event.source_tier, event.event_type.value,
                    event.direction.value, event.sentiment, event.impact_score,
                    event.urgency.value, event.brief, event.buy_signal,
                    event.buy_confidence,
                    json.dumps(event.affected_tickers),
                    json.dumps(event.affected_sectors),
                    json.dumps(event.affected_etfs),
                    json.dumps(event.stock_availability),
                    event.latency_ms,
                )
            )
            self.con.commit()
        except Exception as e:
            print(f"  [DB] Insert error: {e}")

    def get_csv(self) -> str:
        cur = self.con.execute("SELECT * FROM events ORDER BY timestamp DESC")
        cols = [d[0] for d in cur.description]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        w.writerows(cur.fetchall())
        return buf.getvalue()

    def get_json(self) -> str:
        cur = self.con.execute("SELECT * FROM events ORDER BY timestamp DESC")
        cols = [d[0] for d in cur.description]
        return json.dumps([dict(zip(cols, r)) for r in cur.fetchall()], indent=2)

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def get_recent_events(self, limit: int = 100, max_age_seconds: int = 3600) -> list[dict]:
        """Get recent events formatted for the frontend (same shape as WS broadcast).
        Only returns events from the last max_age_seconds (default: 1 hour)."""
        import time
        cutoff = time.time() - max_age_seconds
        cur = self.con.execute(
            "SELECT event_id, timestamp, headline, source, source_tier, "
            "event_type, direction, sentiment, impact_score, urgency, brief, "
            "buy_signal, buy_confidence, affected_tickers, affected_sectors, "
            "affected_etfs, stock_availability, latency_ms "
            "FROM events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit,)
        )
        results = []
        for row in cur.fetchall():
            tickers = json.loads(row[13]) if row[13] else []
            sectors = json.loads(row[14]) if row[14] else []
            etfs = json.loads(row[15]) if row[15] else []
            avail = json.loads(row[16]) if row[16] else {}
            # Build price_data from stock_availability
            price_data = {}
            for t, v in avail.items():
                if isinstance(v, dict):
                    price_data[t] = {"price": v.get("price"), "change_pct": v.get("change_pct")}
            results.append({
                "type": "event",
                "id": row[0],
                "ts": row[1] * 1000,
                "headline": row[2],
                "source": row[3],
                "tier": row[4],
                "type": row[5],
                "direction": row[6],
                "sentiment": row[7],
                "score": row[8],
                "tickers": tickers,
                "sectors": sectors,
                "etfs": etfs,
                "latency": row[17],
                "brief": row[10],
                "buy_signal": row[11],
                "buy_confidence": row[12],
                "reasoning": [],
                "risk": "",
                "time_horizon": "",
                "correlated_moves": [],
                "url": "",
                "stock_availability": avail,
                "price_data": price_data,
            })
        return results

    # ── Signal Outcome Tracking ──────────────────────────────────────────────

    def insert_signal(self, event_id: str, ticker: str, signal: str,
                      confidence: int, entry_price: float, entry_time: float):
        """Record a new signal to track."""
        try:
            self.con.execute(
                "INSERT OR IGNORE INTO signal_outcomes "
                "(event_id, ticker, signal, confidence, entry_price, entry_time) "
                "VALUES (?,?,?,?,?,?)",
                (event_id, ticker, signal, confidence, entry_price, entry_time)
            )
            self.con.commit()
        except Exception as e:
            print(f"  [DB] Signal insert error: {e}")

    def get_pending_signals(self) -> list[dict]:
        """Get signals that still need price checkpoints."""
        cur = self.con.execute(
            "SELECT event_id, ticker, signal, confidence, entry_price, entry_time, "
            "price_1h, price_4h, price_1d, price_1w "
            "FROM signal_outcomes WHERE completed = 0"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def update_signal_checkpoint(self, event_id: str, ticker: str,
                                  checkpoint: str, price: float, pct: float, outcome: str):
        """Update a specific time checkpoint (1h, 4h, 1d, 1w)."""
        valid = {"1h", "4h", "1d", "1w"}
        if checkpoint not in valid:
            return
        try:
            self.con.execute(
                f"UPDATE signal_outcomes SET price_{checkpoint}=?, pct_{checkpoint}=?, "
                f"outcome_{checkpoint}=? WHERE event_id=? AND ticker=?",
                (price, pct, outcome, event_id, ticker)
            )
            # Mark completed if this is the last checkpoint (1w)
            if checkpoint == "1w":
                self.con.execute(
                    "UPDATE signal_outcomes SET completed=1 WHERE event_id=? AND ticker=?",
                    (event_id, ticker)
                )
            self.con.commit()
        except Exception as e:
            print(f"  [DB] Signal checkpoint update error: {e}")

    def get_signal_stats(self) -> dict:
        """Compute aggregate win/loss stats across all tracked signals."""
        stats = {"total": 0, "buy": {}, "sell": {}}
        for signal_type in ("BUY", "SELL"):
            for cp in ("1h", "4h", "1d", "1w"):
                cur = self.con.execute(
                    f"SELECT COUNT(*), "
                    f"SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
                    f"SUM(CASE WHEN outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
                    f"AVG(pct_{cp}) "
                    f"FROM signal_outcomes WHERE signal=? AND pct_{cp} IS NOT NULL",
                    (signal_type,)
                )
                total, wins, losses, avg_pct = cur.fetchone()
                stats[signal_type.lower()][cp] = {
                    "total": total or 0,
                    "wins": wins or 0,
                    "losses": losses or 0,
                    "win_rate": round((wins / total) * 100, 1) if total else 0,
                    "avg_return": round(avg_pct, 2) if avg_pct else 0,
                }
        stats["total"] = self.con.execute(
            "SELECT COUNT(*) FROM signal_outcomes"
        ).fetchone()[0]
        return stats

    def get_recent_outcomes(self, limit: int = 20) -> list[dict]:
        """Get most recent signal outcomes for display."""
        cur = self.con.execute(
            "SELECT s.event_id, s.ticker, s.signal, s.confidence, s.entry_price, "
            "s.entry_time, s.pct_1h, s.pct_4h, s.pct_1d, s.pct_1w, "
            "s.outcome_1h, s.outcome_4h, s.outcome_1d, s.outcome_1w, "
            "e.headline "
            "FROM signal_outcomes s LEFT JOIN events e ON s.event_id = e.event_id "
            "ORDER BY s.entry_time DESC LIMIT ?",
            (limit,)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_tracked_ids(self) -> list[dict]:
        """Get list of all currently tracked event_id + ticker pairs."""
        cur = self.con.execute(
            "SELECT event_id, ticker FROM signal_outcomes ORDER BY entry_time DESC"
        )
        return [{"event_id": r[0], "ticker": r[1]} for r in cur.fetchall()]

    def remove_signal(self, event_id: str, ticker: str = None):
        """Remove a tracked signal (untrack)."""
        try:
            if ticker:
                self.con.execute(
                    "DELETE FROM signal_outcomes WHERE event_id=? AND ticker=?",
                    (event_id, ticker)
                )
            else:
                self.con.execute(
                    "DELETE FROM signal_outcomes WHERE event_id=?",
                    (event_id,)
                )
            self.con.commit()
            print(f"  [Tracker] Untracked signal {event_id} {ticker or '(all tickers)'}")
        except Exception as e:
            print(f"  [DB] Signal remove error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: EXPANDED SIMULATED NEWS FEED — 25 Events Across All Sectors
# ═══════════════════════════════════════════════════════════════════════════════

DUMMY_NEWS_FEED: list[dict] = [
    # ── SEMICONDUCTORS ──────────────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "U.S. Commerce Dept announces sweeping new chip export controls targeting China's AI sector",
        "body": "The Biden administration unveiled new restrictions on semiconductor exports to China, "
                "specifically targeting advanced AI chips and lithography equipment. NVIDIA, AMD, and "
                "ASML are expected to be most affected. The rules take effect in 90 days and close "
                "prior loopholes that allowed modified chip designs to bypass controls.",
        "tickers": ["NVDA", "AMD", "ASML"],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "TSMC reports record Q4 revenue, raises 2026 capex to $40B on AI chip demand surge",
        "body": "Taiwan Semiconductor Manufacturing Company posted record quarterly revenue of $23.6B, "
                "beating estimates by 8%. The company raised its 2026 capital expenditure forecast to "
                "$40B, citing unprecedented demand for advanced 3nm and 2nm AI chips from NVIDIA and AMD.",
        "tickers": ["TSM"],
    },
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Micron Technology beats earnings, HBM memory demand exceeds all forecasts",
        "body": "Micron reported EPS of $1.82 vs $1.45 expected. High-bandwidth memory (HBM) revenue "
                "tripled year-over-year, driven by AI accelerator demand from NVIDIA and AMD. The "
                "company raised guidance for the next two quarters.",
        "tickers": ["MU"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "Intel CEO Pat Gelsinger resigns amid foundy struggles; board names interim leadership",
        "body": "Intel CEO Pat Gelsinger has stepped down effective immediately after the board lost "
                "confidence in the company's foundry turnaround plan. Intel's contract manufacturing "
                "business has consistently missed yield targets. CFO David Zinsner and VP MJ Holthaus "
                "named interim co-CEOs.",
        "tickers": ["INTC"],
    },

    # ── ENERGY ──────────────────────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "OPEC+ agrees to deepen oil production cuts by 1.5M barrels/day starting January",
        "body": "OPEC+ ministers agreed to an additional 1.5 million barrel-per-day production cut, "
                "the largest surprise reduction since 2020. Saudi Arabia will shoulder 500K bpd, "
                "with Russia and UAE splitting the remainder. Brent crude surged 6% on the news.",
        "tickers": [],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Exxon Mobil declares force majeure on Permian Basin operations after pipeline explosion",
        "body": "An explosion at a major Exxon Mobil pipeline junction in the Permian Basin has "
                "forced the company to declare force majeure on approximately 200K bpd of production. "
                "Halliburton and Schlumberger crews are responding. Full restoration expected in 4-6 weeks.",
        "tickers": ["XOM"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "First Solar surges after IRA tax credit extension confirmed through 2035",
        "body": "First Solar shares rallied in pre-market after Congress confirmed the extension "
                "of Inflation Reduction Act solar manufacturing tax credits through 2035. Enphase "
                "Energy also expected to benefit from the expanded timeline.",
        "tickers": ["FSLR", "ENPH"],
    },

    # ── FINANCIALS ──────────────────────────────────────────────────────────
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "JPMorgan to acquire regional bank First Republic in $10.6B deal",
        "body": "JPMorgan Chase has agreed to acquire substantially all of First Republic Bank's "
                "assets in a deal valued at $10.6 billion. The FDIC-assisted transaction includes "
                "all deposits and most assets. Jamie Dimon called it a 'responsible resolution.'",
        "tickers": ["JPM"],
    },
    {
        "source": "SEC EDGAR",
        "source_tier": 2,
        "headline": "SEC charges Goldman Sachs with misleading investors on ESG fund practices",
        "body": "The Securities and Exchange Commission has charged Goldman Sachs Asset Management "
                "with failing to follow its own policies for ESG investing. Goldman neither admitted "
                "nor denied the findings and agreed to pay a $4M fine.",
        "tickers": ["GS"],
    },
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Visa reports record Q4 transaction volume, announces $10B buyback program",
        "body": "Visa reported Q4 earnings above estimates with payment volume reaching an all-time "
                "high of $3.5 trillion. The board authorized a new $10B share repurchase program. "
                "Cross-border transactions grew 15% year-over-year.",
        "tickers": ["V"],
    },

    # ── HEALTHCARE / PHARMA ─────────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "BREAKING: FDA approves Pfizer's new RSV vaccine for elderly adults",
        "body": "The FDA granted full approval to Pfizer's respiratory syncytial virus vaccine, "
                "making it the first approved RSV shot for adults over 60. Analysts estimate "
                "peak sales of $5B annually.",
        "tickers": ["PFE"],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Eli Lilly obesity drug Mounjaro Phase 3 data shows 26% weight loss, surpassing Ozempic",
        "body": "Eli Lilly released Phase 3 clinical trial data showing its obesity drug achieved "
                "26.2% average weight loss at 72 weeks, significantly exceeding Novo Nordisk's "
                "Ozempic at 16.9%. The data positions Mounjaro as the potential market leader in "
                "the $100B+ obesity treatment market.",
        "tickers": ["LLY"],
    },
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "UnitedHealth Group CEO under DOJ investigation for insider trading — shares halted",
        "body": "The Department of Justice has opened a criminal investigation into UnitedHealth "
                "Group's CEO for alleged insider trading ahead of a major acquisition announcement. "
                "Trading in UNH shares has been halted pending further information.",
        "tickers": ["UNH"],
    },

    # ── DEFENSE / AEROSPACE ─────────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Pentagon awards Lockheed Martin $22B contract for next-generation fighter jet",
        "body": "The Department of Defense awarded Lockheed Martin a $22 billion contract for "
                "the Next Generation Air Dominance (NGAD) program, the largest single defense "
                "contract in a decade. Northrop Grumman and RTX will serve as key subcontractors.",
        "tickers": ["LMT"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "Boeing 737 MAX deliveries halted again after new fuselage quality defect found",
        "body": "Boeing has paused deliveries of its 737 MAX aircraft after discovering a new "
                "manufacturing defect in the fuselage. The FAA is investigating. This marks the "
                "third delivery halt in 18 months. GE Aerospace engine deliveries also impacted.",
        "tickers": ["BA"],
    },

    # ── MACRO EVENTS ────────────────────────────────────────────────────────
    {
        "source": "BLS",
        "source_tier": 1,
        "headline": "CPI rises 0.6% in March, hotter than expected — core inflation surges to 4.1%",
        "body": "The Bureau of Labor Statistics reported the Consumer Price Index rose 0.6% in March, "
                "well above the 0.3% consensus. Core CPI hit 4.1% year-over-year, raising fears "
                "the Fed will maintain hawkish stance longer than markets anticipated.",
        "tickers": [],
    },
    {
        "source": "Federal Reserve",
        "source_tier": 1,
        "headline": "FOMC holds rate steady at 5.25-5.50%, signals hawkish stance with dot plot showing no cuts until Q3",
        "body": "The Federal Reserve held the federal funds rate unchanged at 5.25-5.50% as expected. "
                "However, the updated dot plot surprised markets by signaling no rate cuts until at "
                "least Q3, with two governors dissenting in favor of a hike.",
        "tickers": [],
    },
    {
        "source": "BLS",
        "source_tier": 1,
        "headline": "Nonfarm payrolls surge by 353K in January, crushing 180K estimate — wages rise 0.6%",
        "body": "The U.S. economy added 353,000 jobs in January, nearly double the consensus forecast. "
                "Average hourly earnings rose 0.6%, also above expectations. The unemployment rate "
                "held at 3.7%. Markets repriced rate cut expectations sharply.",
        "tickers": [],
    },

    # ── MATERIALS / MINING ──────────────────────────────────────────────────
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Copper prices surge to all-time high on China stimulus + AI data center demand",
        "body": "Copper futures hit a record $5.20/lb, driven by China's massive infrastructure "
                "stimulus package and surging demand from AI data center construction. Freeport-McMoRan, "
                "the world's largest public copper miner, is the primary beneficiary.",
        "tickers": ["FCX"],
    },

    # ── UTILITIES / DATA CENTERS ────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Vistra Energy surges after securing $4.2B in long-term nuclear power contracts with hyperscalers",
        "body": "Vistra Corp announced $4.2 billion in long-term power purchase agreements with "
                "major tech companies for its Comanche Peak nuclear facility. The contracts, "
                "spanning 15-20 years, will power AI data centers. This follows similar deals "
                "by Constellation Energy.",
        "tickers": ["VST"],
    },

    # ── REITs ───────────────────────────────────────────────────────────────
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Equinix announces $5B data center expansion across 8 markets to meet AI demand",
        "body": "Equinix, the world's largest data center REIT, announced a $5 billion expansion "
                "plan targeting 8 new metropolitan markets. The investment is driven by surging "
                "demand from cloud providers and AI workloads. Prologis also benefits from "
                "industrial logistics supporting these buildouts.",
        "tickers": ["EQIX"],
    },

    # ── GEOPOLITICAL ────────────────────────────────────────────────────────
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "China announces retaliatory tariffs of 25% on U.S. agricultural and semiconductor equipment exports",
        "body": "China's Commerce Ministry announced 25% tariffs on U.S. agricultural machinery, "
                "semiconductor manufacturing equipment, and selected energy products in retaliation "
                "for new U.S. chip export controls. Deere, Applied Materials, and Lam Research "
                "are directly impacted. Markets selling off broadly.",
        "tickers": [],
    },

    # ── CONSUMER ────────────────────────────────────────────────────────────
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Walmart beats Q3 earnings estimates, raises full-year guidance on strong grocery and e-commerce",
        "body": "Walmart reported Q3 EPS of $1.53, beating consensus of $1.32. Revenue came in at "
                "$160.8B vs. $159.7B expected. The company raised its full-year guidance citing "
                "strong grocery demand and e-commerce growth.",
        "tickers": ["WMT"],
    },

    # ── CYBER / TECH ────────────────────────────────────────────────────────
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Massive cyberattack hits AT&T — 70M customer records exposed, FCC launches probe",
        "body": "AT&T disclosed a major data breach affecting approximately 70 million current and "
                "former customers. Social security numbers, account details, and passcodes were "
                "compromised. The FCC has opened a formal investigation. AT&T faces potential "
                "fines exceeding $1 billion.",
        "tickers": ["T"],
    },

    # ── LOW NOISE — Should score low ────────────────────────────────────────
    {
        "source": "Twitter/X",
        "source_tier": 3,
        "headline": "Rumor: Nike may be exploring strategic options including potential sale",
        "body": "Unconfirmed reports suggest Nike's board has engaged advisors to explore "
                "strategic alternatives. No official statement from the company.",
        "tickers": ["NKE"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    global _LIVE_MARKET_STATE, _SIGNAL_TRACKER_DB, _SIGNAL_TRACKER

    screener = NYSEImpactScreener(alert_threshold=0)
    screener.alert_dispatcher.set_broadcast_callback(broadcast_event)
    screener.signal_tracker.set_broadcast_callback(_broadcast_signal_performance)
    rss = RSSFeed()
    ws_news = WebSocketNewsFeed()  # auto-detects providers from env vars
    screener.rss = rss
    await start_http_server(screener.db)

    # Wire up global references so WS handler can send state on connect
    _LIVE_MARKET_STATE = screener.reference_db.live_market
    _SIGNAL_TRACKER_DB = screener.db
    _SIGNAL_TRACKER = screener.signal_tracker

    # Initial live market state fetch (VIX, SPY, pre-market, earnings season)
    print("  [MarketState] Fetching initial live market data...")
    await screener.reference_db.live_market.update(force=True)

    # Start signal outcome tracker as a background task
    asyncio.create_task(screener.signal_tracker.run_loop())

    # Start WebSocket news feed listeners (Finnhub, Benzinga, Polygon — whichever has API keys)
    ws_news.start()

    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print("  WebSocket server listening on ws://localhost:8765")
        active = ws_news.active_providers
        if active:
            print(f"  WebSocket news feeds active: {', '.join(active)}")
        print("  Polling RSS feeds every 60 seconds. Press Ctrl+C to stop.\n")
        while True:
            # Refresh market state each cycle (auto-skips if within cooldown)
            await screener.reference_db.live_market.update()

            # ── Drain WebSocket news (real-time, arrives between RSS polls) ───
            ws_items = await ws_news.drain()
            if ws_items:
                print(f"  [WS-News] {len(ws_items)} new articles from WebSocket feeds")
                await screener.run_feed(ws_items, delay=0.1)

            # ── Poll RSS feeds (bulk, every 60s) ─────────────────────────────
            items = await rss.fetch()
            if items:
                print(f"  [RSS] {len(items)} new articles fetched")
                await screener.run_feed(items, delay=0.3)
            else:
                print("  [RSS] No new articles, waiting...")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
