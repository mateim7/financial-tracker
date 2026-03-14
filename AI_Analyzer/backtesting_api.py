"""
Backtesting Analytics API
─────────────────────────
Provides aggregated analytics endpoints for the Historical Backtesting Dashboard.
Queries the existing SQLite database (signal_outcomes + events tables).
"""

import json
from aiohttp import web


def setup_backtesting_routes(app: web.Application):
    """Register all backtesting API routes on the aiohttp app."""
    app.router.add_get("/api/backtesting/overview", overview_handler)
    app.router.add_get("/api/backtesting/by-event-type", by_event_type_handler)
    app.router.add_get("/api/backtesting/confidence-calibration", confidence_calibration_handler)
    app.router.add_get("/api/backtesting/pnl-curve", pnl_curve_handler)
    app.router.add_get("/api/backtesting/by-ticker", by_ticker_handler)
    app.router.add_get("/api/backtesting/signal-history", signal_history_handler)


CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


def _json_response(data):
    return web.Response(
        text=json.dumps(data),
        content_type="application/json",
        headers=CORS_HEADERS,
    )


# ── Overview ─────────────────────────────────────────────────────────────────

async def overview_handler(request):
    """Overall stats: total signals, win rates, avg returns per checkpoint."""
    db = request.app["db"]
    con = db.con

    total = con.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
    completed = con.execute("SELECT COUNT(*) FROM signal_outcomes WHERE completed = 1").fetchone()[0]

    checkpoints = {}
    for cp in ("1h", "4h", "1d", "1w"):
        row = con.execute(
            f"SELECT COUNT(*), "
            f"SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN outcome_{cp}='FLAT' THEN 1 ELSE 0 END), "
            f"AVG(pct_{cp}), "
            f"MIN(pct_{cp}), "
            f"MAX(pct_{cp}) "
            f"FROM signal_outcomes WHERE pct_{cp} IS NOT NULL"
        ).fetchone()
        filled, wins, losses, flats, avg_ret, min_ret, max_ret = row
        checkpoints[cp] = {
            "filled": filled or 0,
            "wins": wins or 0,
            "losses": losses or 0,
            "flats": flats or 0,
            "win_rate": round((wins / filled) * 100, 1) if filled else 0,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
            "min_return": round(min_ret, 2) if min_ret else 0,
            "max_return": round(max_ret, 2) if max_ret else 0,
        }

    # Buy vs Sell breakdown
    by_signal = {}
    for sig in ("BUY", "SELL"):
        row = con.execute(
            "SELECT COUNT(*), AVG(confidence) FROM signal_outcomes WHERE signal = ?",
            (sig,)
        ).fetchone()
        by_signal[sig.lower()] = {
            "count": row[0] or 0,
            "avg_confidence": round(row[1], 1) if row[1] else 0,
        }

    return _json_response({
        "total_signals": total,
        "completed_signals": completed,
        "pending_signals": total - completed,
        "checkpoints": checkpoints,
        "by_signal": by_signal,
    })


# ── Win Rate by Event Type ───────────────────────────────────────────────────

async def by_event_type_handler(request):
    """Win rate and avg return grouped by event_type from the events table."""
    db = request.app["db"]
    con = db.con
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    rows = con.execute(
        f"SELECT e.event_type, "
        f"COUNT(*), "
        f"SUM(CASE WHEN s.outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN s.outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
        f"AVG(s.pct_{cp}), "
        f"AVG(s.confidence) "
        f"FROM signal_outcomes s "
        f"JOIN events e ON s.event_id = e.event_id "
        f"WHERE s.pct_{cp} IS NOT NULL "
        f"GROUP BY e.event_type "
        f"ORDER BY COUNT(*) DESC"
    ).fetchall()

    results = []
    for row in rows:
        event_type, total, wins, losses, avg_ret, avg_conf = row
        results.append({
            "event_type": event_type or "unknown",
            "total": total,
            "wins": wins or 0,
            "losses": losses or 0,
            "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
            "avg_confidence": round(avg_conf, 1) if avg_conf else 0,
        })

    return _json_response({"checkpoint": cp, "data": results})


# ── Confidence Calibration ───────────────────────────────────────────────────

async def confidence_calibration_handler(request):
    """
    Groups signals into confidence buckets (0-10, 10-20, ..., 90-100)
    and shows actual win rate per bucket vs expected.
    """
    db = request.app["db"]
    con = db.con
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    buckets = []
    for low in range(0, 100, 10):
        high = low + 10
        row = con.execute(
            f"SELECT COUNT(*), "
            f"SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
            f"AVG(pct_{cp}) "
            f"FROM signal_outcomes "
            f"WHERE confidence >= ? AND confidence < ? AND pct_{cp} IS NOT NULL",
            (low, high)
        ).fetchone()
        total, wins, avg_ret = row
        buckets.append({
            "bucket": f"{low}-{high}%",
            "bucket_low": low,
            "bucket_high": high,
            "expected_midpoint": (low + high) / 2,
            "total": total or 0,
            "wins": wins or 0,
            "actual_win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
        })

    return _json_response({"checkpoint": cp, "data": buckets})


