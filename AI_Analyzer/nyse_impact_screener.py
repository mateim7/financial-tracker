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
    disconnected = set()
    for ws in WS_CLIENTS:
        try:
            await ws.send(payload)
        except websockets.ConnectionClosed:
            disconnected.add(ws)
    WS_CLIENTS -= disconnected

# Global references set in main() so WS handler can send state on connect
_LIVE_MARKET_STATE: "LiveMarketState | None" = None
_SIGNAL_TRACKER_DB: "EventDatabase | None" = None
_SIGNAL_TRACKER: "SignalOutcomeTracker | None" = None


async def broadcast_market_state():
    """Push current market state (VIX, regime, SPY, etc.) to all WS clients."""
    if not WS_CLIENTS or _LIVE_MARKET_STATE is None:
        return
    payload = json.dumps({"type": "market_state", **_LIVE_MARKET_STATE.state})
    disconnected = set()
    for ws in WS_CLIENTS:
        try:
            await ws.send(payload)
        except websockets.ConnectionClosed:
            disconnected.add(ws)
    WS_CLIENTS -= disconnected


async def broadcast_event(event):
    """Serialize a ScoredEvent and push it to all connected WebSocket clients."""
    global WS_CLIENTS
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
        "technical_data":     event.technical_data,
        "ws_source":          event.ws_source,
    }
    message = json.dumps(payload)
    disconnected = set()
    for ws in WS_CLIENTS:
        try:
            await ws.send(message)
        except websockets.ConnectionClosed:
            disconnected.add(ws)
    WS_CLIENTS -= disconnected


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


