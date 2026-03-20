"""
WebSocket / HTTP Server for the NYSE Impact Screener.
"""

import json
import asyncio
import websockets
import websockets.server
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
