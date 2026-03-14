"""
Stock Chart API
───────────────
Serves historical OHLCV price data for charting via yfinance.
Supports multiple time periods with appropriate intervals.
"""

import asyncio
import json
import time
import yfinance as yf
from aiohttp import web


CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

# Period → yfinance params
PERIOD_CONFIG = {
    "1d":  {"period": "1d",  "interval": "5m"},
    "5d":  {"period": "5d",  "interval": "15m"},
    "1mo": {"period": "1mo", "interval": "1h"},
    "3mo": {"period": "3mo", "interval": "1d"},
    "6mo": {"period": "6mo", "interval": "1d"},
    "1y":  {"period": "1y",  "interval": "1d"},
    "5y":  {"period": "5y",  "interval": "1wk"},
    "max": {"period": "max", "interval": "1mo"},
}

# Cache: {(ticker, period): {"data": [...], "ts": float}}
_cache = {}
CACHE_TTL = 120  # 2 minutes


def _yf_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def _fetch_chart_data(ticker: str, period: str) -> dict:
    """Fetch OHLCV data from yfinance (blocking)."""
    cfg = PERIOD_CONFIG.get(period)
    if not cfg:
        return {"error": f"Invalid period: {period}"}

    symbol = _yf_symbol(ticker)
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period=cfg["period"], interval=cfg["interval"])

        if hist is None or hist.empty:
            return {"ticker": ticker, "period": period, "data": [], "info": {}}

        # Get basic info
        try:
            fast = tk.fast_info
            info = {
                "name": getattr(fast, "short_name", ticker) if hasattr(fast, "short_name") else ticker,
                "price": round(getattr(fast, "last_price", 0), 2),
                "prev_close": round(getattr(fast, "previous_close", 0), 2),
                "market_cap": getattr(fast, "market_cap", None),
                "currency": getattr(fast, "currency", "USD"),
            }
            if info["prev_close"] and info["price"]:
                info["change"] = round(info["price"] - info["prev_close"], 2)
                info["change_pct"] = round((info["change"] / info["prev_close"]) * 100, 2)
        except Exception:
            info = {"name": ticker, "price": 0, "currency": "USD"}

        # Convert to list of candles
        candles = []
        for idx, row in hist.iterrows():
            ts = int(idx.timestamp())
            candles.append({
                "t": ts,
                "o": round(row["Open"], 2),
                "h": round(row["High"], 2),
                "l": round(row["Low"], 2),
                "c": round(row["Close"], 2),
                "v": int(row["Volume"]),
            })

        # Compute period stats
        if len(candles) >= 2:
            first_close = candles[0]["c"]
            last_close = candles[-1]["c"]
            period_change = round(last_close - first_close, 2)
            period_change_pct = round((period_change / first_close) * 100, 2) if first_close else 0
            period_high = max(c["h"] for c in candles)
            period_low = min(c["l"] for c in candles)
            total_volume = sum(c["v"] for c in candles)
            avg_volume = int(total_volume / len(candles))
        else:
            period_change = 0
            period_change_pct = 0
            period_high = candles[0]["h"] if candles else 0
            period_low = candles[0]["l"] if candles else 0
            total_volume = candles[0]["v"] if candles else 0
            avg_volume = total_volume

        return {
            "ticker": ticker,
            "period": period,
            "interval": cfg["interval"],
            "data": candles,
            "info": info,
            "stats": {
                "period_change": period_change,
                "period_change_pct": period_change_pct,
                "period_high": round(period_high, 2),
                "period_low": round(period_low, 2),
                "total_volume": total_volume,
                "avg_volume": avg_volume,
            },
        }

    except Exception as e:
        print(f"  [ChartAPI] Error fetching {ticker}/{period}: {e}")
        return {"ticker": ticker, "period": period, "data": [], "error": str(e)}


async def chart_handler(request):
    """GET /api/chart?ticker=AAPL&period=1mo"""
    ticker = request.query.get("ticker", "").strip().upper()
    period = request.query.get("period", "1mo").strip()

    if not ticker:
        return web.Response(
            text=json.dumps({"error": "ticker parameter required"}),
            content_type="application/json",
            headers=CORS_HEADERS,
            status=400,
        )

    if period not in PERIOD_CONFIG:
        return web.Response(
            text=json.dumps({"error": f"Invalid period. Use: {', '.join(PERIOD_CONFIG.keys())}"}),
            content_type="application/json",
            headers=CORS_HEADERS,
            status=400,
        )

    # Check cache
    cache_key = (ticker, period)
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached["ts"]) < CACHE_TTL:
        return web.Response(
            text=json.dumps(cached["data"]),
            content_type="application/json",
            headers=CORS_HEADERS,
        )

    # Fetch in thread
    data = await asyncio.to_thread(_fetch_chart_data, ticker, period)

    # Cache result
    _cache[cache_key] = {"data": data, "ts": now}

    return web.Response(
        text=json.dumps(data),
        content_type="application/json",
        headers=CORS_HEADERS,
    )


def setup_chart_routes(app: web.Application):
    """Register chart API routes."""
    app.router.add_get("/api/chart", chart_handler)