async def tech_indicators_handler(request):
    """Serves technical indicators (RSI, MACD, volume) for given tickers."""
    tickers_param = request.query.get("tickers", "")
    if not tickers_param:
        return aiohttp_web.Response(
            text=json.dumps({"error": "tickers parameter required"}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
            status=400,
        )
    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    tech = request.app.get("tech_indicators")
    if not tech:
        return aiohttp_web.Response(
            text=json.dumps({"error": "technical indicators not available"}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
            status=503,
        )
    data = await tech.get_indicators(tickers[:10])  # limit to 10 tickers per request
    return aiohttp_web.Response(
        text=json.dumps(data),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def start_http_server(db: "EventDatabase", tech_indicators=None):
    from backtesting_api import setup_backtesting_routes
    from stock_chart_api import setup_chart_routes

    app = aiohttp_web.Application()
    app["db"] = db
    if tech_indicators:
        app["tech_indicators"] = tech_indicators
    app.router.add_get("/download/{fmt}", http_handler)
    app.router.add_get("/download", http_handler)
    app.router.add_get("/api/signals", signals_handler)
    app.router.add_get("/api/events", events_handler)
    app.router.add_get("/api/tech-indicators", tech_indicators_handler)
    setup_backtesting_routes(app)
    setup_chart_routes(app)
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
# SECTION 1: DOMAIN MODELS & ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class Direction(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Urgency(Enum):
    FLASH = "FLASH"          # Breaking — requires immediate action
    HIGH = "HIGH"            # Significant — act within minutes
    STANDARD = "STANDARD"    # Notable — review within the hour
    LOW = "LOW"              # Informational — end-of-day digest


class EventType(Enum):
    # Earnings & Revenue
    EARNINGS_BEAT = "EARNINGS_BEAT"
    EARNINGS_MISS = "EARNINGS_MISS"
    REVENUE_BEAT = "REVENUE_BEAT"
    REVENUE_MISS = "REVENUE_MISS"
    GUIDANCE_RAISE = "GUIDANCE_RAISE"
    GUIDANCE_CUT = "GUIDANCE_CUT"
    # M&A and Corporate Actions
    MA_ANNOUNCED = "MA_ANNOUNCED"
    MA_BLOCKED = "MA_BLOCKED"
    SPINOFF = "SPINOFF"
    STOCK_BUYBACK = "STOCK_BUYBACK"
    DIVIDEND_CUT = "DIVIDEND_CUT"
    DIVIDEND_HIKE = "DIVIDEND_HIKE"
    STOCK_SPLIT = "STOCK_SPLIT"
    # Regulatory & Legal
    FDA_APPROVAL = "FDA_APPROVAL"
    FDA_REJECTION = "FDA_REJECTION"
    REGULATORY_ACTION = "REGULATORY_ACTION"
    ANTITRUST = "ANTITRUST"
    PATENT_RULING = "PATENT_RULING"
    # Analyst Actions
    ANALYST_UPGRADE = "ANALYST_UPGRADE"
    ANALYST_DOWNGRADE = "ANALYST_DOWNGRADE"
    ANALYST_INITIATION = "ANALYST_INITIATION"
    # Leadership
    CEO_DEPARTURE = "CEO_DEPARTURE"
    CFO_DEPARTURE = "CFO_DEPARTURE"
    BOARD_SHAKEUP = "BOARD_SHAKEUP"
    # Insider Activity
    INSIDER_BUY = "INSIDER_BUY"
    INSIDER_SELL = "INSIDER_SELL"
    # Macro Events
    MACRO_CPI = "MACRO_CPI"
    MACRO_FOMC = "MACRO_FOMC"
    MACRO_NFP = "MACRO_NFP"
    MACRO_GDP = "MACRO_GDP"
    MACRO_PPI = "MACRO_PPI"
    MACRO_RETAIL_SALES = "MACRO_RETAIL_SALES"
    MACRO_HOUSING = "MACRO_HOUSING"
    MACRO_PMI = "MACRO_PMI"
    # Sector-Specific
    CHIP_EXPORT_CONTROL = "CHIP_EXPORT_CONTROL"
    OIL_PRODUCTION_CUT = "OIL_PRODUCTION_CUT"
    OIL_INVENTORY = "OIL_INVENTORY"
    PIPELINE_DISRUPTION = "PIPELINE_DISRUPTION"
    POWER_GRID_EVENT = "POWER_GRID_EVENT"
    DRUG_TRIAL_DATA = "DRUG_TRIAL_DATA"
    CYBER_BREACH = "CYBER_BREACH"
    SUPPLY_CHAIN_DISRUPTION = "SUPPLY_CHAIN_DISRUPTION"
    PRODUCT_RECALL = "PRODUCT_RECALL"
    CONTRACT_WIN = "CONTRACT_WIN"
    CONTRACT_LOSS = "CONTRACT_LOSS"
    # Distress
    BANKRUPTCY = "BANKRUPTCY"
    CREDIT_DOWNGRADE = "CREDIT_DOWNGRADE"
    CREDIT_UPGRADE = "CREDIT_UPGRADE"
    DEBT_DEFAULT = "DEBT_DEFAULT"
    # Special
    ACTIVIST_STAKE = "ACTIVIST_STAKE"
    SHORT_SQUEEZE = "SHORT_SQUEEZE"
    GEOPOLITICAL = "GEOPOLITICAL"
    TARIFF = "TARIFF"
    SANCTIONS = "SANCTIONS"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    UNKNOWN = "UNKNOWN"


@dataclass
class RawNewsEvent:
    """Normalized news event from any source."""
    event_id: str
    timestamp: float
    source: str
    source_tier: int          # 1=institutional, 2=professional, 3=social
    headline: str
    body: str = ""
    raw_tickers: list[str] = field(default_factory=list)
    url: str = ""
    ws_source: bool = False   # True if from WebSocket feed, False if RSS


@dataclass
class ScoredEvent:
    """Fully processed and scored news event."""
    event_id: str
    timestamp: float
    headline: str
    source: str
    source_tier: int
    event_type: EventType
    urgency: Urgency
    sentiment: float          # -1.0 to +1.0
    direction: Direction
    impact_score: int         # 1-100
    affected_tickers: list[str] = field(default_factory=list)
    affected_sectors: list[str] = field(default_factory=list)
    affected_etfs: list[str] = field(default_factory=list)
    supply_chain_exposure: list[str] = field(default_factory=list)
    contagion_tickers: list[str] = field(default_factory=list)
    brief: str = ""
    buy_signal: str = ""
    buy_confidence: int = 0
    reasoning: list[str] = field(default_factory=list)
    risk: str = ""
    time_horizon: str = ""
    correlated_moves: list[str] = field(default_factory=list)
    ticker_signals: dict = field(default_factory=dict)  # {ticker: {"signal": "BUY"/"SELL"/"HOLD", "confidence": int}}
    url: str = ""
    stock_availability: dict = field(default_factory=dict)
    price_data: dict = field(default_factory=dict)
    technical_data: dict = field(default_factory=dict)  # {ticker: {rsi, macd, volume, tech_signal, ...}}
    latency_ms: float = 0.0
    ws_source: bool = False   # True if from WebSocket feed


# ═══════════════════════════════════════════════════════════════════════════════
# CLAUDE API SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class ClaudeScorer:
    # ── Headlines that are almost never market-moving (skip Claude entirely) ──
    SKIP_PATTERNS = re.compile(
        r'(?i)('
        r'\d+\s+(best|top|worst)\s+(stock|etf|fund|pick)|'       # "10 best stocks to buy"
        r'(morning|evening|daily|weekly)\s+(brief|recap|wrap|roundup)|'  # newsletters
        r'(opinion|editorial|column|commentary)\s*[:\-–—]|'      # opinion pieces
        r'(things|reasons|tips|ways)\s+(to|you)|'                 # listicles
        r'should\s+you\s+(buy|sell|invest)|'                      # clickbait advice
        r'(what\s+is|how\s+to|beginner|explained|101)|'           # educational
        r'(podcast|video|interview|transcript|webinar)|'          # media formats
        r'(sponsored|promoted|partner\s+content|advertisement)'   # ads
        r')'
    )

    def __init__(self, known_tickers: set[str] = None):
        import os
        self._known_tickers = known_tickers or set()
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  [Claude] ANTHROPIC_API_KEY not set — falling back to keyword scoring")
            self.client = None
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            print("  [Claude] API key loaded — enhanced scoring enabled")

        # Token usage tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_calls = 0
        self._calls_skipped = 0

        # Recent headline cache — avoid calling Claude for very similar headlines
        self._recent_headline_hashes: dict[str, float] = {}  # hash -> timestamp

    def _headline_sim_hash(self, headline: str) -> str:
        """Coarse hash: strip numbers/punctuation so 'NVDA up 5%' and 'NVDA up 3%' match."""
        coarse = re.sub(r'[^a-z\s]', '', headline.lower())
        coarse = re.sub(r'\s+', ' ', coarse).strip()
        return hashlib.md5(coarse.encode()).hexdigest()

    def _should_skip(self, headline: str, scored: ScoredEvent) -> str | None:
        """Return a skip reason string, or None if Claude should run."""
        # Skip listicles, opinion pieces, sponsored content, etc.
        if self.SKIP_PATTERNS.search(headline):
            return "headline matches skip pattern (opinion/listicle/ad)"

        # Skip if we already called Claude for a very similar headline recently (10 min)
        h = self._headline_sim_hash(headline)
        now = time.time()
        # Clean old entries
        self._recent_headline_hashes = {k: v for k, v in self._recent_headline_hashes.items() if now - v < 600}
        if h in self._recent_headline_hashes:
            return "similar headline already scored in last 10 min"

        # Skip UNKNOWN event type with low automated score (borderline, likely noise)
        if scored.event_type == EventType.UNKNOWN and scored.impact_score < 50:
            return "UNKNOWN event type with low auto-score"

        return None

    @property
    def usage_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "calls_skipped": self._calls_skipped,
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "estimated_cost_usd": round(
                (self._total_input_tokens * 3.0 / 1_000_000) +
                (self._total_output_tokens * 15.0 / 1_000_000), 4
            ),
        }

    async def enhance(self, scored: ScoredEvent, headline: str, body: str) -> ScoredEvent:
        """Call Claude to improve scoring fields. Falls back to original if unavailable."""
        if not self.client:
            return scored
        if scored.impact_score < 40:
            return scored

        # ── Pre-Claude skip checks (saves tokens) ────────────────────────
        skip_reason = self._should_skip(headline, scored)
        if skip_reason:
            self._calls_skipped += 1
            print(f"  [Claude] Skipped: {skip_reason}")
            return scored

        valid_types = [e.value for e in EventType]
        tickers_str = ", ".join(scored.affected_tickers) if scored.affected_tickers else "MACRO"

        # Build live price context string for Claude
        price_context_parts = []
        if scored.price_data:
            for t, pd in scored.price_data.items():
                if pd.get("price") and pd.get("change_pct") is not None:
                    price_context_parts.append(f"  {t}: ${pd['price']} ({pd['change_pct']:+.2f}% today)")
        price_context = "\n".join(price_context_parts) if price_context_parts else "  (prices unavailable)"

        prompt = f"""You are a financial news analyst. Analyze this news headline and return ONLY a JSON object.

Headline: {headline}
Body: {body[:400] if body else "N/A"}
Affected tickers: {tickers_str}

Live market data (today's price action):
{price_context}

Current automated scoring:
- event_type: {scored.event_type.value}
- sentiment: {scored.sentiment}
- impact_score: {scored.impact_score}
- direction: {scored.direction.value}

Return JSON with these exact fields:
{{
  "event_type": one of {valid_types},
  "sentiment": float from -1.0 to 1.0,
  "impact_score": integer from 1 to 100,
  "direction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "brief": one sentence summary of the market impact,
  "buy_signal": "BUY" or "HOLD" or "SELL",
  "buy_confidence": integer from 1 to 100. Be precise and granular — every value from 1 to 100 is valid. Do NOT round to multiples of 5 or 10. Think carefully and pick the exact number that reflects your conviction. Scale:
    1-10: extremely low conviction, near noise
    11-25: weak signal, high uncertainty
    26-40: below average conviction, significant risk
    41-49: borderline, slight lean
    50-64: moderate confidence, recommended consideration
    65-74: solid conviction, good risk/reward
    75-84: strong conviction, favorable setup
    85-94: high confidence, strong opportunity
    95-99: very high conviction, near certain
    100: absolute certainty (reserve only for unambiguous catalysts like FDA approval of blockbuster drug)
  "reasoning": array of 2-3 short strings, each one specific reason why this is a BUY/SELL/HOLD. Be concrete — mention numbers, catalysts, or comparisons. E.g. ["Revenue beat of 12% vs estimates signals demand inflection", "Guidance raised — rare for this sector in current macro environment"],
  "risk": one sentence on the single biggest risk that could invalidate this signal,
  "time_horizon": one of "intraday" or "swing (1-3d)" or "medium-term (1-4w)",
  "correlated_moves": array of up to 4 ticker strings (beyond the primary tickers) that are likely to move in sympathy or inverse — e.g. sector peers, suppliers, competitors. Only include real NYSE/NASDAQ tickers.
  "ticker_signals": object mapping each affected ticker AND each correlated_moves ticker to its own signal direction. CRITICAL: In macro/geopolitical events, different assets move in OPPOSITE directions due to capital rotation. For example, a Middle East escalation is BULLISH for oil (USO, XOM), gold (GLD), and defense (ITA) but BEARISH for airlines (DAL, UAL) and consumer discretionary. A trade war is BEARISH for importers but BULLISH for domestic competitors. You MUST analyze each ticker independently. Format: {{"TICKER": {{"signal": "BUY" or "SELL" or "HOLD", "confidence": 1-100}}}}. If all tickers move the same direction, they should still each have an entry. Never apply a blanket signal to all tickers without considering how the event specifically impacts each one.
}}

CRITICAL RULES:

1. "Don't shoot the messenger": If the article is a macroeconomic warning, market commentary, analyst note, research report, or rating change, DO NOT include the ticker of the investment bank or analyst firm that authored the report. Examples:
- "Goldman Sachs warns of GDP drag" → DO NOT include $GS.
- "JPMorgan downgrades VMC" → DO NOT include $JPM.
- "Morgan Stanley expects rate cuts" → DO NOT include $MS.

2. "No hallucinated associations": ONLY include tickers for companies that are explicitly mentioned in the article OR are direct competitors/suppliers/customers of the primary company. Do NOT include tickers just because you associate them with a concept in the article. Examples of what NOT to do:
- Article about "open-weight AI models" → Do NOT add Hugging Face or any AI platform ticker that isn't mentioned.
- Article about "cloud computing" → Do NOT add random cloud companies that aren't discussed.
- A person endorsing a company → Do NOT add that person's company unless the article discusses impact on it.

3. "Respect the tape": The live market data above shows how each stock is ACTUALLY trading right now. If a stock is up significantly (+3% or more) today, do NOT issue a SELL signal on it unless you have extremely high conviction (85%+) — you would be telling someone to short a stock with strong buying momentum, which is extremely dangerous. Conversely, if a stock is down significantly (-3% or more), be cautious about issuing a BUY signal. Price action reflects information you may not have. When the tape contradicts your thesis, default to HOLD or reduce confidence substantially.

Only include the tickers of companies, sectors, commodities, or ETFs that are actually AFFECTED by the news.

Only correct other scoring fields where automated scoring is clearly wrong. Return valid JSON only."""

        try:
            response = await asyncio.to_thread(
                self.client.messages.create,
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track token usage
            self._total_calls += 1
            if hasattr(response, 'usage'):
                self._total_input_tokens += getattr(response.usage, 'input_tokens', 0)
                self._total_output_tokens += getattr(response.usage, 'output_tokens', 0)

            # Cache this headline to avoid duplicate calls
            self._recent_headline_hashes[self._headline_sim_hash(headline)] = time.time()

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)

            if data.get("event_type") in valid_types:
                scored.event_type = EventType(data["event_type"])
            if isinstance(data.get("sentiment"), (int, float)):
                scored.sentiment = max(-1.0, min(1.0, float(data["sentiment"])))
            if isinstance(data.get("impact_score"), (int, float)):
                scored.impact_score = max(1, min(100, int(data["impact_score"])))
            if data.get("direction") in ("BULLISH", "BEARISH", "NEUTRAL"):
                scored.direction = Direction(data["direction"])
            if data.get("brief"):
                scored.brief = str(data["brief"])
            if data.get("buy_signal") in ("BUY", "HOLD", "SELL"):
                scored.buy_signal = data["buy_signal"]
            if isinstance(data.get("buy_confidence"), (int, float)):
                scored.buy_confidence = max(0, min(100, int(data["buy_confidence"])))
            if isinstance(data.get("reasoning"), list):
                scored.reasoning = [str(r) for r in data["reasoning"][:3]]
            if data.get("risk"):
                scored.risk = str(data["risk"])
            if data.get("time_horizon"):
                scored.time_horizon = str(data["time_horizon"])
            if isinstance(data.get("correlated_moves"), list):
                validated = []
                for t in data["correlated_moves"][:6]:
                    t = str(t).upper()
                    if self._known_tickers and t not in self._known_tickers:
                        print(f"  [Claude] Rejected hallucinated ticker: {t}")
                        continue
                    validated.append(t)
                scored.correlated_moves = validated[:4]
            if isinstance(data.get("ticker_signals"), dict):
                ts = {}
                for t, v in data["ticker_signals"].items():
                    t = str(t).upper()
                    if self._known_tickers and t not in self._known_tickers:
                        print(f"  [Claude] Rejected hallucinated ticker signal: {t}")
                        continue
                    if isinstance(v, dict) and v.get("signal") in ("BUY", "SELL", "HOLD"):
                        ts[t] = {
                            "signal": v["signal"],
                            "confidence": max(1, min(100, int(v.get("confidence", scored.buy_confidence)))),
                        }
                if ts:
                    scored.ticker_signals = ts

        except Exception as e:
            print(f"  [Claude] Scoring error: {e}")

        # Fix "Missing Main Character": if entity extraction found no primary tickers
        # but Claude identified tickers in correlated_moves/ticker_signals, promote
        # the highest-confidence ticker to affected_tickers (primary).
        if not scored.affected_tickers and scored.correlated_moves:
            if scored.ticker_signals:
                # Sort by confidence descending, promote the top ticker
                ranked = sorted(
                    scored.ticker_signals.items(),
                    key=lambda x: x[1].get("confidence", 0),
                    reverse=True,
                )
                if ranked:
                    primary = ranked[0][0]
                    scored.affected_tickers = [primary]
                    # Remove from correlated_moves so it's not listed twice
                    scored.correlated_moves = [t for t in scored.correlated_moves if t != primary]
                    print(f"  [Fix] Promoted {primary} from correlated to primary ticker")
            elif scored.correlated_moves:
                # No ticker_signals, just promote the first correlated move
                primary = scored.correlated_moves[0]
                scored.affected_tickers = [primary]
                scored.correlated_moves = scored.correlated_moves[1:]
                print(f"  [Fix] Promoted {primary} from correlated to primary ticker (no signals)")

        return scored

    async def validate_buy(self, scored: ScoredEvent, corroborating: list[dict]) -> ScoredEvent:
        """Second Claude call to validate BUY signal using corroborating sources.
        Uses Haiku for this simple yes/no task — ~20x cheaper than Sonnet."""
        if not self.client or not corroborating:
            return scored
        headlines = "\n".join(f"- [{a['source']}] {a['headline']}" for a in corroborating[:3])
        prompt = f"""A financial screener flagged this as a BUY at {scored.buy_confidence}% confidence:

Primary article: {scored.headline}
Affected tickers: {', '.join(scored.affected_tickers) or 'MACRO'}

Other sources covering the same story:
{headlines}

Return ONLY JSON:
{{
  "adjusted_confidence": integer 1-100 (adjust up if sources confirm, down if they contradict or add risk),
  "validation_note": one sentence on what the other sources add or change
}}"""
        try:
            response = await asyncio.to_thread(
                self.client.messages.create,
                model="claude-haiku-4-5-20251001",  # Haiku: cheaper for simple validation
                max_tokens=120,
                messages=[{"role": "user", "content": prompt}]
            )
            # Track tokens
            self._total_calls += 1
            if hasattr(response, 'usage'):
                self._total_input_tokens += getattr(response.usage, 'input_tokens', 0)
                self._total_output_tokens += getattr(response.usage, 'output_tokens', 0)
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            if isinstance(data.get("adjusted_confidence"), (int, float)):
                scored.buy_confidence = max(1, min(100, int(data["adjusted_confidence"])))
            if data.get("validation_note"):
                scored.brief = (scored.brief + " | " + data["validation_note"]) if scored.brief else data["validation_note"]
        except Exception as e:
            print(f"  [Claude] Validation error: {e}")
        return scored


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK AVAILABILITY CHECKER
# ═══════════════════════════════════════════════════════════════════════════════

class StockAvailabilityChecker:
    """Checks live prices via yfinance and broker availability against real ticker lists."""

    # ── Revolut EU — ~2,200+ US stocks (sourced from community-maintained lists + official app)
    # Updated March 2025. Covers S&P 500, NASDAQ-100, and popular mid/small-caps.
    REVOLUT_TICKERS = {
        # Mega-cap & large-cap (S&P 500 core)
        "A", "AA", "AAL", "AAP", "AAPL", "ABBV", "ABEV", "ABNB", "ABT", "ACGL",
        "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE", "AEP", "AER", "AES",
        "AFL", "AG", "AGNC", "AI", "AIG", "AKAM", "AL", "ALB", "ALC", "ALGN",
        "ALL", "ALLE", "ALLY", "ALNY", "AMAT", "AMBA", "AMC", "AMCR", "AMD",
        "AME", "AMGN", "AMP", "AMT", "AMZN", "AN", "ANET", "ANSS", "AON", "AOS",
        "APA", "APD", "APH", "APO", "APPS", "APTV", "ARCC", "ARE", "ARES", "ARI",
        "ARMK", "ARR", "ASAN", "ASML", "ATUS", "AU", "AVGO", "AVB", "AVY", "AXP",
        "AXON", "AZN", "AZO",
        # B
        "BA", "BABA", "BAC", "BAH", "BAM", "BAP", "BAX", "BBAR", "BBD", "BBY",
        "BDX", "BE", "BEN", "BEPC", "BG", "BHC", "BHP", "BIDU", "BIIB", "BILI",
        "BIO", "BJ", "BK", "BKNG", "BKR", "BLK", "BLL", "BMA", "BMRN", "BMY",
        "BN", "BNTX", "BOX", "BP", "BPOP", "BR", "BRK.B", "BRO", "BROS", "BSX",
        "BTG", "BUD", "BVN", "BWA", "BX", "BYND",
        # C
        "C", "CABO", "CAG", "CAH", "CARR", "CARS", "CAT", "CB", "CBOE", "CBRE",
        "CC", "CCI", "CCK", "CCL", "CDNS", "CDW", "CE", "CEG", "CELH", "CF",
        "CFG", "CG", "CGNX", "CHGG", "CHD", "CHDN", "CHKP", "CHRD", "CHRW",
        "CHTR", "CHWY", "CI", "CIEN", "CINF", "CL", "CLF", "CLH", "CLX", "CMA",
        "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COHR", "COLB", "COLD",
        "COMM", "COP", "COST", "COTY", "CPB", "CPRI", "CPRT", "CPT", "CRM",
        "CROX", "CRSP", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTRA", "CTSH",
        "CTVA", "CVE", "CVNA", "CVS", "CVX", "CW", "CWEN", "CZR",
        # D
        "D", "DAL", "DAR", "DASH", "DBX", "DD", "DDOG", "DE", "DECK", "DELL",
        "DEO", "DFS", "DG", "DGX", "DHI", "DHR", "DIN", "DIS", "DISH", "DKNG",
        "DLR", "DLTR", "DOCU", "DOV", "DOW", "DPZ", "DRI", "DT", "DTE", "DUK",
        "DVA", "DVN", "DXC", "DXCM",
        # E
        "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "ELAN", "ELV", "EMR",
        "ENPH", "ENS", "EOG", "EPAM", "EQH", "EQIX", "EQNR", "EQR", "EQT",
        "ES", "ESS", "ESTC", "ETN", "ETR", "ETSY", "EW", "EWBC", "EXAS", "EXC",
        "EXEL", "EXPE", "EXR",
        # F
        "F", "FANG", "FAST", "FBIN", "FCX", "FDS", "FDX", "FE", "FERG", "FFIV",
        "FHN", "FICO", "FIS", "FISV", "FIX", "FL", "FLT", "FMC", "FND", "FNF",
        "FOXA", "FOX", "FROG", "FSLR", "FSLY", "FTNT", "FTV", "FUBO", "FUTU",
        "FVRR",
        # G
        "GD", "GDDY", "GDS", "GE", "GILD", "GIS", "GL", "GLOB", "GLW", "GM",
        "GME", "GMED", "GNRC", "GO", "GOLD", "GOOG", "GOOGL", "GPC", "GPN",
        "GRAB", "GRMN", "GS", "GSK", "GT", "GTLS", "GWW", "GXO",
        # H
        "H", "HAL", "HAS", "HBAN", "HBI", "HCA", "HD", "HDB", "HELE", "HES",
        "HIG", "HIMX", "HL", "HLF", "HLT", "HMC", "HOG", "HOLX", "HON", "HOOD",
        "HPE", "HPQ", "HRB", "HRL", "HSBC", "HSIC", "HST", "HSY", "HUM", "HUN",
        "HUYA", "HWM",
        # I
        "IAC", "IBM", "IBN", "ICE", "ICLR", "IDXX", "IEX", "IFF", "IGT", "IIPR",
        "ILMN", "IMGN", "INCY", "INFY", "INTC", "INTU", "INVH", "IP", "IPG",
        "IQ", "IR", "IRBT", "IRM", "ISRG", "IT", "ITW", "IVZ",
        # J
        "JBHT", "JBL", "JCI", "JD", "JEF", "JKS", "JLL", "JMIA", "JNJ", "JNPR",
        "JOBY", "JPM", "JWN",
        # K
        "K", "KDP", "KEP", "KEY", "KEYS", "KGC", "KHC", "KIM", "KKR", "KLAC",
        "KMB", "KMI", "KMX", "KNX", "KO", "KR", "KTOS", "KVUE", "KSS",
        # L
        "L", "LAD", "LAZR", "LCID", "LDOS", "LEA", "LEN", "LEVI", "LH", "LI",
        "LIN", "LKQ", "LLY", "LMND", "LMT", "LNG", "LNT", "LOGI", "LOMA",
        "LOPE", "LOW", "LRCX", "LSCC", "LULU", "LUV", "LVS", "LYB", "LYFT",
        "LYV",
        # M
        "M", "MA", "MAA", "MAN", "MANU", "MAR", "MARA", "MAS", "MAT", "MCD",
        "MCHP", "MCK", "MCO", "MDB", "MDLZ", "MDT", "MELI", "MET", "META",
        "MFC", "MFG", "MGM", "MKL", "MLCO", "MLM", "MMC", "MMM", "MNST", "MO",
        "MORN", "MOS", "MPC", "MPWR", "MPW", "MRK", "MRNA", "MRO", "MRVL", "MS",
        "MSCI", "MSFT", "MSGS", "MSI", "MSTR", "MT", "MTB", "MTCH", "MTD", "MTG",
        "MTH", "MTN", "MU", "MUFG", "MUR",
        # N
        "NAVI", "NBIX", "NCLH", "NCNO", "NDAQ", "NDSN", "NEE", "NEM", "NET",
        "NFLX", "NIO", "NKE", "NKLA", "NLY", "NMR", "NOC", "NOV", "NOW", "NRG",
        "NSC", "NTAP", "NTES", "NTNX", "NTRS", "NUE", "NVAX", "NVCR", "NVDA",
        "NVR", "NWL", "NWSA", "NYT",
        # O
        "O", "OC", "ODP", "OHI", "OKE", "OKTA", "OLED", "OLN", "OMC", "ON",
        "ONTO", "OPEN", "ORCL", "ORI", "ORLY", "OSK", "OTIS", "OVV", "OXY",
        # P
        "PAAS", "PANW", "PATH", "PAYC", "PAYX", "PBF", "PBR", "PCAR", "PCG",
        "PDD", "PEG", "PEGA", "PENN", "PEP", "PFE", "PFG", "PFGC", "PG", "PGR",
        "PH", "PHM", "PINS", "PKG", "PLD", "PLNT", "PLTR", "PLUG", "PM", "PNC",
        "PNR", "POOL", "POST", "PPG", "PPL", "PRI", "PRU", "PSA", "PSX", "PTON",
        "PVH", "PWR", "PYPL",
        # Q
        "QCOM", "QDEL", "QS", "QTWO",
        # R
        "RACE", "RBLX", "RCL", "RDDT", "REGN", "RF", "RH", "RHI", "RITM", "RIVN",
        "RJF", "RL", "RMD", "RNG", "ROK", "ROKU", "ROST", "RPM", "RS", "RSG",
        "RTX", "RUN", "RVMD", "RY",
        # S
        "SAIC", "SAM", "SBAC", "SBUX", "SCCO", "SCHW", "SE", "SEDG", "SFIX",
        "SFM", "SHAK", "SHOP", "SHW", "SID", "SIRI", "SJM", "SKX", "SLB", "SLM",
        "SMCI", "SNAP", "SNOW", "SNPS", "SO", "SONY", "SPCE", "SPG", "SPGI",
        "SPOT", "SQ", "SQM", "SRE", "SRPT", "SSNC", "STAG", "STLA", "STLD",
        "STNE", "STT", "STX", "STZ", "SU", "SUI", "SWK", "SWKS", "SYF", "SYK",
        "SYNA", "SYY",
        # T
        "T", "TAK", "TAL", "TAP", "TD", "TDOC", "TDY", "TEAM", "TECH", "TEL",
        "TENB", "TER", "TEVA", "TFX", "TGT", "THO", "TJX", "TME", "TMO", "TMUS",
        "TOL", "TPR", "TREE", "TRIP", "TRMB", "TROW", "TRV", "TSCO", "TSLA",
        "TSM", "TSN", "TT", "TTD", "TTE", "TTWO", "TWLO", "TXN", "TXRH", "TXT",
        "TYL",
        # U
        "U", "UAA", "UAL", "UBER", "UDR", "ULTA", "UNH", "UNP", "UPS", "URBN",
        "USB",
        # V
        "V", "VALE", "VEEV", "VFC", "VICI", "VIPS", "VLO", "VMC", "VNO", "VOD",
        "VRSK", "VRSN", "VRTX", "VTRS", "VTR", "VZ",
        # W
        "W", "WAB", "WAT", "WBA", "WBD", "WBS", "WDAY", "WDC", "WEC", "WELL",
        "WEN", "WERN", "WFC", "WHR", "WIX", "WKHS", "WLK", "WM", "WMB", "WMT",
        "WPC", "WRK", "WST", "WU", "WY", "WYNN",
        # X-Z
        "X", "XEL", "XOM", "XPEV", "XRX", "XYL", "YETI", "YPF", "YUM", "YUMC",
        "Z", "ZBH", "ZBRA", "ZI", "ZION", "ZM", "ZS", "ZTO", "ZTS",
    }

    # ── XTB — ~2,000+ US stock CFDs + real stocks (sourced from official equity-table.pdf)
    # Updated March 2025. Includes all S&P 500, NASDAQ-100, and broad mid-cap coverage.
    XTB_TICKERS = {
        # A
        "A", "AA", "AAL", "AAP", "AAPL", "ABBV", "ABG", "ABT", "ACGL", "ACHC",
        "ACHR", "ACI", "ACM", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "ADTN",
        "AEE", "AEP", "AER", "AES", "AFG", "AFL", "AFRM", "AGCO", "AGNC", "AGO",
        "AGR", "AI", "AIG", "AIN", "AIR", "AIT", "AIZ", "AJG", "AKAM", "AL",
        "ALB", "ALC", "ALGM", "ALGN", "ALGT", "ALK", "ALKS", "ALL", "ALLE",
        "ALLY", "ALNY", "AMAT", "AMBA", "AMC", "AMCR", "AMCX", "AMD", "AME",
        "AMED", "AMG", "AMGN", "AMP", "AMR", "AMT", "AMZN", "AN", "ANET", "ANSS",
        "AON", "AOS", "APA", "APD", "APH", "APLE", "APLS", "APO", "APPS", "APTV",
        "ARCC", "ARE", "ARES", "ARGX", "ARI", "ARMK", "ARR", "ARWR", "ASAN",
        "ASGN", "ASH", "ASML", "ATUS", "AU", "AUB", "AVGO", "AVB", "AVT", "AVY",
        "AXON", "AXP", "AXS", "AZUL",
        # B
        "BA", "BABA", "BAC", "BAH", "BAK", "BALL", "BAM", "BAND", "BAP", "BAX",
        "BBAR", "BBD", "BBY", "BC", "BDX", "BE", "BEAM", "BEN", "BEPC", "BG",
        "BHC", "BHP", "BIDU", "BIIB", "BILI", "BIO", "BJ", "BK", "BKNG", "BKR",
        "BL", "BLDR", "BLK", "BLL", "BMA", "BMBL", "BMO", "BMRN", "BMY", "BN",
        "BNTX", "BOX", "BP", "BPOP", "BR", "BRBR", "BRK.B", "BRO", "BROS",
        "BSAC", "BSX", "BTG", "BUD", "BVN", "BWA", "BX", "BYND", "BZ",
        # C
        "C", "CABO", "CACC", "CACI", "CADE", "CAG", "CAH", "CAKE", "CALM", "CAR",
        "CARG", "CARR", "CARS", "CAT", "CB", "CBOE", "CBRE", "CBRL", "CC", "CCI",
        "CCK", "CCL", "CCU", "CDNS", "CDW", "CE", "CEG", "CELH", "CF", "CFG",
        "CG", "CGNX", "CHGG", "CHD", "CHDN", "CHEF", "CHKP", "CHRD", "CHRW",
        "CHTR", "CHWY", "CI", "CIB", "CIEN", "CINF", "CL", "CLF", "CLH", "CLX",
        "CM", "CMA", "CMC", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNK",
        "CNO", "CNP", "COF", "COHR", "COHU", "COKE", "COLB", "COLM", "COMM", "COO", "COP",
        "COST", "COTY", "CPB", "CPRI", "CPRT", "CPT", "CRI", "CRK", "CRL", "CRM",
        "CROX", "CRS", "CSCO", "CSIQ", "CSL", "CSX", "CTAS", "CTRA", "CTRE",
        "CTSH", "CTVA", "CVE", "CVS", "CVX", "CW", "CWEN", "CZR",
        # D
        "D", "DAL", "DAR", "DASH", "DBX", "DD", "DDOG", "DE", "DECK", "DELL",
        "DEO", "DFS", "DG", "DGX", "DHI", "DHR", "DIN", "DINO", "DIS", "DISH",
        "DKS", "DLB", "DLR", "DLTR", "DOCS", "DOCU", "DOV", "DOW", "DPZ", "DRI",
        "DT", "DTE", "DUK", "DVA", "DVN", "DXC", "DXCM",
        # E
        "EA", "EAT", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "ELAN", "ELV",
        "EME", "EMN", "EMR", "ENB", "ENPH", "ENR", "ENS", "EOG", "EPAM", "EPC",
        "EPR", "EQH", "EQIX", "EQR", "EQT", "ES", "ESS", "ESTC", "ETN", "ETR",
        "ETSY", "EVH", "EW", "EWBC", "EXAS", "EXC", "EXEL", "EXLS", "EXP",
        "EXPD", "EXPE", "EXPO",
        # F
        "F", "FAF", "FANG", "FAST", "FATE", "FBIN", "FCNCA", "FDS", "FDX", "FE",
        "FERG", "FFIV", "FHN", "FICO", "FIS", "FISV", "FIX", "FIZZ", "FL", "FLO",
        "FLS", "FLT", "FMC", "FMS", "FN", "FND", "FNF", "FOX", "FOXA", "FROG",
        "FRPT", "FRT", "FSLY", "FSR", "FTI", "FTNT", "FTS", "FTV", "FUBO", "FUL",
        "FUTU", "FVRR",
        # G
        "GD", "GDDY", "GDS", "GE", "GEL", "GEN", "GFL", "GHC", "GILD", "GIS",
        "GL", "GLOB", "GLW", "GM", "GME", "GMED", "GMS", "GNRC", "GO", "GOGO",
        "GOLD", "GOOG", "GOOGL", "GOOS", "GPC", "GPI", "GPN", "GRAB", "GRBK",
        "GRFS", "GRMN", "GS", "GSK", "GTLS", "GTN", "GWW", "GXO",
        # H
        "H", "HAIN", "HALO", "HAS", "HBI", "HCA", "HD", "HDB", "HELE", "HES",
        "HIG", "HIMX", "HL", "HLF", "HLT", "HMC", "HOG", "HOLX", "HON", "HOOD",
        "HPE", "HPQ", "HRB", "HRL", "HSBC", "HSIC", "HST", "HSY", "HUM", "HUN",
        "HUYA", "HWM",
        # I
        "IAC", "IART", "IBM", "IBN", "ICE", "ICLR", "IDCC", "IDXX", "IEX", "IFF",
        "IGT", "IIPR", "ILMN", "IMAX", "IMGN", "INCY", "INFY", "INSP", "INTC",
        "INTU", "INVH", "IONS", "IPAR", "IPG", "IQ", "IR", "IRBT", "IRM", "IRTC",
        "ISRG", "IT", "ITW", "IVZ",
        # J
        "J", "JACK", "JBHT", "JBL", "JCI", "JD", "JEF", "JKS", "JLL", "JMIA",
        "JNJ", "JNPR", "JOBY", "JPM", "JWN",
        # K
        "K", "KBR", "KDP", "KEP", "KEY", "KEYS", "KEX", "KGC", "KHC", "KIM",
        "KKR", "KLAC", "KMB", "KMI", "KMX", "KNX", "KO", "KR", "KRYS", "KSS",
        "KTOS", "KVUE",
        # L
        "L", "LAD", "LAMR", "LAZR", "LCID", "LDOS", "LEA", "LECO", "LEG", "LEN",
        "LEVI", "LH", "LI", "LIN", "LKQ", "LLY", "LMND", "LMT", "LNC", "LNG",
        "LNT", "LOGI", "LOMA", "LOPE", "LOW", "LRCX", "LRN", "LSCC", "LULU",
        "LUV", "LVS", "LYB", "LYFT", "LYV",
        # M
        "M", "MA", "MAA", "MAN", "MANH", "MANU", "MAR", "MARA", "MAS", "MASI",
        "MAT", "MATX", "MAXN", "MBT", "MCD", "MCHP", "MCK", "MCO", "MDB", "MDLZ",
        "MDT", "MDU", "MELI", "MET", "META", "MFC", "MFG", "MGM", "MHK", "MKL",
        "MLCO", "MLM", "MMC", "MMM", "MNST", "MO", "MOD", "MORN", "MOS", "MPC",
        "MPWR", "MPW", "MRK", "MRNA", "MRO", "MRVL", "MS", "MSCI", "MSFT",
        "MSGS", "MSI", "MSTR", "MT", "MTB", "MTCH", "MTD", "MTG", "MTH", "MTN",
        "MU", "MUFG", "MUR",
        # N
        "NAVI", "NBIX", "NCLH", "NCNO", "NCR", "NDAQ", "NDSN", "NE", "NEE", "NEM",
        "NET", "NFLX", "NFG", "NIO", "NKE", "NKLA", "NLY", "NMR", "NOC", "NOV",
        "NOW", "NRG", "NSC", "NSIT", "NTAP", "NTCT", "NTES", "NTNX", "NTRS",
        "NUE", "NVAX", "NVCR", "NVDA", "NVR", "NWL", "NWSA", "NXST", "NYT",
        # O
        "O", "OBDC", "OC", "OGN", "OHI", "OKE", "OKTA", "OLED", "OLN", "OLPX",
        "OMC", "ON", "ONTO", "OPEN", "ORCL", "ORI", "ORLY", "OSK", "OTIS", "OUST",
        "OVV", "OXY",
        # P
        "PAAS", "PACB", "PANW", "PATH", "PAYC", "PAYX", "PB", "PBF", "PBR",
        "PCAR", "PCG", "PDD", "PEG", "PEGA", "PENN", "PEP", "PFE", "PFG", "PFGC",
        "PG", "PGR", "PH", "PHM", "PINS", "PKG", "PKX", "PLD", "PLMR", "PLNT",
        "PLTR", "PLUG", "PLUS", "PM", "PMT", "PNC", "PNFP", "POOL", "POR", "POST",
        "PPC", "PPG", "PPL", "PRI", "PRU", "PSA", "PSX", "PTON", "PVH", "PWR",
        "PYPL",
        # Q
        "QCOM", "QDEL", "QS", "QTWO",
        # R
        "R", "RACE", "RARE", "RBLX", "RCL", "RDDT", "RDY", "RE", "REG", "REGN",
        "REVG", "RF", "RGEN", "RGLD", "RH", "RHI", "RICK", "RITM", "RIVN", "RJF",
        "RL", "RMBS", "RMD", "RNG", "RNR", "ROK", "ROKU", "ROST", "RPM", "RS",
        "RSG", "RTX", "RUN", "RVMD", "RY",
        # S
        "S", "SAIC", "SAM", "SBAC", "SBUX", "SCCO", "SCHW", "SE", "SEDG", "SFIX",
        "SFM", "SHAK", "SHOP", "SHW", "SID", "SIGA", "SJM", "SKM", "SLB", "SLGN",
        "SLM", "SMCI", "SMG", "SNAP", "SNOW", "SNPS", "SO", "SONO", "SONY",
        "SPCE", "SPG", "SPGI", "SPOT", "SPR", "SQ", "SQM", "SRE", "SRPT", "SSB",
        "SSNC", "ST", "STAG", "STLA", "STLD", "STNE", "STT", "STX", "STZ", "SUI",
        "SWK", "SWKS", "SYF", "SYK", "SYNA", "SYY",
        # T
        "T", "TAK", "TAL", "TAP", "TD", "TDOC", "TDY", "TEAM", "TECH", "TEL",
        "TENB", "TER", "TEVA", "TFX", "TGT", "THG", "THO", "THS", "TJX", "TME",
        "TMO", "TMUS", "TOL", "TPR", "TREE", "TRIP", "TRMB", "TROW", "TRV",
        "TSCO", "TSLA", "TSM", "TSN", "TSEM", "TT", "TTD", "TTE", "TTWO", "TWLO",
        "TX", "TXN", "TXRH", "TXT", "TYL",
        # U
        "U", "UAA", "UAL", "UBER", "UDR", "UHS", "UL", "ULTA", "UNH", "UNP",
        "UPS", "URBN", "USB",
        # V
        "V", "VAC", "VCEL", "VEEV", "VICI", "VICR", "VIPS", "VLO", "VMC", "VNO",
        "VOD", "VRSK", "VRSN", "VRTX", "VTRS", "VTR", "VZ",
        # W
        "W", "WAB", "WAFD", "WAT", "WBA", "WBD", "WBS", "WCN", "WDAY", "WDC",
        "WEC", "WELL", "WEN", "WERN", "WFC", "WFRD", "WGO", "WHR", "WIX", "WKHS",
        "WLK", "WM", "WMB", "WMG", "WMT", "WPC", "WRB", "WRK", "WST", "WU",
        "WY", "WYNN",
        # X-Z
        "X", "XEL", "XOM", "XPEL", "XPEV", "XRAY", "XRX", "XYL", "YETI", "YPF",
        "YUM", "YUMC", "Z", "ZBRA", "ZBH", "ZI", "ZION", "ZM", "ZS", "ZTO", "ZTS",
    }

    PRICE_TTL = 300  # seconds — re-fetch after 5 minutes
    _cache: dict = {}  # ticker -> {"data": {...}, "ts": float}

    def _is_fresh(self, ticker: str) -> bool:
        entry = self._cache.get(ticker)
        return entry is not None and (time.time() - entry["ts"]) < self.PRICE_TTL

    @staticmethod
    def _yf_symbol(ticker: str) -> str:
        """Convert ticker to yfinance format. e.g. BRK.B → BRK-B"""
        return ticker.replace(".", "-")

    async def check_tickers(self, tickers: list[str]) -> dict:
        import yfinance as yf

        def _fetch_one(ticker: str) -> tuple[str, dict]:
            try:
                info = yf.Ticker(self._yf_symbol(ticker)).fast_info
                exchange = getattr(info, 'exchange', '') or ''
                last_price = getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previous_close', None)
                if last_price and prev_close and prev_close != 0:
                    pct_change = round((last_price - prev_close) / prev_close * 100, 2)
                else:
                    pct_change = None
                result = {
                    "exchange": exchange,
                    "revolut": ticker in StockAvailabilityChecker.REVOLUT_TICKERS,
                    "xtb": ticker in StockAvailabilityChecker.XTB_TICKERS,
                    "price": round(last_price, 2) if last_price else None,
                    "change_pct": pct_change,
                }
            except Exception:
                result = {
                    "exchange": "unknown",
                    "revolut": ticker in StockAvailabilityChecker.REVOLUT_TICKERS,
                    "xtb": ticker in StockAvailabilityChecker.XTB_TICKERS,
                    "price": None,
                    "change_pct": None,
                }
            return ticker, result

        results = {t: self._cache[t]["data"] for t in tickers if self._is_fresh(t)}
        uncached = [t for t in tickers if not self._is_fresh(t)]
        if uncached:
            fetched = await asyncio.gather(*[asyncio.to_thread(_fetch_one, t) for t in uncached])
            for ticker, result in fetched:
                self._cache[ticker] = {"data": result, "ts": time.time()}
                results[ticker] = result
        return results


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
# SIGNAL OUTCOME TRACKER — Measures whether BUY/SELL signals were correct
# ═══════════════════════════════════════════════════════════════════════════════

class SignalOutcomeTracker:
    """
    Tracks BUY/SELL signal outcomes by checking prices at +1h, +4h, +1d, +1w.
    - A BUY signal is a WIN if the price went up by the checkpoint.
    - A SELL signal is a WIN if the price went down.
    - Runs as a background task, checking pending signals every 5 minutes.
    """

    # Checkpoint offsets in seconds
    CHECKPOINTS = {
        "1h":  3600,
        "4h":  14400,
        "1d":  86400,
        "1w":  604800,
    }

    def __init__(self, db: "EventDatabase"):
        self.db = db
        self._running = False

    def record_signal(self, event_id: str, ticker: str, signal: str,
                      confidence: int, entry_price: float):
        """Called when a new BUY or SELL signal is generated."""
        if signal not in ("BUY", "SELL") or not entry_price:
            return
        self.db.insert_signal(event_id, ticker, signal, confidence,
                              entry_price, time.time())
        print(f"  [Tracker] Recording {signal} signal for ${ticker} @ ${entry_price:.2f} ({confidence}%)")

    async def check_pending(self):
        """Check all pending signals and update any due checkpoints."""
        import yfinance as yf

        pending = self.db.get_pending_signals()
        if not pending:
            return

        # Group by ticker to minimize API calls
        tickers_needed = set()
        now = time.time()
        for sig in pending:
            elapsed = now - sig["entry_time"]
            for cp, offset in self.CHECKPOINTS.items():
                price_field = f"price_{cp}"
                if sig.get(price_field) is None and elapsed >= offset:
                    tickers_needed.add(sig["ticker"])
                    break

        if not tickers_needed:
            return

        # Batch fetch current prices
        prices = {}

        def _fetch_prices():
            for t in tickers_needed:
                try:
                    info = yf.Ticker(StockAvailabilityChecker._yf_symbol(t)).fast_info
                    p = getattr(info, "last_price", None)
                    if p:
                        prices[t] = round(p, 2)
                except Exception:
                    pass

        await asyncio.to_thread(_fetch_prices)

        # Update checkpoints
        updates = 0
        for sig in pending:
            ticker = sig["ticker"]
            if ticker not in prices:
                continue
            current_price = prices[ticker]
            entry_price = sig["entry_price"]
            elapsed = now - sig["entry_time"]

            for cp, offset in self.CHECKPOINTS.items():
                price_field = f"price_{cp}"
                if sig.get(price_field) is not None:
                    continue  # Already filled
                if elapsed < offset:
                    continue  # Not due yet

                pct = round((current_price - entry_price) / entry_price * 100, 2)

                # WIN: BUY + price up, or SELL + price down
                if sig["signal"] == "BUY":
                    outcome = "WIN" if pct > 0 else "LOSS" if pct < 0 else "FLAT"
                else:  # SELL
                    outcome = "WIN" if pct < 0 else "LOSS" if pct > 0 else "FLAT"

                self.db.update_signal_checkpoint(
                    sig["event_id"], ticker, cp, current_price, pct, outcome
                )
                updates += 1
                print(f"  [Tracker] {sig['signal']} ${ticker} @ +{cp}: "
                      f"${entry_price:.2f} → ${current_price:.2f} ({pct:+.2f}%) = {outcome}")

        if updates:
            # Broadcast updated stats to dashboard
            await self._broadcast_stats()

    async def handle_track_request(self, msg: dict):
        """Handle a user-initiated track request from the dashboard."""
        import yfinance as yf

        event_id = msg.get("event_id")
        ticker = msg.get("ticker")
        signal = msg.get("signal")  # BUY or SELL
        confidence = msg.get("confidence", 0)

        if not event_id or not ticker or signal not in ("BUY", "SELL"):
            return

        # Fetch current price as entry point
        def _get_price():
            try:
                info = yf.Ticker(StockAvailabilityChecker._yf_symbol(ticker)).fast_info
                return getattr(info, "last_price", None)
            except Exception:
                return None

        price = await asyncio.to_thread(_get_price)
        if not price:
            print(f"  [Tracker] Could not fetch price for ${ticker}, skipping track")
            return

        self.record_signal(event_id, ticker, signal, confidence, round(price, 2))
        await _broadcast_signal_performance()

    async def _broadcast_stats(self):
        """Send signal performance stats to all WS clients."""
        await _broadcast_signal_performance()

    async def run_loop(self):
        """Background loop — checks pending signals every 5 minutes."""
        self._running = True
        print("  [Tracker] Signal outcome tracker started (checking every 5 min)")
        while self._running:
            try:
                await self.check_pending()
            except Exception as e:
                print(f"  [Tracker] Error checking signals: {e}")
            await asyncio.sleep(300)  # 5 minutes


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
# SECTION 2: NYSE REFERENCE DATA — 300+ TICKERS, 20 SECTORS
# ═══════════════════════════════════════════════════════════════════════════════

class NYSEReferenceDB:
    """
    Comprehensive in-memory ticker resolution database.
    Covers: Semiconductors, Mega-cap Tech, Cloud/SaaS, Cybersecurity, Crypto,
    Energy (upstream/midstream/downstream/refining), Financials, Fintech,
    Healthcare/Pharma/Biotech, Defense/Aerospace, Industrials, Autos/EVs,
    Consumer, Airlines, Utilities, REITs, Materials, Transportation, Telecom,
    and Broad Market ETFs.

    Production version uses SQLite FTS5 for fuzzy matching + Redis hot cache.
    """

    def __init__(self):
        self.tickers: dict[str, dict] = {
            # ── SEMICONDUCTORS ──────────────────────────────────────────────
            "NVDA": {"name": "NVIDIA", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "GPU/AI Chips", "beta_30d": 1.8},
            "AMD":  {"name": "Advanced Micro Devices", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "GPU/CPU", "beta_30d": 1.7},
            "INTC": {"name": "Intel", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "CPU/Foundry", "beta_30d": 1.3},
            "TSM":  {"name": "Taiwan Semiconductor", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Foundry", "beta_30d": 1.4},
            "AVGO": {"name": "Broadcom", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Networking/Custom", "beta_30d": 1.3},
            "QCOM": {"name": "Qualcomm", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Mobile/RF", "beta_30d": 1.4},
            "ASML": {"name": "ASML Holding", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Lithography Equipment", "beta_30d": 1.5},
            "MU":   {"name": "Micron Technology", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Memory", "beta_30d": 1.6},
            "LRCX": {"name": "Lam Research", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Equipment", "beta_30d": 1.5},
            "AMAT": {"name": "Applied Materials", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Equipment", "beta_30d": 1.4},
            "TXN":  {"name": "Texas Instruments", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Analog", "beta_30d": 1.1},
            "ARM":  {"name": "Arm Holdings", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "IP/Architecture", "beta_30d": 1.9},
            "MRVL": {"name": "Marvell Technology", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Data Infrastructure", "beta_30d": 1.6},

            # ── ENERGY — Upstream (E&P) ────────────────────────────────────
            "XOM":  {"name": "Exxon Mobil", "sector": "Energy", "mcap": "mega", "etf": "XLE",
                     "sub_sector": "Integrated", "beta_30d": 0.9},
            "CVX":  {"name": "Chevron", "sector": "Energy", "mcap": "mega", "etf": "XLE",
                     "sub_sector": "Integrated", "beta_30d": 0.9},
            "COP":  {"name": "ConocoPhillips", "sector": "Energy", "mcap": "large", "etf": "XLE",
                     "sub_sector": "E&P", "beta_30d": 1.1},
            "EOG":  {"name": "EOG Resources", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.2},
            "PXD":  {"name": "Pioneer Natural Resources", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P Permian", "beta_30d": 1.3},
            "OXY":  {"name": "Occidental Petroleum", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.5},
            # ── Energy — Midstream ─────────────────────────────────────────
            "WMB":  {"name": "Williams Companies", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.8},
            "KMI":  {"name": "Kinder Morgan", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.7},
            "ET":   {"name": "Energy Transfer", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.9},
            # ── Energy — Services ──────────────────────────────────────────
            "SLB":  {"name": "Schlumberger", "sector": "Energy", "mcap": "large", "etf": "OIH",
                     "sub_sector": "Oilfield Services", "beta_30d": 1.3},
            "HAL":  {"name": "Halliburton", "sector": "Energy", "mcap": "large", "etf": "OIH",
                     "sub_sector": "Oilfield Services", "beta_30d": 1.4},
            # ── Energy — Renewables ────────────────────────────────────────
            "NEE":  {"name": "NextEra Energy", "sector": "Utilities", "mcap": "mega", "etf": "XLU",
                     "sub_sector": "Renewable Utilities", "beta_30d": 0.7},
            "ENPH": {"name": "Enphase Energy", "sector": "Energy", "mcap": "mid", "etf": "TAN",
                     "sub_sector": "Solar", "beta_30d": 2.0},
            "FSLR": {"name": "First Solar", "sector": "Energy", "mcap": "mid", "etf": "TAN",
                     "sub_sector": "Solar", "beta_30d": 1.8},

            # ── FINANCIALS ─────────────────────────────────────────────────
            "JPM":  {"name": "JPMorgan Chase", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.1},
            "GS":   {"name": "Goldman Sachs", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Investment Banking", "beta_30d": 1.3},
            "BAC":  {"name": "Bank of America", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.2},
            "MS":   {"name": "Morgan Stanley", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Investment Banking", "beta_30d": 1.3},
            "C":    {"name": "Citigroup", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.3},
            "WFC":  {"name": "Wells Fargo", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.1},
            "BRK.B": {"name": "Berkshire Hathaway", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                      "sub_sector": "Diversified", "beta_30d": 0.6},
            "V":    {"name": "Visa", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Payments", "beta_30d": 0.9},
            "MA":   {"name": "Mastercard", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Payments", "beta_30d": 0.9},
            "BLK":  {"name": "BlackRock", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Asset Management", "beta_30d": 1.1},

            # ── HEALTHCARE / PHARMA / BIOTECH ──────────────────────────────
            "JNJ":  {"name": "Johnson & Johnson", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Diversified Pharma", "beta_30d": 0.6},
            "PFE":  {"name": "Pfizer", "sector": "Healthcare", "mcap": "large", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.7},
            "UNH":  {"name": "UnitedHealth Group", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Managed Care", "beta_30d": 0.8},
            "LLY":  {"name": "Eli Lilly", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.9},
            "ABBV": {"name": "AbbVie", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.7},
            "MRK":  {"name": "Merck", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.6},
            "TMO":  {"name": "Thermo Fisher", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Life Sciences Tools", "beta_30d": 0.9},
            "AMGN": {"name": "Amgen", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.7},
            "GILD": {"name": "Gilead Sciences", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.6},

            # ── DEFENSE / AEROSPACE ────────────────────────────────────────
            "LMT":  {"name": "Lockheed Martin", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Prime", "beta_30d": 0.7},
            "RTX":  {"name": "RTX (Raytheon)", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense/Aero", "beta_30d": 0.8},
            "NOC":  {"name": "Northrop Grumman", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Prime", "beta_30d": 0.6},
            "GD":   {"name": "General Dynamics", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Diversified", "beta_30d": 0.7},
            "BA":   {"name": "Boeing", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Commercial Aero/Defense", "beta_30d": 1.4},

            # ── TECHNOLOGY ─────────────────────────────────────────────────
            "IBM":  {"name": "IBM", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Enterprise IT", "beta_30d": 0.9},
            "CRM":  {"name": "Salesforce", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Cloud/SaaS", "beta_30d": 1.2},
            "ORCL": {"name": "Oracle", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Cloud/Enterprise", "beta_30d": 1.1},
            "NOW":  {"name": "ServiceNow", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Cloud/SaaS", "beta_30d": 1.2},
            "PLTR": {"name": "Palantir", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "AI/Data Analytics", "beta_30d": 2.1},

            # ── INDUSTRIALS ────────────────────────────────────────────────
            "CAT":  {"name": "Caterpillar", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Heavy Equipment", "beta_30d": 1.1},
            "DE":   {"name": "Deere & Company", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Agriculture Equipment", "beta_30d": 1.0},
            "GE":   {"name": "GE Aerospace", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Jet Engines/Power", "beta_30d": 1.1},
            "HON":  {"name": "Honeywell", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Diversified Industrial", "beta_30d": 0.9},
            "UNP":  {"name": "Union Pacific", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Railroads", "beta_30d": 0.9},
            "UPS":  {"name": "United Parcel Service", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Logistics", "beta_30d": 1.0},
            "FDX":  {"name": "FedEx", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Logistics", "beta_30d": 1.2},

            # ── CONSUMER STAPLES ───────────────────────────────────────────
            "WMT":  {"name": "Walmart", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Big Box Retail", "beta_30d": 0.5},
            "KO":   {"name": "Coca-Cola", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Beverages", "beta_30d": 0.5},
            "PEP":  {"name": "PepsiCo", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Beverages/Snacks", "beta_30d": 0.5},
            "PG":   {"name": "Procter & Gamble", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Household Products", "beta_30d": 0.4},
            "COST": {"name": "Costco", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Warehouse Retail", "beta_30d": 0.7},

            # ── CONSUMER DISCRETIONARY ─────────────────────────────────────
            "NKE":  {"name": "Nike", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Apparel/Footwear", "beta_30d": 1.1},
            "HD":   {"name": "Home Depot", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "Home Improvement", "beta_30d": 1.0},
            "MCD":  {"name": "McDonald's", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "QSR", "beta_30d": 0.6},
            "SBUX": {"name": "Starbucks", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "QSR/Coffee", "beta_30d": 0.9},
            # ── Consumer Disc. — Specialty Retail / Beauty ────────────────
            "ULTA": {"name": "Ulta Beauty", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Specialty Beauty Retail", "beta_30d": 1.3},
            "ELF":  {"name": "e.l.f. Beauty", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "Specialty Beauty", "beta_30d": 1.8},
            "COTY": {"name": "Coty", "sector": "Consumer Staples", "mcap": "mid", "etf": "XLP",
                     "sub_sector": "Beauty/Personal Care", "beta_30d": 1.4},
            "EL":   {"name": "Estée Lauder", "sector": "Consumer Staples", "mcap": "large", "etf": "XLP",
                     "sub_sector": "Beauty/Personal Care", "beta_30d": 1.2},
            "TGT":  {"name": "Target", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Big Box Retail", "beta_30d": 1.0},
            "LOW":  {"name": "Lowe's", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Home Improvement", "beta_30d": 1.0},
            "TJX":  {"name": "TJX Companies", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Off-Price Retail", "beta_30d": 0.9},
            "ROST": {"name": "Ross Stores", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Off-Price Retail", "beta_30d": 0.9},
            "DG":   {"name": "Dollar General", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Discount Retail", "beta_30d": 0.8},
            "DLTR": {"name": "Dollar Tree", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "Discount Retail", "beta_30d": 1.0},
            "DIS":  {"name": "Walt Disney", "sector": "Communication", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Media/Entertainment", "beta_30d": 1.1},

            # ── UTILITIES ──────────────────────────────────────────────────
            "DUK":  {"name": "Duke Energy", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.4},
            "SO":   {"name": "Southern Company", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.4},
            "AEP":  {"name": "American Electric Power", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.5},
            "VST":  {"name": "Vistra", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Power Generation/Nuclear", "beta_30d": 1.6},

            # ── REITs ──────────────────────────────────────────────────────
            "AMT":  {"name": "American Tower", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Cell Tower REITs", "beta_30d": 0.8},
            "PLD":  {"name": "Prologis", "sector": "REITs", "mcap": "mega", "etf": "VNQ",
                     "sub_sector": "Industrial/Logistics REITs", "beta_30d": 0.9},
            "EQIX": {"name": "Equinix", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Data Center REITs", "beta_30d": 0.9},
            "SPG":  {"name": "Simon Property Group", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Retail REITs", "beta_30d": 1.2},

            # ── MATERIALS / MINING ─────────────────────────────────────────
            "FCX":  {"name": "Freeport-McMoRan", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Copper/Gold Mining", "beta_30d": 1.5},
            "NEM":  {"name": "Newmont Mining", "sector": "Materials", "mcap": "large", "etf": "GDX",
                     "sub_sector": "Gold Mining", "beta_30d": 0.5},
            "NUE":  {"name": "Nucor", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Steel", "beta_30d": 1.3},
            "APD":  {"name": "Air Products", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Industrial Gases", "beta_30d": 0.8},
            "LIN":  {"name": "Linde", "sector": "Materials", "mcap": "mega", "etf": "XLB",
                     "sub_sector": "Industrial Gases", "beta_30d": 0.7},

            # ── TELECOM ────────────────────────────────────────────────────
            "T":    {"name": "AT&T", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.7},
            "VZ":   {"name": "Verizon", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.6},
            "TMUS": {"name": "T-Mobile", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.7},

            # ── MEGA-CAP TECH (Big 7) ───────────────────────────────────────
            "AAPL": {"name": "Apple", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Consumer Electronics/Software", "beta_30d": 1.2},
            "MSFT": {"name": "Microsoft", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Cloud/Enterprise Software", "beta_30d": 1.1},
            "GOOGL": {"name": "Alphabet", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Search/Cloud/AI", "beta_30d": 1.2},
            "GOOG":  {"name": "Alphabet (Class C)", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Search/Cloud/AI", "beta_30d": 1.2},
            "META":  {"name": "Meta Platforms", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Social Media/AI", "beta_30d": 1.4},
            "AMZN": {"name": "Amazon", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "E-Commerce/Cloud", "beta_30d": 1.3},
            "NFLX": {"name": "Netflix", "sector": "Communication", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Streaming", "beta_30d": 1.5},
            "TSLA": {"name": "Tesla", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "EV/Autonomous", "beta_30d": 2.0},

            # ── MORE TECHNOLOGY / SOFTWARE ──────────────────────────────────
            "ADBE": {"name": "Adobe", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Creative/AI Software", "beta_30d": 1.3},
            "INTU": {"name": "Intuit", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Financial Software", "beta_30d": 1.2},
            "SNPS": {"name": "Synopsys", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "EDA Software", "beta_30d": 1.3},
            "CDNS": {"name": "Cadence Design", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "EDA Software", "beta_30d": 1.3},
            "WDAY": {"name": "Workday", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/HR Software", "beta_30d": 1.2},
            "TEAM": {"name": "Atlassian", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/Dev Tools", "beta_30d": 1.4},
            "HUBS": {"name": "HubSpot", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/CRM", "beta_30d": 1.3},
            "UBER": {"name": "Uber", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Ride-Sharing/Logistics", "beta_30d": 1.5},
            "SMCI": {"name": "Super Micro Computer", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "AI Servers", "beta_30d": 2.5},
            "SHOP": {"name": "Shopify", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "E-Commerce Platform", "beta_30d": 1.8},

            # ── CYBERSECURITY ───────────────────────────────────────────────
            "PANW": {"name": "Palo Alto Networks", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity", "beta_30d": 1.4},
            "CRWD": {"name": "CrowdStrike", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/EDR", "beta_30d": 1.6},
            "FTNT": {"name": "Fortinet", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/Firewall", "beta_30d": 1.3},
            "ZS":   {"name": "Zscaler", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cloud Security", "beta_30d": 1.6},
            "S":    {"name": "SentinelOne", "sector": "Technology", "mcap": "mid", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/AI", "beta_30d": 1.8},

            # ── CLOUD / DATA ────────────────────────────────────────────────
            "SNOW": {"name": "Snowflake", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Data Platform", "beta_30d": 1.7},
            "DDOG": {"name": "Datadog", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Monitoring", "beta_30d": 1.6},
            "NET":  {"name": "Cloudflare", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Networking/Security", "beta_30d": 1.7},
            "MDB":  {"name": "MongoDB", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Database", "beta_30d": 1.8},
            "RBLX": {"name": "Roblox", "sector": "Technology", "mcap": "mid", "etf": "WCLD",
                     "sub_sector": "Gaming/Metaverse", "beta_30d": 1.9},
            "SNAP": {"name": "Snap", "sector": "Communication", "mcap": "mid", "etf": "XLC",
                     "sub_sector": "Social Media", "beta_30d": 2.2},
            "ROKU": {"name": "Roku", "sector": "Communication", "mcap": "mid", "etf": "XLC",
                     "sub_sector": "Streaming Platform", "beta_30d": 2.0},

            # ── CRYPTO-ADJACENT ─────────────────────────────────────────────
            "COIN": {"name": "Coinbase", "sector": "Financials", "mcap": "large", "etf": "BKCH",
                     "sub_sector": "Crypto Exchange", "beta_30d": 3.0},
            "MSTR": {"name": "MicroStrategy", "sector": "Technology", "mcap": "large", "etf": "BKCH",
                     "sub_sector": "Bitcoin Treasury", "beta_30d": 3.5},
            "RIOT": {"name": "Riot Platforms", "sector": "Technology", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Bitcoin Mining", "beta_30d": 3.2},
            "MARA": {"name": "Marathon Digital", "sector": "Technology", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Bitcoin Mining", "beta_30d": 3.3},
            "HOOD": {"name": "Robinhood", "sector": "Financials", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Retail Brokerage/Crypto", "beta_30d": 2.5},

            # ── FINTECH ─────────────────────────────────────────────────────
            "PYPL": {"name": "PayPal", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Digital Payments", "beta_30d": 1.4},
            "SQ":   {"name": "Block (Square)", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Fintech/Payments", "beta_30d": 1.8},
            "SOFI": {"name": "SoFi Technologies", "sector": "Financials", "mcap": "mid", "etf": "XLF",
                     "sub_sector": "Digital Banking", "beta_30d": 2.0},
            "SCHW": {"name": "Charles Schwab", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Retail Brokerage", "beta_30d": 1.2},
            "AFRM": {"name": "Affirm", "sector": "Financials", "mcap": "mid", "etf": "XLF",
                     "sub_sector": "BNPL/Fintech", "beta_30d": 2.3},
            "DASH": {"name": "DoorDash", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Food Delivery", "beta_30d": 1.7},
            "LYFT": {"name": "Lyft", "sector": "Technology", "mcap": "mid", "etf": "XLK",
                     "sub_sector": "Ride-Sharing", "beta_30d": 2.0},

            # ── BIOTECH / PHARMA (additional) ───────────────────────────────
            "MRNA": {"name": "Moderna", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "mRNA Biotech", "beta_30d": 1.8},
            "BNTX": {"name": "BioNTech", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "mRNA Biotech", "beta_30d": 1.7},
            "REGN": {"name": "Regeneron", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.8},
            "VRTX": {"name": "Vertex Pharmaceuticals", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Rare Disease Biotech", "beta_30d": 0.9},
            "NVO":  {"name": "Novo Nordisk", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Diabetes/GLP-1 Pharma", "beta_30d": 0.8},

            # ── EVs / AUTOS ──────────────────────────────────────────────────
            "GM":   {"name": "General Motors", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Autos/EV", "beta_30d": 1.3},
            "F":    {"name": "Ford Motor", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Autos/EV", "beta_30d": 1.4},
            "RIVN": {"name": "Rivian", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "EV Trucks", "beta_30d": 2.3},
            "LCID": {"name": "Lucid Group", "sector": "Consumer Disc.", "mcap": "small", "etf": "XLY",
                     "sub_sector": "EV Luxury", "beta_30d": 2.5},
            "DVN":  {"name": "Devon Energy", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.4},
        }

        # ── ALIAS RESOLUTION: Common Names → Tickers ──────────────────────
        self.aliases: dict[str, str] = {
            # Semiconductors
            "nvidia": "NVDA", "nvda": "NVDA", "jensen huang": "NVDA",
            "amd": "AMD", "advanced micro": "AMD", "lisa su": "AMD",
            "intel": "INTC", "pat gelsinger": "INTC",
            "tsmc": "TSM", "taiwan semi": "TSM", "taiwan semiconductor": "TSM",
            "broadcom": "AVGO", "hock tan": "AVGO",
            "qualcomm": "QCOM",
            "asml": "ASML",
            "micron": "MU",
            "lam research": "LRCX", "lam": "LRCX",
            "applied materials": "AMAT",
            "texas instruments": "TXN",
            "arm": "ARM", "arm holdings": "ARM", "softbank arm": "ARM",
            "marvell": "MRVL",
            # Energy
            "exxon": "XOM", "exxon mobil": "XOM", "exxonmobil": "XOM",
            "chevron": "CVX",
            "conocophillips": "COP", "conoco": "COP",
            "eog": "EOG", "eog resources": "EOG",
            "pioneer": "PXD", "pioneer natural": "PXD",
            "occidental": "OXY", "oxy": "OXY",
            "williams": "WMB", "williams companies": "WMB",
            "kinder morgan": "KMI",
            "energy transfer": "ET",
            "schlumberger": "SLB",
            "halliburton": "HAL",
            "nextera": "NEE", "nextera energy": "NEE",
            "enphase": "ENPH",
            "first solar": "FSLR",
            # Financials
            "jpmorgan": "JPM", "jp morgan": "JPM", "chase": "JPM", "jamie dimon": "JPM",
            "goldman": "GS", "goldman sachs": "GS", "david solomon": "GS",
            "bank of america": "BAC", "bofa": "BAC",
            "morgan stanley": "MS",
            "citigroup": "C", "citi": "C",
            "wells fargo": "WFC",
            "berkshire": "BRK.B", "berkshire hathaway": "BRK.B", "warren buffett": "BRK.B", "buffett": "BRK.B",
            "visa": "V",
            "mastercard": "MA",
            "blackrock": "BLK", "larry fink": "BLK",
            # Regional Banks
            "columbia banking": "COLB", "columbia banking system": "COLB",
            "zions": "ZION", "zions bancorporation": "ZION", "zions bancorp": "ZION",
            "regions financial": "RF", "regions bank": "RF",
            "keycorp": "KEY", "key bank": "KEY", "keybank": "KEY",
            "comerica": "CMA",
            "first republic": "FRC",
            "western alliance": "WAL",
            "east west bancorp": "EWBC",
            # Healthcare
            "johnson & johnson": "JNJ", "j&j": "JNJ",
            "pfizer": "PFE",
            "unitedhealth": "UNH", "united health": "UNH",
            "eli lilly": "LLY", "lilly": "LLY",
            "abbvie": "ABBV",
            "merck": "MRK",
            "thermo fisher": "TMO",
            "amgen": "AMGN",
            "gilead": "GILD",
            # Defense
            "lockheed": "LMT", "lockheed martin": "LMT",
            "raytheon": "RTX", "rtx": "RTX",
            "northrop": "NOC", "northrop grumman": "NOC",
            "general dynamics": "GD",
            "boeing": "BA",
            # Technology
            "ibm": "IBM",
            "salesforce": "CRM",
            "oracle": "ORCL",
            "servicenow": "NOW",
            "palantir": "PLTR",
            # Industrials / Transport
            "freightcar america": "RAIL", "freightcar": "RAIL",
            "trinity industries": "TRN", "trinity": "TRN",
            "greenbrier": "GBX", "greenbrier companies": "GBX",
            "caterpillar": "CAT",
            "deere": "DE", "john deere": "DE",
            "ge": "GE", "ge aerospace": "GE",
            "honeywell": "HON",
            "union pacific": "UNP",
            "ups": "UPS",
            "fedex": "FDX",
            # Consumer
            "walmart": "WMT", "wal-mart": "WMT",
            "coca-cola": "KO", "coca cola": "KO", "coke": "KO",
            "pepsi": "PEP", "pepsico": "PEP",
            "procter": "PG", "procter & gamble": "PG", "p&g": "PG",
            "costco": "COST",
            "nike": "NKE",
            "home depot": "HD",
            "lowe's": "LOW", "lowes": "LOW",
            "mcdonald's": "MCD", "mcdonalds": "MCD",
            "starbucks": "SBUX",
            "disney": "DIS", "walt disney": "DIS",
            "target": "TGT",
            "tjx": "TJX", "tj maxx": "TJX", "t.j. maxx": "TJX", "marshalls": "TJX",
            "ross stores": "ROST", "ross": "ROST",
            "dollar general": "DG",
            "dollar tree": "DLTR",
            # Beauty / Personal Care
            "ulta": "ULTA", "ulta beauty": "ULTA",
            "elf beauty": "ELF", "e.l.f.": "ELF", "e.l.f. beauty": "ELF",
            "coty": "COTY",
            "estee lauder": "EL", "estée lauder": "EL", "lauder": "EL",
            # Utilities
            "duke energy": "DUK",
            "southern company": "SO",
            "vistra": "VST",
            # REITs
            "american tower": "AMT",
            "prologis": "PLD",
            "equinix": "EQIX",
            "simon property": "SPG",
            # Materials
            "freeport": "FCX", "freeport-mcmoran": "FCX", "freeport mcmoran": "FCX",
            "newmont": "NEM",
            "nucor": "NUE",
            "air products": "APD",
            "linde": "LIN",
            # Telecom
            "at&t": "T", "att": "T",
            "verizon": "VZ",
            "t-mobile": "TMUS",
            # Mega-cap Tech (Big 7)
            "apple": "AAPL", "iphone": "AAPL", "tim cook": "AAPL",
            "microsoft": "MSFT", "satya nadella": "MSFT", "azure": "MSFT",
            "alphabet": "GOOGL", "google": "GOOGL", "sundar pichai": "GOOGL", "gemini": "GOOGL",
            "meta": "META", "facebook": "META", "mark zuckerberg": "META", "instagram": "META", "whatsapp": "META",
            "amazon": "AMZN", "aws": "AMZN", "andy jassy": "AMZN",
            "netflix": "NFLX",
            "tesla": "TSLA", "elon musk": "TSLA", "elon": "TSLA",
            # More Tech / Software
            "adobe": "ADBE",
            "intuit": "INTU", "turbotax": "INTU",
            "synopsys": "SNPS",
            "cadence": "CDNS",
            "workday": "WDAY",
            "atlassian": "TEAM", "jira": "TEAM",
            "hubspot": "HUBS",
            "uber": "UBER",
            "super micro": "SMCI", "supermicro": "SMCI",
            "shopify": "SHOP",
            # Cybersecurity
            "palo alto": "PANW", "palo alto networks": "PANW",
            "crowdstrike": "CRWD",
            "fortinet": "FTNT",
            "zscaler": "ZS",
            "sentinelone": "S",
            # Cloud / Data
            "snowflake": "SNOW",
            "datadog": "DDOG",
            "cloudflare": "NET",
            "mongodb": "MDB",
            "roblox": "RBLX",
            "snap": "SNAP", "snapchat": "SNAP",
            "roku": "ROKU",
            # Crypto-adjacent
            "coinbase": "COIN",
            "microstrategy": "MSTR",
            "riot": "RIOT", "riot platforms": "RIOT",
            "marathon digital": "MARA",
            "robinhood": "HOOD",
            # Fintech
            "paypal": "PYPL",
            "block": "SQ", "square": "SQ", "cash app": "SQ", "jack dorsey": "SQ",
            "sofi": "SOFI",
            "schwab": "SCHW", "charles schwab": "SCHW",
            "affirm": "AFRM",
            "doordash": "DASH",
            "lyft": "LYFT",
            # Biotech additions
            "moderna": "MRNA",
            "biontech": "BNTX",
            "regeneron": "REGN",
            "vertex": "VRTX",
            "novo nordisk": "NVO", "ozempic": "NVO", "wegovy": "NVO",
            # EVs / Autos
            "general motors": "GM",
            "ford": "F", "ford motor": "F",
            "rivian": "RIVN",
            "lucid": "LCID",
            "devon": "DVN", "devon energy": "DVN",
        }

        # ── SECTOR → ETF CONTAGION MAP ─────────────────────────────────────
        self.sector_correlations: dict[str, list[str]] = {
            "Crypto":            ["IBIT", "BITO", "WGMI", "BITQ"],
            "Semiconductors":    ["SMH", "SOXX", "XSD", "PSI"],
            "Energy":            ["XLE", "XOP", "OIH", "AMLP", "TAN"],
            "Financials":        ["XLF", "KRE", "KBE", "IAI"],
            "Healthcare":        ["XLV", "IBB", "XBI", "IHI"],
            "Defense":           ["ITA", "PPA", "XAR"],
            "Technology":        ["XLK", "IGV", "WCLD"],
            "Industrials":       ["XLI", "IYT"],
            "Transportation":    ["IYT", "XLI"],
            "Consumer Staples":  ["XLP", "KXI"],
            "Consumer Disc.":    ["XLY", "FDIS"],
            "Communication":     ["XLC", "VOX"],
            "Utilities":         ["XLU", "IDU"],
            "REITs":             ["VNQ", "IYR", "XLRE"],
            "Materials":         ["XLB", "GDX", "SLV"],
            "Telecom":           ["XLC", "VOX"],
        }

        # ── SUPPLY CHAIN & DEPENDENCY GRAPH ─────────────────────────────────
        # Maps a ticker to its key suppliers, customers, and peers
        self.supply_chain: dict[str, dict[str, list[str]]] = {
            "NVDA": {
                "suppliers": ["TSM", "ASML", "LRCX", "AMAT", "MU"],
                "customers": ["ORCL", "EQIX", "VST"],  # Data center / power
                "peers": ["AMD", "INTC", "AVGO", "ARM"],
            },
            "AMD": {
                "suppliers": ["TSM", "ASML"],
                "customers": ["ORCL"],
                "peers": ["NVDA", "INTC"],
            },
            "TSM": {
                "suppliers": ["ASML", "LRCX", "AMAT"],
                "customers": ["NVDA", "AMD", "QCOM", "AVGO", "ARM"],
                "peers": ["INTC"],
            },
            "ASML": {
                "suppliers": [],
                "customers": ["TSM", "INTC"],
                "peers": ["LRCX", "AMAT"],
            },
            "XOM": {
                "suppliers": ["SLB", "HAL"],
                "customers": [],
                "peers": ["CVX", "COP", "OXY"],
            },
            "BA": {
                "suppliers": ["GE", "RTX", "HON"],
                "customers": [],
                "peers": ["LMT", "RTX"],
            },
            "LMT": {
                "suppliers": ["RTX", "NOC", "GD"],
                "customers": [],
                "peers": ["RTX", "NOC", "GD", "BA"],
            },
            "JPM": {
                "suppliers": [],
                "customers": [],
                "peers": ["GS", "BAC", "MS", "C", "WFC"],
            },
            "WMT": {
                "suppliers": ["PG", "KO", "PEP"],
                "customers": [],
                "peers": ["COST", "HD"],
            },
            "UNH": {
                "suppliers": [],
                "customers": [],
                "peers": ["LLY", "JNJ", "PFE"],
            },
            "EQIX": {
                "suppliers": [],
                "customers": ["NVDA", "CRM", "ORCL"],
                "peers": ["AMT", "PLD"],
            },
            "FCX": {
                "suppliers": [],
                "customers": [],
                "peers": ["NEM", "NUE"],
            },
            "ULTA": {
                "suppliers": ["EL", "COTY", "ELF"],
                "customers": [],
                "peers": ["ELF", "COTY", "EL", "TGT"],
            },
            "ELF": {
                "suppliers": [],
                "customers": ["ULTA", "TGT", "WMT"],
                "peers": ["COTY", "EL"],
            },
            "TGT": {
                "suppliers": ["PG", "KO"],
                "customers": [],
                "peers": ["WMT", "COST", "DG"],
            },
        }

        # ── MARKET STATE (live via yfinance — VIX, SPY, pre-market, earnings) ──
        self.live_market = LiveMarketState()
        self.market_state = self.live_market.state  # shared reference — updates in-place

    def resolve_ticker(self, text: str) -> Optional[str]:
        """Resolve a company name or alias to its NYSE ticker."""
        text_lower = text.lower().strip()
        text_upper = text.upper().strip()
        if text_upper in self.tickers:
            return text_upper
        if text_lower in self.aliases:
            return self.aliases[text_lower]
        return None

    def get_sector_etfs(self, ticker: str) -> list[str]:
        info = self.tickers.get(ticker, {})
        sector = info.get("sector", "")
        return self.sector_correlations.get(sector, [])

    def get_market_cap_bucket(self, ticker: str) -> str:
        return self.tickers.get(ticker, {}).get("mcap", "unknown")

    def get_beta(self, ticker: str) -> float:
        return self.tickers.get(ticker, {}).get("beta_30d", 1.0)

    def get_supply_chain_exposure(self, ticker: str) -> dict[str, list[str]]:
        return self.supply_chain.get(ticker, {"suppliers": [], "customers": [], "peers": []})

    def get_sector_peers(self, ticker: str) -> list[str]:
        """Get all tickers in the same sub-sector."""
        info = self.tickers.get(ticker, {})
        sub = info.get("sub_sector", "")
        if not sub:
            return []
        return [t for t, d in self.tickers.items() if d.get("sub_sector") == sub and t != ticker]

    def get_vix_regime_multiplier(self) -> float:
        """Higher VIX = news has amplified impact."""
        vix = self.market_state["vix"]
        if vix < 15:
            return 0.9
        elif vix < 20:
            return 1.0
        elif vix < 30:
            return 1.15
        elif vix < 40:
            return 1.30
        return 1.50  # Crisis

    def get_time_of_day_multiplier(self) -> float:
        """Pre-market and first 30 min of trading see amplified reactions."""
        if self.market_state.get("is_pre_market"):
            return 1.15
        return 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: ENTITY & TICKER EXTRACTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class EntityExtractor:
    """
    Multi-pass entity extraction with supply chain propagation.

    Pass 1: Explicit ticker symbols ($NVDA, NYSE:NVDA)
    Pass 2: Company name / alias resolution
    Pass 3: Sector keyword detection for macro events
    Pass 4: Supply chain contagion graph traversal
    Pass 5: Sector → ETF propagation
    """

    # Aliases that are common English words — always require word-boundary matching
    # regardless of length, to prevent false extraction from news text.
    AMBIGUOUS_ALIASES = {
        "ge", "arm", "lam", "ups", "citi", "chase", "visa", "coke", "now",
        "oxy", "all", "it", "on", "an", "key", "car", "run", "well",
        "lilly", "pioneer", "gold", "ford",
    }

    # Patterns to detect analyst/rater role and separate actor from target.
    # Group "actor" captures the firm performing the action (analyst).
    # These patterns match common headline structures for upgrades/downgrades.
    ANALYST_ACTION_PATTERNS = [
        # "VMC downgraded to Neutral by JPMorgan" / "VMC upgraded by Goldman Sachs"
        re.compile(
            r'(?:downgrade[sd]?|upgrade[sd]?|rated|cut|initiated?|reiterate[sd]?'
            r'|maintained?|raises?\s+(?:price\s+)?target|lowers?\s+(?:price\s+)?target'
            r'|overweight|underweight|outperform|underperform|neutral|sell\s+rating'
            r'|buy\s+rating)\s+.*?\bby\s+(?P<actor>.+?)(?:\s*[,;.\-—]|\s+(?:as|amid|after|on|citing|due|with|the|saying|over|ahead|following|here))',
            re.IGNORECASE,
        ),
        # "JPMorgan downgrades VMC" / "Goldman Sachs upgrades AAPL"
        re.compile(
            r'(?P<actor>.+?)\s+(?:downgrade[sd]?|upgrade[sd]?|initiate[sd]?'
            r'|reiterate[sd]?|maintain[sd]?|cut[sd]?|rate[sd]?'
            r'|raises?\s+(?:price\s+)?target|lowers?\s+(?:price\s+)?target'
            r'|starts?\s+coverage|begins?\s+coverage)\s',
            re.IGNORECASE,
        ),
        # "Goldman warns of..." / "Jack Dorsey praises..." / "Morgan Stanley expects..."
        # Person/firm is the COMMENTATOR or ENDORSER, not the subject of the news
        re.compile(
            r'(?P<actor>.+?)\s+(?:warns?|says?|expects?|predicts?|forecasts?'
            r'|sees?\b|projects?|estimates?|cautions?|flags?|notes?'
            r'|believes?|analysts?\s+at|strategists?\s+at|economists?\s+at'
            r'|research\s+from|according\s+to|report\s+from|reaffirms?'
            r'|highlights?|signals?|recommends?'
            r'|praises?|endorses?|backs?|supports?|touts?|applauds?'
            r'|criticizes?|slams?|blasts?|questions?|doubts?)\s',
            re.IGNORECASE,
        ),
        # "...warns Goldman" / "...says JPMorgan" / "...praises Jack Dorsey"
        re.compile(
            r'(?:warns?|says?|expects?|predicts?|forecasts?|sees?'
            r'|projects?|estimates?|cautions?|flags?|notes?'
            r'|believes?|according\s+to|report\s+(?:from|by)'
            r'|praises?|endorses?|backs?|supports?|touts?)\s+(?P<actor>.+?)(?:\s*[,;.\-—]|$)',
            re.IGNORECASE,
        ),
    ]

    def __init__(self, reference_db: NYSEReferenceDB):
        self.db = reference_db
        self.ticker_pattern = re.compile(
            r'(?:\$([A-Z]{1,5}))'                             # $VMC
            r'|(?:\((?:NYSE|NASDAQ)\s*:\s*([A-Z]{1,5})\))'    # (NYSE:VMC)
            r'|(?:\(([A-Z]{1,5})\))'                          # (VMC) — parenthesized ticker
        )
        # Combined set of all known tickers (detailed DB + broker lists)
        self._all_known_tickers = (
            set(self.db.tickers.keys())
            | StockAvailabilityChecker.REVOLUT_TICKERS
            | StockAvailabilityChecker.XTB_TICKERS
        )
        # Precompile word-boundary regex for short/ambiguous aliases
        self._alias_patterns: dict[str, tuple[re.Pattern, str]] = {}
        for alias, ticker in self.db.aliases.items():
            if len(alias) <= 3 or alias in self.AMBIGUOUS_ALIASES:
                self._alias_patterns[alias] = (
                    re.compile(r'\b' + re.escape(alias) + r'\b'),
                    ticker,
                )
            else:
                self._alias_patterns[alias] = (None, ticker)  # plain substring
        # Sector keywords for macro events that don't mention specific companies.
        # Order matters: Crypto is checked first so "bitcoin" articles don't fall
        # through to Materials just because "gold" appears in comparison text.
        self.sector_keywords: dict[str, list[str]] = {
            "Crypto": ["bitcoin", "btc", "ethereum", "eth ", "crypto", "cryptocurrency",
                       "blockchain", "defi", "stablecoin", "digital asset", "microstrategy",
                       "bitcoin etf", "spot etf", "crypto regulation", "digital currency",
                       "altcoin", "memecoin", "nft"],
            "Semiconductors": ["chip", "semiconductor", "wafer", "fab ", "foundry", "gpu", "ai chip",
                               "hbm", "memory chip", "processor", "lithography"],
            "Energy": ["oil", "crude", "natural gas", "lng", "opec", "drilling", "refinery",
                       "pipeline", "barrel", "permian", "shale", "petroleum", "brent", "wti"],
            "Financials": ["banking", "interest rate", "loan", "mortgage", "credit card",
                           "lending", "deposit", "yield curve", "net interest"],
            "Healthcare": ["drug", "pharma", "clinical trial", "fda", "medicare", "medicaid",
                           "hospital", "vaccine", "biotech", "gene therapy", "obesity drug"],
            "Defense": ["defense contract", "pentagon", "military", "weapon", "missile",
                        "fighter jet", "nato", "defense spending", "arms"],
            "Utilities": ["power grid", "electricity", "nuclear", "renewable", "solar",
                          "wind farm", "data center power", "grid reliability"],
            "REITs": ["commercial real estate", "office vacancy", "data center",
                      "warehouse", "industrial real estate", "cell tower"],
            "Materials": ["copper", "gold price", "gold miner", "steel", "aluminum", "lithium",
                          "rare earth", "mining", "commodity", "iron ore", "gold futures",
                          "precious metal"],
        }

    def extract(self, headline: str, body: str = "") -> dict:
        text = f"{headline} {body}"
        found_tickers = set()
        found_sectors = set()
        found_etfs = set()
        found_supply_chain = set()
        found_contagion = set()

        # Pass 1: Explicit ticker symbols ($VMC, NYSE:VMC, or (VMC))
        for match in self.ticker_pattern.finditer(text):
            ticker = match.group(1) or match.group(2) or match.group(3)
            if ticker in self._all_known_tickers:
                found_tickers.add(ticker)

        # Pass 2: Company name / alias resolution (word-boundary safe)
        text_lower = text.lower()
        for alias, (pattern, ticker) in self._alias_patterns.items():
            if pattern is not None:
                # Short or ambiguous alias — require whole-word match
                if pattern.search(text_lower):
                    found_tickers.add(ticker)
            else:
                # Longer, unambiguous alias — substring is safe
                if alias in text_lower:
                    found_tickers.add(ticker)

        # Pass 2b: Analyst role detection — identify actor (analyst firm) tickers.
        # These will be removed AFTER all passes so that sector/supply-chain tickers
        # are available as targets. This fixes cases like "Goldman warns of GDP drag"
        # where GS is the only ticker at this point but oil/macro tickers come later.
        analyst_tickers = set()
        headline_lower = headline.lower()
        for pattern in self.ANALYST_ACTION_PATTERNS:
            m = pattern.search(headline_lower)
            if m:
                actor_text = m.group("actor").strip()
                # Resolve the actor text to a ticker via aliases
                for alias, (apatt, aticker) in self._alias_patterns.items():
                    if apatt is not None:
                        if apatt.search(actor_text):
                            analyst_tickers.add(aticker)
                    else:
                        if alias in actor_text:
                            analyst_tickers.add(aticker)
                # Also check explicit ticker symbols in the actor text
                for tmatch in self.ticker_pattern.finditer(actor_text):
                    t = tmatch.group(1) or tmatch.group(2) or tmatch.group(3)
                    if t in self._all_known_tickers:
                        analyst_tickers.add(t)
                break  # first matching pattern is enough

        # Pass 3: Sector keyword detection (for macro / broad events)
        detected_sectors_from_keywords = set()
        for sector, keywords in self.sector_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    detected_sectors_from_keywords.add(sector)
                    break

        # If no real target tickers found (empty or only analyst messengers),
        # use sector keywords to flag sector-wide impact
        real_tickers = found_tickers - analyst_tickers
        if not real_tickers and detected_sectors_from_keywords:
            for sector in detected_sectors_from_keywords:
                found_sectors.add(sector)
                found_etfs.update(self.db.sector_correlations.get(sector, []))

        # Pass 4: Supply chain contagion
        for ticker in list(found_tickers):
            chain = self.db.get_supply_chain_exposure(ticker)
            for role, related in chain.items():
                for t in related:
                    found_supply_chain.add(f"{t} ({role[:-1]})")  # "TSM (supplier)"
                    found_contagion.add(t)

        # Pass 5: Sector & ETF propagation from real target tickers only.
        # Exclude analyst/messenger tickers so their sectors don't pollute ETFs.
        # e.g. Jack Dorsey → SQ → Financials ETFs should NOT appear on an NVDA article.
        target_tickers = found_tickers - analyst_tickers
        for ticker in target_tickers:
            info = self.db.tickers.get(ticker, {})
            if "sector" in info:
                found_sectors.add(info["sector"])
            found_etfs.update(self.db.get_sector_etfs(ticker))

        # Also add sectors from keywords even if we have tickers
        found_sectors.update(detected_sectors_from_keywords)

        # Final pass: Remove analyst/messenger tickers identified in Pass 2b.
        # Always remove the messenger — even if it's the only ticker found.
        # The "Missing Main Character" fix downstream will promote the correct
        # ticker from Claude's correlated_moves/ticker_signals.
        # e.g. "Goldman warns of GDP drag" → GS removed, Claude provides USO/XOM/SPY.
        if analyst_tickers:
            found_tickers -= analyst_tickers
            found_supply_chain -= analyst_tickers
            found_contagion -= analyst_tickers

        return {
            "tickers": sorted(found_tickers),
            "sectors": sorted(found_sectors),
            "etfs": sorted(found_etfs),
            "supply_chain": sorted(found_supply_chain),
            "contagion": sorted(found_contagion - found_tickers),  # Exclude direct hits
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: AI MARKET IMPACT SCORING ENGINE v2
# ═══════════════════════════════════════════════════════════════════════════════

class MarketImpactScoringEngine:
    """
    Enhanced three-stage scoring pipeline with:
    - Expanded event taxonomy (55+ types)
    - Beta-adjusted impact
    - VIX regime awareness
    - Supply chain amplification
    - Source credibility weighting
    - Earnings season context
    """

    EVENT_BASE_SCORES: dict[str, int] = {
        # Earnings
        "EARNINGS_BEAT": 55, "EARNINGS_MISS": 60,
        "REVENUE_BEAT": 50, "REVENUE_MISS": 55,
        "GUIDANCE_RAISE": 65, "GUIDANCE_CUT": 70,
        # M&A / Corporate
        "MA_ANNOUNCED": 80, "MA_BLOCKED": 75, "SPINOFF": 55,
        "STOCK_BUYBACK": 40, "DIVIDEND_CUT": 65, "DIVIDEND_HIKE": 35,
        "STOCK_SPLIT": 30,
        # Regulatory
        "FDA_APPROVAL": 85, "FDA_REJECTION": 90,
        "REGULATORY_ACTION": 70, "ANTITRUST": 75, "PATENT_RULING": 60,
        # Analyst
        "ANALYST_UPGRADE": 40, "ANALYST_DOWNGRADE": 45, "ANALYST_INITIATION": 30,
        # Leadership
        "CEO_DEPARTURE": 65, "CFO_DEPARTURE": 55, "BOARD_SHAKEUP": 50,
        # Insider
        "INSIDER_BUY": 35, "INSIDER_SELL": 45,
        # Macro
        "MACRO_CPI": 70, "MACRO_FOMC": 90, "MACRO_NFP": 75,
        "MACRO_GDP": 65, "MACRO_PPI": 55, "MACRO_RETAIL_SALES": 50,
        "MACRO_HOUSING": 45, "MACRO_PMI": 50,
        # Sector-Specific
        "CHIP_EXPORT_CONTROL": 85, "OIL_PRODUCTION_CUT": 80, "OIL_INVENTORY": 50,
        "PIPELINE_DISRUPTION": 70, "POWER_GRID_EVENT": 60, "DRUG_TRIAL_DATA": 80,
        "CYBER_BREACH": 65, "SUPPLY_CHAIN_DISRUPTION": 70,
        "PRODUCT_RECALL": 60, "CONTRACT_WIN": 55, "CONTRACT_LOSS": 60,
        # Distress
        "BANKRUPTCY": 95, "CREDIT_DOWNGRADE": 65, "CREDIT_UPGRADE": 50,
        "DEBT_DEFAULT": 90,
        # Special
        "ACTIVIST_STAKE": 60, "SHORT_SQUEEZE": 70,
        "GEOPOLITICAL": 75, "TARIFF": 75, "SANCTIONS": 80,
        "NATURAL_DISASTER": 65,
        "UNKNOWN": 20,
    }

    SOURCE_MULTIPLIERS: dict[int, float] = {
        1: 1.15,   # Institutional (Reuters, Bloomberg, Fed)
        2: 1.00,   # Professional (Benzinga, SEC EDGAR, CNBC)
        3: 0.70,   # Social (Twitter/X, Reddit)
    }

    MCAP_MULTIPLIERS: dict[str, float] = {
        "mega": 1.20,   # > $200B
        "large": 1.00,  # $10B-$200B
        "mid": 0.85,    # $2B-$10B
        "small": 0.70,  # < $2B
        "unknown": 0.80,
    }

    EVENT_PATTERNS: list[tuple[str, EventType, float]] = [
        # FDA / Drug
        (r"fda\s+approv", EventType.FDA_APPROVAL, 0.9),
        (r"fda\s+reject|fda\s+den|complete\s+response\s+letter|crl\b", EventType.FDA_REJECTION, 0.9),
        (r"phase\s+[123i]+.*(?:data|results|endpoint|efficacy)|clinical\s+trial.*(?:success|fail|miss)", EventType.DRUG_TRIAL_DATA, 0.85),
        # Earnings / Revenue / Guidance
        (r"beat.*(?:earnings|eps)|(?:earnings|eps).*beat|tops\s+estimates|(?:eps|earnings)\s+surprise", EventType.EARNINGS_BEAT, 0.85),
        (r"miss.*(?:earnings|eps)|(?:earnings|eps).*miss|falls?\s+short|disappointing\s+(?:earnings|eps)", EventType.EARNINGS_MISS, 0.85),
        (r"revenue.*beat|revenue.*tops|revenue.*exceed", EventType.REVENUE_BEAT, 0.8),
        (r"revenue.*miss|revenue.*falls?\s+short|revenue.*disappoint", EventType.REVENUE_MISS, 0.8),
        (r"rais(?:e[sd]?|ing)\s+(?:full.year\s+)?guidance|guidance\s+(?:raise|up|higher|above)", EventType.GUIDANCE_RAISE, 0.85),
        (r"(?:cut|lower|slash|reduce)[sd]?\s+guidance|guidance\s+(?:cut|down|below|lower)", EventType.GUIDANCE_CUT, 0.85),
        # M&A / Corporate Actions
        (r"acquir|merger|buyout|takeover|(?:to\s+buy)|(?:deal\s+to)", EventType.MA_ANNOUNCED, 0.9),
        (r"(?:block|reject|halt)\w*\s+(?:merger|acquisition|deal)|antitrust\s+(?:block|challenge)", EventType.MA_BLOCKED, 0.85),
        (r"spin\s*off|spin\s*out|separate\s+unit|split\s+into", EventType.SPINOFF, 0.8),
        (r"buyback|share\s+repurchas|stock\s+repurchas", EventType.STOCK_BUYBACK, 0.75),
        (r"(?:cut|slash|suspend|eliminat)\w*\s+dividend", EventType.DIVIDEND_CUT, 0.85),
        (r"(?:rais|hik|increas|boost)\w*\s+dividend|special\s+dividend", EventType.DIVIDEND_HIKE, 0.75),
        # Analyst
        (r"upgrade[sd]?|raises?\s+(?:price\s+)?target|overweight", EventType.ANALYST_UPGRADE, 0.75),
        (r"downgrade[sd]?|lower[sd]?\s+(?:price\s+)?target|underweight|sell\s+rating", EventType.ANALYST_DOWNGRADE, 0.75),
        (r"initiat\w+\s+coverage|new\s+coverage", EventType.ANALYST_INITIATION, 0.7),
        # Leadership
        (r"ceo\s+(?:resign|depart|step|fired|ousted|retire|leaves?)", EventType.CEO_DEPARTURE, 0.85),
        (r"cfo\s+(?:resign|depart|step|fired|ousted|retire|leaves?)", EventType.CFO_DEPARTURE, 0.8),
        (r"board.*(?:shakeup|overhaul|resign)|director.*resign", EventType.BOARD_SHAKEUP, 0.75),
        # Macro
        (r"cpi\s+(?:rise|fall|surge|drop|unexpect|surprise|higher|lower|hot)", EventType.MACRO_CPI, 0.8),
        (r"(?:fed|fomc)\s+(?:rate|hike|cut|hold|pause|hawkish|dovish|decision)", EventType.MACRO_FOMC, 0.9),
        (r"(?:nonfarm|non-farm|payroll|jobs?\s+report).*(?:surge|plunge|beat|miss|add)", EventType.MACRO_NFP, 0.8),
        (r"gdp\s+(?:grow|contract|surge|miss|beat|shrink|revis)", EventType.MACRO_GDP, 0.8),
        (r"ppi\s+(?:rise|fall|surge|drop|unexpect|hot)", EventType.MACRO_PPI, 0.75),
        (r"retail\s+sales?\s+(?:surge|plunge|beat|miss|drop|rise)", EventType.MACRO_RETAIL_SALES, 0.75),
        (r"(?:housing\s+starts?|existing\s+home|new\s+home)\s+(?:surge|plunge|drop|rise|fall)", EventType.MACRO_HOUSING, 0.7),
        (r"(?:pmi|manufacturing\s+index|ism)\s+(?:expand|contract|surge|fall|surprise)", EventType.MACRO_PMI, 0.75),
        # Sector-Specific
        (r"(?:chip|semiconductor)\s+(?:export|restrict|ban|sanction|control)|huawei.*chip|chip.*(?:china|beijing)", EventType.CHIP_EXPORT_CONTROL, 0.9),
        (r"opec.*(?:cut|reduce|curb|slash)|production\s+cut|oil\s+(?:cut|curtail)", EventType.OIL_PRODUCTION_CUT, 0.85),
        (r"(?:crude|oil)\s+inventor(?:y|ies)\s+(?:build|draw|surge|drop|surprise)", EventType.OIL_INVENTORY, 0.75),
        (r"pipeline\s+(?:explosi|ruptur|leak|shut|disrupt|attack)", EventType.PIPELINE_DISRUPTION, 0.85),
        (r"(?:power\s+grid|blackout|grid\s+failure|rolling\s+blackout|electricity.*outage)", EventType.POWER_GRID_EVENT, 0.8),
        (r"cyber\s*(?:attack|breach|hack|incident|ransomware)|data\s+breach|hack(?:ed|ing)", EventType.CYBER_BREACH, 0.85),
        (r"supply\s+chain\s+(?:disrupt|crisis|shortage|bottleneck)", EventType.SUPPLY_CHAIN_DISRUPTION, 0.8),
        (r"(?:product|vehicle|food)\s+recall|safety\s+recall|voluntary\s+recall", EventType.PRODUCT_RECALL, 0.75),
        (r"(?:award|win|secur)\w*\s+(?:\$[\d.]+[BbMm]?\s+)?contract|defense\s+contract", EventType.CONTRACT_WIN, 0.8),
        (r"(?:los[est]+|fail)\w*\s+contract|contract\s+(?:cancel|terminat|lost)", EventType.CONTRACT_LOSS, 0.8),
        # Insider
        (r"insider\s+(?:buy|purchas)", EventType.INSIDER_BUY, 0.7),
        (r"insider\s+(?:sell|sold|dump)", EventType.INSIDER_SELL, 0.7),
        # Distress
        (r"bankrupt|chapter\s+(?:7|11)|default|insolven", EventType.BANKRUPTCY, 0.95),
        (r"(?:moody|s&p|fitch)\s+(?:downgrad|cut|lower)\w*\s+(?:credit|rating|debt)", EventType.CREDIT_DOWNGRADE, 0.85),
        (r"(?:moody|s&p|fitch)\s+(?:upgrad|rais)\w*\s+(?:credit|rating|debt)", EventType.CREDIT_UPGRADE, 0.8),
        # Special
        (r"sec\s+(?:charg|investigat|probe|lawsuit|fine|enforcement)", EventType.REGULATORY_ACTION, 0.85),
        (r"antitrust|(?:doj|ftc)\s+(?:su|block|challenge|investigat)", EventType.ANTITRUST, 0.85),
        (r"activist|stake|13d|proxy\s+fight|hostile", EventType.ACTIVIST_STAKE, 0.8),
        (r"short\s+squeeze|gamma\s+squeeze|meme\s+stock", EventType.SHORT_SQUEEZE, 0.75),
        (r"sanction|tariff|trade\s+war|trade\s+restrict|embargo", EventType.TARIFF, 0.8),
        (r"geopolit|war\s+|military\s+strike|invasion|conflict\s+escalat", EventType.GEOPOLITICAL, 0.75),
        (r"hurricane|earthquake|wildfire|flood|tsunami|natural\s+disaster", EventType.NATURAL_DISASTER, 0.8),
        (r"patent.*(?:invalid|upheld|ruling|granted|infring)", EventType.PATENT_RULING, 0.75),
    ]

    BULLISH_KEYWORDS = {
        "beat", "surge", "soar", "rally", "approval", "upgrade", "record",
        "breakthrough", "growth", "bullish", "outperform", "buy", "strong",
        "exceeds", "raises", "dividend", "accelerat", "optimis", "boom",
        "profit", "recovery", "expand", "wins", "awarded", "above",
        "positive", "upside", "best", "tops", "surprise", "blowout",
        "hike", "buyback", "repurchas",
    }

    BEARISH_KEYWORDS = {
        "miss", "plunge", "crash", "decline", "rejection", "downgrade",
        "bankruptcy", "default", "warning", "layoff", "recall", "probe",
        "investigation", "fraud", "loss", "bearish", "underperform", "sell",
        "cuts", "slashes", "disappointing", "weak", "concern", "fear",
        "sanctions", "tariff", "halt", "suspend", "breach", "hack",
        "shortage", "crisis", "failure", "below", "worst", "downside",
        "slash", "negative", "resign", "depart", "oust", "restrict",
    }

    def __init__(self, reference_db: NYSEReferenceDB):
        self.db = reference_db

    def classify_event(self, headline: str, body: str = "") -> tuple[EventType, float]:
        text = f"{headline} {body}".lower()
        best_match = (EventType.UNKNOWN, 0.0)
        for pattern, event_type, base_conf in self.EVENT_PATTERNS:
            if re.search(pattern, text):
                if base_conf > best_match[1]:
                    best_match = (event_type, base_conf)
        return best_match

    def analyze_sentiment(self, headline: str, body: str = "") -> float:
        text = f"{headline} {body}".lower()
        words = set(re.findall(r'\b\w+\b', text))
        bull_count = len(words & self.BULLISH_KEYWORDS)
        bear_count = len(words & self.BEARISH_KEYWORDS)
        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return round((bull_count - bear_count) / total, 3)

    def compute_impact_score(
        self,
        event_type: EventType,
        sentiment: float,
        source_tier: int,
        affected_tickers: list[str],
        contagion_tickers: list[str],
    ) -> int:
        # Base score from event type
        base = self.EVENT_BASE_SCORES.get(event_type.value, 20)

        # Sentiment magnitude amplifier
        sentiment_amp = 1.0 + (abs(sentiment) * 0.3)

        # Source credibility
        source_mult = self.SOURCE_MULTIPLIERS.get(source_tier, 0.8)

        # Market cap significance (use highest mcap among affected)
        mcap_mult = max(
            (self.MCAP_MULTIPLIERS.get(self.db.get_market_cap_bucket(t), 0.8)
             for t in affected_tickers),
            default=0.8
        )

        # Beta amplifier — high-beta stocks react more violently
        max_beta = max((self.db.get_beta(t) for t in affected_tickers), default=1.0)
        beta_amp = 1.0 + max(0, (max_beta - 1.0) * 0.15)

        # VIX regime amplifier
        vix_mult = self.db.get_vix_regime_multiplier()

        # Time of day
        tod_mult = self.db.get_time_of_day_multiplier()

        # Multi-ticker / contagion bonus
        ticker_bonus = min(len(affected_tickers) * 3, 12)
        contagion_bonus = min(len(contagion_tickers) * 2, 10)

        # Earnings season dampener for earnings events (more noise)
        earnings_events = {"EARNINGS_BEAT", "EARNINGS_MISS", "REVENUE_BEAT",
                           "REVENUE_MISS", "GUIDANCE_RAISE", "GUIDANCE_CUT"}
        season_mult = 0.9 if (self.db.market_state.get("is_earnings_season")
                              and event_type.value in earnings_events) else 1.0

        # Compute raw score
        raw = (base * sentiment_amp * source_mult * mcap_mult * beta_amp
               * vix_mult * tod_mult * season_mult) + ticker_bonus + contagion_bonus

        return max(1, min(100, int(round(raw))))

    def determine_direction(self, event_type: EventType, sentiment: float) -> Direction:
        inherently_bearish = {
            EventType.EARNINGS_MISS, EventType.REVENUE_MISS, EventType.GUIDANCE_CUT,
            EventType.FDA_REJECTION, EventType.MA_BLOCKED,
            EventType.ANALYST_DOWNGRADE, EventType.CEO_DEPARTURE, EventType.CFO_DEPARTURE,
            EventType.INSIDER_SELL, EventType.BANKRUPTCY, EventType.DEBT_DEFAULT,
            EventType.CREDIT_DOWNGRADE, EventType.DIVIDEND_CUT,
            EventType.REGULATORY_ACTION, EventType.ANTITRUST,
            EventType.CYBER_BREACH, EventType.PRODUCT_RECALL, EventType.CONTRACT_LOSS,
            EventType.PIPELINE_DISRUPTION,
        }
        inherently_bullish = {
            EventType.EARNINGS_BEAT, EventType.REVENUE_BEAT, EventType.GUIDANCE_RAISE,
            EventType.FDA_APPROVAL, EventType.MA_ANNOUNCED,
            EventType.ANALYST_UPGRADE, EventType.ANALYST_INITIATION,
            EventType.INSIDER_BUY, EventType.CREDIT_UPGRADE,
            EventType.DIVIDEND_HIKE, EventType.STOCK_BUYBACK,
            EventType.CONTRACT_WIN, EventType.DRUG_TRIAL_DATA,
        }

        if event_type in inherently_bearish:
            return Direction.BEARISH
        elif event_type in inherently_bullish:
            return Direction.BULLISH
        elif sentiment > 0.2:
            return Direction.BULLISH
        elif sentiment < -0.2:
            return Direction.BEARISH
        return Direction.NEUTRAL

    def determine_urgency(self, impact_score: int, event_type: EventType) -> Urgency:
        flash_events = {
            EventType.MACRO_FOMC, EventType.BANKRUPTCY, EventType.DEBT_DEFAULT,
            EventType.GEOPOLITICAL, EventType.FDA_APPROVAL, EventType.FDA_REJECTION,
        }
        if impact_score >= 90 or (impact_score >= 80 and event_type in flash_events):
            return Urgency.FLASH
        elif impact_score >= 70:
            return Urgency.HIGH
        elif impact_score >= 45:
            return Urgency.STANDARD
        return Urgency.LOW

    def score_event(self, event: RawNewsEvent, entities: dict) -> ScoredEvent:
        t_start = time.perf_counter()

        event_type, confidence = self.classify_event(event.headline, event.body)
        sentiment = self.analyze_sentiment(event.headline, event.body)

        impact_score = self.compute_impact_score(
            event_type=event_type,
            sentiment=sentiment,
            source_tier=event.source_tier,
            affected_tickers=entities["tickers"],
            contagion_tickers=entities.get("contagion", []),
        )

        direction = self.determine_direction(event_type, sentiment)
        urgency = self.determine_urgency(impact_score, event_type)

        latency_ms = (time.perf_counter() - t_start) * 1000

        return ScoredEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            headline=event.headline,
            source=event.source,
            source_tier=event.source_tier,
            event_type=event_type,
            urgency=urgency,
            sentiment=sentiment,
            direction=direction,
            impact_score=impact_score,
            affected_tickers=entities["tickers"],
            affected_sectors=entities["sectors"],
            affected_etfs=entities["etfs"],
            supply_chain_exposure=entities.get("supply_chain", []),
            contagion_tickers=entities.get("contagion", []),
            url=event.url,
            latency_ms=round(latency_ms, 2),
            ws_source=event.ws_source,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: ALERT DISPATCHER (Enhanced with urgency levels)
# ═══════════════════════════════════════════════════════════════════════════════

class AlertDispatcher:

    CRITICAL_THRESHOLD = 80
    HIGH_THRESHOLD = 60
    MEDIUM_THRESHOLD = 40

    COLORS = {
        "CRITICAL": "\033[91m\033[1m",
        "HIGH":     "\033[93m\033[1m",
        "MEDIUM":   "\033[96m",
        "LOW":      "\033[90m",
        "RESET":    "\033[0m",
        "GREEN":    "\033[92m",
        "RED":      "\033[91m",
        "WHITE":    "\033[97m\033[1m",
        "MAGENTA":  "\033[95m",
        "DIM":      "\033[2m",
    }

    URGENCY_SYMBOLS = {
        "FLASH": "⚡⚡",
        "HIGH": "⚡",
        "STANDARD": "●",
        "LOW": "○",
    }

    def classify_severity(self, score: int) -> str:
        if score >= self.CRITICAL_THRESHOLD:
            return "CRITICAL"
        elif score >= self.HIGH_THRESHOLD:
            return "HIGH"
        elif score >= self.MEDIUM_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    def format_direction_badge(self, direction: Direction) -> str:
        c = self.COLORS
        if direction == Direction.BULLISH:
            return f"{c['GREEN']}▲ BULLISH{c['RESET']}"
        elif direction == Direction.BEARISH:
            return f"{c['RED']}▼ BEARISH{c['RESET']}"
        return f"{c['WHITE']}● NEUTRAL{c['RESET']}"

    def format_score_bar(self, score: int) -> str:
        filled = score // 5
        empty = 20 - filled
        if score >= 80:
            color = self.COLORS["CRITICAL"]
        elif score >= 60:
            color = self.COLORS["HIGH"]
        elif score >= 40:
            color = self.COLORS["MEDIUM"]
        else:
            color = self.COLORS["LOW"]
        return f"{color}{'█' * filled}{'░' * empty}{self.COLORS['RESET']} {score}/100"

    async def dispatch(self, event: ScoredEvent):
        severity = self.classify_severity(event.impact_score)
        c = self.COLORS

        timestamp = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
        ts_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
        urgency_sym = self.URGENCY_SYMBOLS.get(event.urgency.value, "●")

        print()
        print(f"  {c[severity]}{'━' * 76}{c['RESET']}")
        print(f"  {c[severity]}{urgency_sym} {severity} ALERT{c['RESET']}  │  {ts_str} UTC  │  "
              f"Urgency: {event.urgency.value}  │  Processed in {event.latency_ms:.1f}ms")
        print(f"  {c[severity]}{'━' * 76}{c['RESET']}")
        print()
        print(f"    {c['WHITE']}Headline:{c['RESET']}   {event.headline}")
        if event.brief:
            print(f"    {c['WHITE']}Brief:{c['RESET']}      {event.brief}")
        if event.buy_signal:
            conf = event.buy_confidence
            if event.buy_signal == "BUY":
                if conf == 100:   label = "SURE PURCHASE"
                elif conf >= 95:  label = "VERY HIGH CONVICTION"
                elif conf >= 85:  label = "HIGH CONFIDENCE"
                elif conf >= 75:  label = "STRONG BUY"
                elif conf >= 65:  label = "SOLID CONVICTION"
                elif conf >= 50:  label = "RECOMMENDED PURCHASE"
                elif conf >= 41:  label = "BORDERLINE BUY"
                elif conf >= 26:  label = "SPECULATIVE BUY"
                elif conf >= 11:  label = "WEAK SIGNAL"
                else:             label = "VERY LOW CONVICTION"
                color = c['GREEN']
            elif event.buy_signal == "SELL":
                if conf >= 85:    label = "STRONG SELL"
                elif conf >= 65:  label = "CONFIDENT SELL"
                elif conf >= 50:  label = "RECOMMENDED SELL"
                else:             label = "SPECULATIVE SELL"
                color = c['RED']
            else:
                label = "HOLD — NEUTRAL"
                color = c['DIM']
            print(f"    {c['WHITE']}Signal:{c['RESET']}     {color}{event.buy_signal} — {label} ({conf}% confidence){c['RESET']}")
        if event.stock_availability:
            print(f"    {c['WHITE']}Platforms:{c['RESET']}")
            for ticker, info in event.stock_availability.items():
                platforms = [p for p, ok in [("Revolut", info.get("revolut")), ("XTB", info.get("xtb"))] if ok]
                status = "✓ " + ", ".join(platforms) if platforms else "✗ Not on major platforms"
                print(f"      {ticker}: {status} ({info.get('exchange', '?')})")
        print(f"    {c['WHITE']}Source:{c['RESET']}     {event.source} (Tier {event.source_tier})")
        print(f"    {c['WHITE']}Type:{c['RESET']}       {event.event_type.value}")
        print(f"    {c['WHITE']}Direction:{c['RESET']}  {self.format_direction_badge(event.direction)}")
        print(f"    {c['WHITE']}Sentiment:{c['RESET']}  {event.sentiment:+.3f}")
        print(f"    {c['WHITE']}Impact:{c['RESET']}     {self.format_score_bar(event.impact_score)}")
        print()
        if event.affected_tickers:
            print(f"    {c['WHITE']}Tickers:{c['RESET']}    {', '.join(event.affected_tickers)}")
        if event.affected_sectors:
            print(f"    {c['WHITE']}Sectors:{c['RESET']}    {', '.join(event.affected_sectors)}")
        if event.affected_etfs:
            print(f"    {c['WHITE']}ETFs:{c['RESET']}       {', '.join(event.affected_etfs)}")
        if event.supply_chain_exposure:
            print(f"    {c['MAGENTA']}Supply Chain:{c['RESET']} {', '.join(event.supply_chain_exposure[:8])}")
        if event.contagion_tickers:
            print(f"    {c['MAGENTA']}Contagion:{c['RESET']}  {', '.join(event.contagion_tickers[:8])}")
        print()

        if severity == "CRITICAL":
            await self._send_webhook(event)

        await broadcast_event(event)

    async def _send_webhook(self, event: ScoredEvent):
        dir_emoji = {"BULLISH": "🟢▲", "BEARISH": "🔴▼", "NEUTRAL": "⚪●"}
        event_dict = asdict(event)
        event_dict["event_type"] = event.event_type.value
        event_dict["direction"] = event.direction.value
        event_dict["urgency"] = event.urgency.value
        payload = {
            "content": (
                f"**{self.URGENCY_SYMBOLS.get(event.urgency.value, '')} "
                f"{event.urgency.value} — Impact: {event.impact_score}/100**\n"
                f"{dir_emoji.get(event.direction.value, '')} **{event.direction.value}**\n\n"
                f"📰 {event.headline}\n"
                f"🏷️ Tickers: {', '.join(event.affected_tickers) or 'MACRO'}\n"
                f"📊 Sectors: {', '.join(event.affected_sectors)}\n"
                f"📈 ETFs: {', '.join(event.affected_etfs)}\n"
                f"🔗 Supply Chain: {', '.join(event.supply_chain_exposure[:5]) or 'N/A'}\n"
                f"🔬 Type: {event.event_type.value} | Sentiment: {event.sentiment:+.3f}\n"
                f"⏱️ Source: {event.source} | Latency: {event.latency_ms:.1f}ms"
            ),
            "event_data": event_dict,
        }
        print(f"    📡 Webhook payload prepared ({len(json.dumps(payload))} bytes)")
        print()


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
# SECTION 7: MAIN ENGINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class NYSEImpactScreener:

    def __init__(self, alert_threshold: int = 0):
        self.reference_db = NYSEReferenceDB()
        self.entity_extractor = EntityExtractor(self.reference_db)
        self.scoring_engine = MarketImpactScoringEngine(self.reference_db)
        self.alert_dispatcher = AlertDispatcher()
        self.claude_scorer = ClaudeScorer(known_tickers=self.entity_extractor._all_known_tickers)
        self.availability_checker = StockAvailabilityChecker()
        from technical_indicators import TechnicalIndicators
        self.tech_indicators = TechnicalIndicators()
        self.db = EventDatabase()
        self.signal_tracker = SignalOutcomeTracker(self.db)
        self.rss = None
        self.alert_threshold = alert_threshold
        self.processed_count = 0
        self.alert_count = 0
        self.sector_heat: dict[str, list[int]] = defaultdict(list)

    def ingest_raw(self, raw: dict) -> RawNewsEvent:
        # Use original publication timestamp if available, fallback to now
        ts = raw.get("pub_ts") or time.time()
        return RawNewsEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=ts,
            source=raw["source"],
            source_tier=raw["source_tier"],
            headline=raw["headline"],
            body=raw.get("body", ""),
            raw_tickers=raw.get("tickers", []),
            url=raw.get("link", ""),
            ws_source=raw.get("ws_source", False),
        )

    async def process_event(self, raw: dict) -> Optional[ScoredEvent]:
        event = self.ingest_raw(raw)
        entities = self.entity_extractor.extract(event.headline, event.body)
        scored = self.scoring_engine.score_event(event, entities)

        # ── LOW-IMPACT FILTER — comment out the next 2 lines to re-enable low-impact events ──
        if scored.impact_score < 40:
            return None
        # ─────────────────────────────────────────────────────────────────────────────────────

        # Check stock availability + live price BEFORE Claude (free, no tokens)
        if scored.affected_tickers:
            availability = await self.availability_checker.check_tickers(scored.affected_tickers)
            scored.stock_availability = availability
            scored.price_data = {t: {"price": v.get("price"), "change_pct": v.get("change_pct")} for t, v in availability.items()}

        # Skip Claude for LOW impact events (score < 40)
        if scored.impact_score >= 40:
            scored = await self.claude_scorer.enhance(scored, event.headline, event.body)

            # Validate BUY signal > 50% against other sources
            if scored.buy_signal == "BUY" and scored.buy_confidence > 50 and self.rss:
                tickers_set = set(scored.affected_tickers)
                corroborating = [
                    a for a in self.rss._recent_articles
                    if a.get("source") != event.source
                    and any(t in a.get("headline", "") for t in tickers_set)
                ]
                if corroborating:
                    print(f"  [Claude] Validating BUY signal with {len(corroborating[:3])} corroborating source(s)...")
                    scored = await self.claude_scorer.validate_buy(scored, corroborating[:3])

            # Check availability + price for correlated_moves and ticker_signals tickers
            # that weren't already checked in the pre-Claude pass
            extra_tickers = set()
            extra_tickers.update(scored.correlated_moves)
            extra_tickers.update(scored.ticker_signals.keys())
            extra_tickers -= set(scored.stock_availability.keys())  # skip already checked
            if extra_tickers:
                extra_avail = await self.availability_checker.check_tickers(list(extra_tickers))
                scored.stock_availability.update(extra_avail)
                for t, v in extra_avail.items():
                    scored.price_data[t] = {"price": v.get("price"), "change_pct": v.get("change_pct")}

            # Fetch technical indicators for all affected tickers
            all_tickers = list(set(scored.affected_tickers) | set(scored.ticker_signals.keys()))
            if all_tickers:
                try:
                    scored.technical_data = await self.tech_indicators.get_indicators(all_tickers[:8])
                except Exception as e:
                    print(f"  [TechInd] Failed to fetch indicators: {e}")

            # ── POST-CLAUDE FILTER — drop if Claude re-scored below threshold ──
            if scored.impact_score < 40:
                return None

        self.processed_count += 1
        self.db.insert(scored)

        for sector in scored.affected_sectors:
            self.sector_heat[sector].append(scored.impact_score)
        if scored.impact_score >= self.alert_threshold:
            self.alert_count += 1
            await self.alert_dispatcher.dispatch(scored)
        return scored

    def print_sector_heatmap(self):
        """Print a sector activity heatmap from the session."""
        c = AlertDispatcher.COLORS
        print(f"    {c['WHITE']}{'─' * 72}{c['RESET']}")
        print(f"    {c['WHITE']}SECTOR HEATMAP{c['RESET']}")
        print(f"    {c['WHITE']}{'─' * 72}{c['RESET']}")

        sector_stats = []
        for sector, scores in self.sector_heat.items():
            avg = sum(scores) / len(scores)
            sector_stats.append((sector, len(scores), avg, max(scores)))

        sector_stats.sort(key=lambda x: -x[2])

        for sector, count, avg, peak in sector_stats:
            bar_len = int(avg / 5)
            if avg >= 80:
                color = c["CRITICAL"]
            elif avg >= 60:
                color = c["HIGH"]
            elif avg >= 40:
                color = c["MEDIUM"]
            else:
                color = c["LOW"]
            bar = f"{color}{'█' * bar_len}{'░' * (20 - bar_len)}{c['RESET']}"
            print(f"      {sector:22s} {bar} avg:{avg:5.1f}  peak:{peak:3d}  events:{count}")
        print()

    async def run_feed(self, feed: list[dict], delay: float = 0.8):
        c = AlertDispatcher.COLORS

        print()
        print(f"  {c['WHITE']}╔══════════════════════════════════════════════════════════════════╗{c['RESET']}")
        print(f"  {c['WHITE']}║      NYSE IMPACT NEWS SCREENER v2.0 — Engine Online             ║{c['RESET']}")
        print(f"  {c['WHITE']}║      Sectors: 16  │  Tickers: {len(self.reference_db.tickers):3d}  │  "
              f"Aliases: {len(self.reference_db.aliases):3d}          ║{c['RESET']}")
        vix = self.reference_db.market_state['vix']
        regime = self.reference_db.market_state['market_regime'].upper()
        print(f"  {c['WHITE']}║      Alert Threshold: {self.alert_threshold}/100  │  "
              f"VIX: {vix:.1f} ({regime})  │  Feed: {len(feed)} events   ║{c['RESET']}")
        print(f"  {c['WHITE']}╚══════════════════════════════════════════════════════════════════╝{c['RESET']}")
        print()

        results = []
        for item in feed:
            scored = await self.process_event(item)
            if scored:
                results.append(scored)
            await asyncio.sleep(delay)

        # Session Summary
        print()
        print(f"  {c['WHITE']}{'═' * 76}{c['RESET']}")
        print(f"  {c['WHITE']}SESSION SUMMARY{c['RESET']}")
        print(f"  {c['WHITE']}{'═' * 76}{c['RESET']}")
        print(f"    Events processed:  {self.processed_count}")
        print(f"    Alerts triggered:  {self.alert_count}")

        # Claude API usage stats
        usage = self.claude_scorer.usage_stats
        print(f"    Claude API calls:  {usage['total_calls']}  (skipped: {usage['calls_skipped']})")
        print(f"    Tokens used:       {usage['input_tokens']:,} in / {usage['output_tokens']:,} out")
        print(f"    Estimated cost:    ${usage['estimated_cost_usd']:.4f}")

        if results:
            scores = [r.impact_score for r in results]
            critical = [r for r in results if r.impact_score >= 80]
            high = [r for r in results if 60 <= r.impact_score < 80]
            bullish = [r for r in results if r.direction == Direction.BULLISH]
            bearish = [r for r in results if r.direction == Direction.BEARISH]

            print(f"    Score range:       {min(scores)} — {max(scores)}")
            print(f"    Average score:     {sum(scores) / len(scores):.1f}")
            print(f"    Critical: {len(critical)}  │  High: {len(high)}  │  "
                  f"Bullish: {len(bullish)}  │  Bearish: {len(bearish)}")
            print()

            # Sector Heatmap
            self.print_sector_heatmap()

            if critical:
                print(f"    {c['CRITICAL']}🚨 Critical Events Requiring Immediate Attention:{c['RESET']}")
                for ev in sorted(critical, key=lambda x: -x.impact_score):
                    dir_sym = "▲" if ev.direction == Direction.BULLISH else "▼" if ev.direction == Direction.BEARISH else "●"
                    tickers_str = ', '.join(ev.affected_tickers[:4]) or 'MACRO'
                    contagion_str = f" → +{len(ev.contagion_tickers)} contagion" if ev.contagion_tickers else ""
                    print(f"      [{ev.impact_score:3d}] {ev.urgency.value:8s} {dir_sym} "
                          f"{tickers_str:16s}{contagion_str:20s} │ {ev.headline[:52]}")
        print()

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    global _LIVE_MARKET_STATE, _SIGNAL_TRACKER_DB, _SIGNAL_TRACKER

    screener = NYSEImpactScreener(alert_threshold=0)
    rss = RSSFeed()
    ws_news = WebSocketNewsFeed()  # auto-detects providers from env vars
    screener.rss = rss
    await start_http_server(screener.db, tech_indicators=screener.tech_indicators)

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