"""
Backtesting Analytics API
─────────────────────────
Provides aggregated analytics endpoints for the Historical Backtesting Dashboard.
Compatible with both SQLite (EventDatabase) and Supabase (SupabaseDatabase).
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


def _is_supabase(db):
    """Check if db is a SupabaseDatabase (no .con attribute)."""
    return not hasattr(db, "con")


# ── Helper: fetch all signal_outcomes from Supabase ──────────────────────────

def _fetch_all_signals(db):
    """Fetch all signal_outcomes rows from Supabase."""
    result = db.client.table("signal_outcomes").select("*").execute()
    return result.data or []


def _fetch_all_signals_with_events(db):
    """Fetch all signal_outcomes and join with events headline/event_type/source."""
    signals = db.client.table("signal_outcomes").select("*").execute().data or []
    if not signals:
        return []
    # Fetch all events for joining
    event_ids = list(set(s["event_id"] for s in signals))
    events_map = {}
    # Supabase has a query size limit, batch if needed
    for i in range(0, len(event_ids), 50):
        batch = event_ids[i:i+50]
        result = db.client.table("events").select(
            "event_id, headline, event_type, source"
        ).in_("event_id", batch).execute()
        for e in (result.data or []):
            events_map[e["event_id"]] = e
    # Join
    for s in signals:
        ev = events_map.get(s["event_id"], {})
        s["headline"] = ev.get("headline", "")
        s["event_type"] = ev.get("event_type", "")
        s["source"] = ev.get("source", "")
    return signals


# ── Overview ─────────────────────────────────────────────────────────────────

async def overview_handler(request):
    """Overall stats: total signals, win rates, avg returns per checkpoint."""
    db = request.app["db"]

    if not _is_supabase(db):
        # SQLite path (original)
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
                f"AVG(pct_{cp}), MIN(pct_{cp}), MAX(pct_{cp}) "
                f"FROM signal_outcomes WHERE pct_{cp} IS NOT NULL"
            ).fetchone()
            filled, wins, losses, flats, avg_ret, min_ret, max_ret = row
            checkpoints[cp] = {
                "filled": filled or 0, "wins": wins or 0, "losses": losses or 0, "flats": flats or 0,
                "win_rate": round((wins / filled) * 100, 1) if filled else 0,
                "avg_return": round(avg_ret, 2) if avg_ret else 0,
                "min_return": round(min_ret, 2) if min_ret else 0,
                "max_return": round(max_ret, 2) if max_ret else 0,
            }
        by_signal = {}
        for sig in ("BUY", "SELL"):
            row = con.execute(
                "SELECT COUNT(*), AVG(confidence) FROM signal_outcomes WHERE signal = ?", (sig,)
            ).fetchone()
            by_signal[sig.lower()] = {"count": row[0] or 0, "avg_confidence": round(row[1], 1) if row[1] else 0}
        return _json_response({
            "total_signals": total, "completed_signals": completed,
            "pending_signals": total - completed, "checkpoints": checkpoints, "by_signal": by_signal,
        })

    # Supabase path
    rows = _fetch_all_signals(db)
    total = len(rows)
    completed = sum(1 for r in rows if r.get("completed"))

    checkpoints = {}
    for cp in ("1h", "4h", "1d", "1w"):
        pct_key = f"pct_{cp}"
        out_key = f"outcome_{cp}"
        valid = [r for r in rows if r.get(pct_key) is not None]
        filled = len(valid)
        wins = sum(1 for r in valid if r.get(out_key) == "WIN")
        losses = sum(1 for r in valid if r.get(out_key) == "LOSS")
        flats = sum(1 for r in valid if r.get(out_key) == "FLAT")
        pcts = [r[pct_key] for r in valid]
        checkpoints[cp] = {
            "filled": filled, "wins": wins, "losses": losses, "flats": flats,
            "win_rate": round((wins / filled) * 100, 1) if filled else 0,
            "avg_return": round(sum(pcts) / filled, 2) if filled else 0,
            "min_return": round(min(pcts), 2) if pcts else 0,
            "max_return": round(max(pcts), 2) if pcts else 0,
        }

    by_signal = {}
    for sig in ("BUY", "SELL"):
        sig_rows = [r for r in rows if r.get("signal") == sig]
        confs = [r["confidence"] for r in sig_rows if r.get("confidence") is not None]
        by_signal[sig.lower()] = {
            "count": len(sig_rows),
            "avg_confidence": round(sum(confs) / len(confs), 1) if confs else 0,
        }

    return _json_response({
        "total_signals": total, "completed_signals": completed,
        "pending_signals": total - completed, "checkpoints": checkpoints, "by_signal": by_signal,
    })


# ── Win Rate by Event Type ───────────────────────────────────────────────────

async def by_event_type_handler(request):
    db = request.app["db"]
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    if not _is_supabase(db):
        con = db.con
        rows = con.execute(
            f"SELECT e.event_type, COUNT(*), "
            f"SUM(CASE WHEN s.outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN s.outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
            f"AVG(s.pct_{cp}), AVG(s.confidence) "
            f"FROM signal_outcomes s JOIN events e ON s.event_id = e.event_id "
            f"WHERE s.pct_{cp} IS NOT NULL GROUP BY e.event_type ORDER BY COUNT(*) DESC"
        ).fetchall()
        results = []
        for row in rows:
            event_type, total, wins, losses, avg_ret, avg_conf = row
            results.append({
                "event_type": event_type or "unknown", "total": total,
                "wins": wins or 0, "losses": losses or 0,
                "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
                "avg_return": round(avg_ret, 2) if avg_ret else 0,
                "avg_confidence": round(avg_conf, 1) if avg_conf else 0,
            })
        return _json_response({"checkpoint": cp, "data": results})

    # Supabase
    all_rows = _fetch_all_signals_with_events(db)
    pct_key = f"pct_{cp}"
    out_key = f"outcome_{cp}"
    valid = [r for r in all_rows if r.get(pct_key) is not None]

    grouped = {}
    for r in valid:
        et = r.get("event_type") or "unknown"
        grouped.setdefault(et, []).append(r)

    results = []
    for et, group in sorted(grouped.items(), key=lambda x: -len(x[1])):
        total = len(group)
        wins = sum(1 for r in group if r.get(out_key) == "WIN")
        losses = sum(1 for r in group if r.get(out_key) == "LOSS")
        avg_ret = sum(r[pct_key] for r in group) / total if total else 0
        confs = [r["confidence"] for r in group if r.get("confidence") is not None]
        avg_conf = sum(confs) / len(confs) if confs else 0
        results.append({
            "event_type": et, "total": total, "wins": wins, "losses": losses,
            "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2), "avg_confidence": round(avg_conf, 1),
        })

    return _json_response({"checkpoint": cp, "data": results})


# ── Confidence Calibration ───────────────────────────────────────────────────

async def confidence_calibration_handler(request):
    db = request.app["db"]
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    if not _is_supabase(db):
        con = db.con
        buckets = []
        for low in range(0, 100, 10):
            high = low + 10
            row = con.execute(
                f"SELECT COUNT(*), SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), AVG(pct_{cp}) "
                f"FROM signal_outcomes WHERE confidence >= ? AND confidence < ? AND pct_{cp} IS NOT NULL",
                (low, high)
            ).fetchone()
            total, wins, avg_ret = row
            buckets.append({
                "bucket": f"{low}-{high}%", "bucket_low": low, "bucket_high": high,
                "expected_midpoint": (low + high) / 2, "total": total or 0, "wins": wins or 0,
                "actual_win_rate": round((wins / total) * 100, 1) if total and wins else 0,
                "avg_return": round(avg_ret, 2) if avg_ret else 0,
            })
        return _json_response({"checkpoint": cp, "data": buckets})

    # Supabase
    all_rows = _fetch_all_signals(db)
    pct_key = f"pct_{cp}"
    out_key = f"outcome_{cp}"
    valid = [r for r in all_rows if r.get(pct_key) is not None]

    buckets = []
    for low in range(0, 100, 10):
        high = low + 10
        bucket_rows = [r for r in valid if low <= (r.get("confidence") or 0) < high]
        total = len(bucket_rows)
        wins = sum(1 for r in bucket_rows if r.get(out_key) == "WIN")
        avg_ret = sum(r[pct_key] for r in bucket_rows) / total if total else 0
        buckets.append({
            "bucket": f"{low}-{high}%", "bucket_low": low, "bucket_high": high,
            "expected_midpoint": (low + high) / 2, "total": total, "wins": wins,
            "actual_win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2),
        })

    return _json_response({"checkpoint": cp, "data": buckets})


# ── P&L Curve ────────────────────────────────────────────────────────────────

async def pnl_curve_handler(request):
    db = request.app["db"]
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    if not _is_supabase(db):
        con = db.con
        rows = con.execute(
            f"SELECT s.entry_time, s.ticker, s.signal, s.confidence, "
            f"s.entry_price, s.price_{cp}, s.pct_{cp}, s.outcome_{cp}, e.headline "
            f"FROM signal_outcomes s LEFT JOIN events e ON s.event_id = e.event_id "
            f"WHERE s.pct_{cp} IS NOT NULL ORDER BY s.entry_time ASC"
        ).fetchall()
        cumulative = 0.0
        curve = []
        wins = 0
        losses = 0
        for row in rows:
            entry_time, ticker, signal, confidence, entry_price, exit_price, pct, outcome, headline = row
            actual_pct = -pct if signal == "SELL" else pct
            cumulative += actual_pct
            if outcome == "WIN": wins += 1
            elif outcome == "LOSS": losses += 1
            curve.append({
                "entry_time": entry_time, "ticker": ticker, "signal": signal,
                "confidence": confidence, "entry_price": entry_price, "exit_price": exit_price,
                "pct_return": round(actual_pct, 2), "cumulative_pct": round(cumulative, 2),
                "outcome": outcome, "headline": headline or "",
                "running_wins": wins, "running_losses": losses,
                "running_win_rate": round((wins / (wins + losses)) * 100, 1) if (wins + losses) else 0,
            })
        return _json_response({"checkpoint": cp, "data": curve})

    # Supabase
    pct_key = f"pct_{cp}"
    out_key = f"outcome_{cp}"
    price_key = f"price_{cp}"
    all_rows = _fetch_all_signals_with_events(db)
    valid = [r for r in all_rows if r.get(pct_key) is not None]
    valid.sort(key=lambda r: r.get("entry_time") or 0)

    cumulative = 0.0
    curve = []
    wins = 0
    losses = 0
    for r in valid:
        pct = r[pct_key]
        signal = r.get("signal", "")
        outcome = r.get(out_key, "")
        actual_pct = -pct if signal == "SELL" else pct
        cumulative += actual_pct
        if outcome == "WIN": wins += 1
        elif outcome == "LOSS": losses += 1
        curve.append({
            "entry_time": r.get("entry_time"), "ticker": r.get("ticker"),
            "signal": signal, "confidence": r.get("confidence"),
            "entry_price": r.get("entry_price"), "exit_price": r.get(price_key),
            "pct_return": round(actual_pct, 2), "cumulative_pct": round(cumulative, 2),
            "outcome": outcome, "headline": r.get("headline", ""),
            "running_wins": wins, "running_losses": losses,
            "running_win_rate": round((wins / (wins + losses)) * 100, 1) if (wins + losses) else 0,
        })

    return _json_response({"checkpoint": cp, "data": curve})


# ── By Ticker ────────────────────────────────────────────────────────────────

async def by_ticker_handler(request):
    db = request.app["db"]
    cp = request.query.get("checkpoint", "1d")
    if cp not in ("1h", "4h", "1d", "1w"):
        cp = "1d"

    if not _is_supabase(db):
        con = db.con
        rows = con.execute(
            f"SELECT ticker, COUNT(*), "
            f"SUM(CASE WHEN outcome_{cp}='WIN' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN outcome_{cp}='LOSS' THEN 1 ELSE 0 END), "
            f"AVG(pct_{cp}), SUM(pct_{cp}) "
            f"FROM signal_outcomes WHERE pct_{cp} IS NOT NULL "
            f"GROUP BY ticker ORDER BY SUM(pct_{cp}) DESC"
        ).fetchall()
        results = []
        for row in rows:
            ticker, total, wins, losses, avg_ret, total_ret = row
            results.append({
                "ticker": ticker, "total": total, "wins": wins or 0, "losses": losses or 0,
                "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
                "avg_return": round(avg_ret, 2) if avg_ret else 0,
                "total_return": round(total_ret, 2) if total_ret else 0,
            })
        return _json_response({"checkpoint": cp, "data": results})

    # Supabase
    pct_key = f"pct_{cp}"
    out_key = f"outcome_{cp}"
    all_rows = _fetch_all_signals(db)
    valid = [r for r in all_rows if r.get(pct_key) is not None]

    grouped = {}
    for r in valid:
        t = r.get("ticker", "?")
        grouped.setdefault(t, []).append(r)

    results = []
    for ticker, group in grouped.items():
        total = len(group)
        wins = sum(1 for r in group if r.get(out_key) == "WIN")
        losses = sum(1 for r in group if r.get(out_key) == "LOSS")
        pcts = [r[pct_key] for r in group]
        avg_ret = sum(pcts) / total if total else 0
        total_ret = sum(pcts)
        results.append({
            "ticker": ticker, "total": total, "wins": wins, "losses": losses,
            "win_rate": round((wins / total) * 100, 1) if total and wins else 0,
            "avg_return": round(avg_ret, 2), "total_return": round(total_ret, 2),
        })
    results.sort(key=lambda x: x["total_return"], reverse=True)

    return _json_response({"checkpoint": cp, "data": results})


# ── Signal History ───────────────────────────────────────────────────────────

async def signal_history_handler(request):
    db = request.app["db"]
    limit = min(int(request.query.get("limit", 100)), 500)
    offset = int(request.query.get("offset", 0))

    if not _is_supabase(db):
        con = db.con
        rows = con.execute(
            "SELECT s.event_id, s.ticker, s.signal, s.confidence, "
            "s.entry_price, s.entry_time, "
            "s.price_1h, s.pct_1h, s.outcome_1h, "
            "s.price_4h, s.pct_4h, s.outcome_4h, "
            "s.price_1d, s.pct_1d, s.outcome_1d, "
            "s.price_1w, s.pct_1w, s.outcome_1w, "
            "s.completed, e.headline, e.event_type, e.source "
            "FROM signal_outcomes s LEFT JOIN events e ON s.event_id = e.event_id "
            "ORDER BY s.entry_time DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        total_count = con.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()[0]
        results = []
        for row in rows:
            results.append({
                "event_id": row[0], "ticker": row[1], "signal": row[2],
                "confidence": row[3], "entry_price": row[4], "entry_time": row[5],
                "checkpoints": {
                    "1h": {"price": row[6], "pct": row[7], "outcome": row[8]},
                    "4h": {"price": row[9], "pct": row[10], "outcome": row[11]},
                    "1d": {"price": row[12], "pct": row[13], "outcome": row[14]},
                    "1w": {"price": row[15], "pct": row[16], "outcome": row[17]},
                },
                "completed": bool(row[18]),
                "headline": row[19] or "", "event_type": row[20] or "", "source": row[21] or "",
            })
        return _json_response({"total": total_count, "limit": limit, "offset": offset, "data": results})

    # Supabase
    all_rows = _fetch_all_signals_with_events(db)
    all_rows.sort(key=lambda r: r.get("entry_time") or 0, reverse=True)
    total_count = len(all_rows)
    page = all_rows[offset:offset + limit]

    results = []
    for r in page:
        results.append({
            "event_id": r.get("event_id"), "ticker": r.get("ticker"),
            "signal": r.get("signal"), "confidence": r.get("confidence"),
            "entry_price": r.get("entry_price"), "entry_time": r.get("entry_time"),
            "checkpoints": {
                "1h": {"price": r.get("price_1h"), "pct": r.get("pct_1h"), "outcome": r.get("outcome_1h")},
                "4h": {"price": r.get("price_4h"), "pct": r.get("pct_4h"), "outcome": r.get("outcome_4h")},
                "1d": {"price": r.get("price_1d"), "pct": r.get("pct_1d"), "outcome": r.get("outcome_1d")},
                "1w": {"price": r.get("price_1w"), "pct": r.get("pct_1w"), "outcome": r.get("outcome_1w")},
            },
            "completed": bool(r.get("completed")),
            "headline": r.get("headline", ""), "event_type": r.get("event_type", ""),
            "source": r.get("source", ""),
        })

    return _json_response({"total": total_count, "limit": limit, "offset": offset, "data": results})