# ── P&L Curve ────────────────────────────────────────────────────────────────

async def pnl_curve_handler(request):
    """
    Cumulative P&L curve over time. Each signal contributes its pct return
    at the selected checkpoint, ordered by entry_time.
    """
    db = request.app["db"]
    con = db.con
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    rows = con.execute(
        f"SELECT s.entry_time, s.ticker, s.signal, s.confidence, "
        f"s.entry_price, s.price_{cp}, s.pct_{cp}, s.outcome_{cp}, "
        f"e.headline "
        f"FROM signal_outcomes s "
        f"LEFT JOIN events e ON s.event_id = e.event_id "
        f"WHERE s.pct_{cp} IS NOT NULL "
        f"ORDER BY s.entry_time ASC"
    ).fetchall()

    cumulative = 0.0
    curve = []
    wins = 0
    losses = 0
    for row in rows:
        entry_time, ticker, signal, confidence, entry_price, exit_price, pct, outcome, headline = row
        # For SELL signals, profit is inverted (price going down = profit)
        actual_pct = -pct if signal == "SELL" else pct
        cumulative += actual_pct
        if outcome == "WIN":
            wins += 1
        elif outcome == "LOSS":
            losses += 1

        curve.append({
            "entry_time": entry_time,
            "ticker": ticker,
            "signal": signal,
            "confidence": confidence,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pct_return": round(actual_pct, 2),
            "cumulative_pct": round(cumulative, 2),
            "outcome": outcome,
            "headline": headline or "",
            "running_wins": wins,
            "running_losses": losses,
            "running_win_rate": round((wins / (wins + losses)) * 100, 1) if (wins + losses) else 0,
        })

    return _json_response({"checkpoint": cp, "data": curve})


# ── By Ticker ────────────────────────────────────────────────────────────────

async def by_ticker_handler(request):
    """Performance breakdown per ticker."""
    db = request.app["db"]
    con = db.con
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    rows = con.execute(
        f"SELECT ticker, "
        f"COUNT(*), "
        f"SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
        f"AVG(pct_{cp}), "
        f"SUM(pct_{cp}) "
        f"FROM signal_outcomes "
        f"WHERE pct_{cp} IS NOT NULL "
        f"GROUP BY ticker "
        f"ORDER BY SUM(pct_{cp}) DESC"
    ).fetchall()

    results = []
    for row in rows:
        ticker, total, wins, losses, avg_ret, total_ret = row
        results.append({
            "ticker": ticker,
            "total": total,
            "wins": wins or 0,
            "losses": losses or 0,
            "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2) if avg_ret else 0,
            "total_return": round(total_ret, 2) if total_ret else 0,
        })

    return _json_response({"checkpoint": cp, "data": results})


# ── Signal History ───────────────────────────────────────────────────────────

async def signal_history_handler(request):
    """Full signal history with all checkpoint data, paginated."""
    db = request.app["db"]
    con = db.con
    limit = min(int(request.query.get("limit", 100)), 500)
    offset = int(request.query.get("offset", 0))

    rows = con.execute(
        "SELECT s.event_id, s.ticker, s.signal, s.confidence, "
        "s.entry_price, s.entry_time, "
        "s.price_1h, s.pct_1h, s.outcome_1h, "
        "s.price_4h, s.pct_4h, s.outcome_4h, "
        "s.price_1d, s.pct_1d, s.outcome_1d, "
        "s.price_1w, s.pct_1w, s.outcome_1w, "
        "s.completed, "
        "e.headline, e.event_type, e.source "
        "FROM signal_outcomes s "
        "LEFT JOIN events e ON s.event_id = e.event_id "
        "ORDER BY s.entry_time DESC "
        "LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()

    total_count = con.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]

    results = []
    for row in rows:
        results.append({
            "event_id": row[0],
            "ticker": row[1],
            "signal": row[2],
            "confidence": row[3],
            "entry_price": row[4],
            "entry_time": row[5],
            "checkpoints": {
                "1h": {"price": row[6], "pct": row[7], "outcome": row[8]},
                "4h": {"price": row[9], "pct": row[10], "outcome": row[11]},
                "1d": {"price": row[12], "pct": row[13], "outcome": row[14]},
                "1w": {"price": row[15], "pct": row[16], "outcome": row[17]},
            },
            "completed": bool(row[18]),
            "headline": row[19] or "",
            "event_type": row[20] or "",
            "source": row[21] or "",
        })

    return _json_response({
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "data": results,
    })
