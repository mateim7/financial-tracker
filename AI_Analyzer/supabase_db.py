"""
Supabase Database Client for Financial Tracker
Drop-in replacement for the SQLite EventDatabase.

Usage:
    from supabase_db import SupabaseDatabase
    db = SupabaseDatabase()  # reads SUPABASE_URL and SUPABASE_KEY from env

Requires:
    pip install supabase

Environment variables:
    SUPABASE_URL=https://yzwasqzpkzslqkfggwgg.supabase.co
    SUPABASE_KEY=your_service_role_key
"""

import os
import json
import time
import io
import csv
from supabase import create_client, Client


class SupabaseDatabase:
    """Mirrors every method of EventDatabase (SQLite) but writes to Supabase PostgreSQL."""

    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in environment variables.\n"
                "Add them to ~/.bashrc:\n"
                "  export SUPABASE_URL=\"https://yzwasqzpkzslqkfggwgg.supabase.co\"\n"
                "  export SUPABASE_KEY=\"your_service_role_key\""
            )
        self.client: Client = create_client(url, key)
        self._ensure_tables()
        count = self.count()
        print(f"  [Supabase] Database ready ({count} events stored)")

    # ── Table Creation ────────────────────────────────────────────────────────

    def _ensure_tables(self):
        """Create tables if they don't exist via Supabase RPC (raw SQL)."""
        create_events_sql = """
        CREATE TABLE IF NOT EXISTS events (
            event_id           TEXT PRIMARY KEY,
            timestamp          DOUBLE PRECISION,
            headline           TEXT,
            source             TEXT,
            source_tier        INTEGER,
            event_type         TEXT,
            direction          TEXT,
            sentiment          DOUBLE PRECISION,
            impact_score       INTEGER,
            urgency            TEXT,
            brief              TEXT,
            buy_signal         TEXT,
            buy_confidence     INTEGER,
            affected_tickers   TEXT,
            affected_sectors   TEXT,
            affected_etfs      TEXT,
            stock_availability TEXT,
            latency_ms         DOUBLE PRECISION
        );
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_impact_score ON events(impact_score);
        """

        create_signals_sql = """
        CREATE TABLE IF NOT EXISTS signal_outcomes (
            event_id           TEXT,
            ticker             TEXT,
            signal             TEXT,
            confidence         INTEGER,
            entry_price        DOUBLE PRECISION,
            entry_time         DOUBLE PRECISION,
            price_1h           DOUBLE PRECISION,
            price_4h           DOUBLE PRECISION,
            price_1d           DOUBLE PRECISION,
            price_1w           DOUBLE PRECISION,
            pct_1h             DOUBLE PRECISION,
            pct_4h             DOUBLE PRECISION,
            pct_1d             DOUBLE PRECISION,
            pct_1w             DOUBLE PRECISION,
            outcome_1h         TEXT,
            outcome_4h         TEXT,
            outcome_1d         TEXT,
            outcome_1w         TEXT,
            completed          INTEGER DEFAULT 0,
            PRIMARY KEY (event_id, ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_outcomes_completed ON signal_outcomes(completed);
        """

        try:
            self.client.rpc("exec_sql", {"query": create_events_sql}).execute()
            self.client.rpc("exec_sql", {"query": create_signals_sql}).execute()
        except Exception:
            # Tables likely already exist or RPC not set up — try a test query instead
            try:
                self.client.table("events").select("event_id").limit(1).execute()
                self.client.table("signal_outcomes").select("event_id").limit(1).execute()
                print("  [Supabase] Tables verified via query")
            except Exception as e:
                print(f"  [Supabase] WARNING: Could not verify tables: {e}")
                print("  [Supabase] Please create tables manually in the Supabase SQL Editor.")
                print("  [Supabase] SQL is printed below:\n")
                print(create_events_sql)
                print(create_signals_sql)

    # ── Events ────────────────────────────────────────────────────────────────

    def insert(self, event):
        """Insert a scored event. Mirrors EventDatabase.insert()."""
        try:
            def _native(v):
                """Convert numpy/torch scalars to Python natives for JSON."""
                return v.item() if hasattr(v, 'item') else v

            data = {
                "event_id": event.event_id,
                "timestamp": _native(event.timestamp),
                "headline": event.headline,
                "source": event.source,
                "source_tier": _native(event.source_tier),
                "event_type": event.event_type.value,
                "direction": event.direction.value,
                "sentiment": _native(event.sentiment),
                "impact_score": _native(event.impact_score),
                "urgency": event.urgency.value,
                "brief": event.brief,
                "buy_signal": event.buy_signal,
                "buy_confidence": _native(event.buy_confidence),
                "affected_tickers": json.dumps(event.affected_tickers),
                "affected_sectors": json.dumps(event.affected_sectors),
                "affected_etfs": json.dumps(event.affected_etfs),
                "stock_availability": json.dumps(event.stock_availability),
                "latency_ms": _native(event.latency_ms),
            }
            self.client.table("events").upsert(data).execute()
        except Exception as e:
            print(f"  [Supabase] Insert error: {e}")

    def count(self) -> int:
        """Count total events."""
        try:
            result = self.client.table("events").select("event_id", count="exact").execute()
            return result.count or 0
        except Exception:
            return 0

    def get_csv(self) -> str:
        """Export all events as CSV."""
        result = self.client.table("events").select("*").order("timestamp", desc=True).execute()
        if not result.data:
            return ""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(result.data[0].keys())
        for row in result.data:
            w.writerow(row.values())
        return buf.getvalue()

    def get_json(self) -> str:
        """Export all events as JSON."""
        result = self.client.table("events").select("*").order("timestamp", desc=True).execute()
        return json.dumps(result.data or [], indent=2)

    def get_recent_events(self, limit: int = 100, max_age_seconds: int = 3600) -> list[dict]:
        """Get recent events formatted for the frontend (same shape as WS broadcast)."""
        cutoff = time.time() - max_age_seconds
        result = (
            self.client.table("events")
            .select("*")
            .gte("timestamp", cutoff)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        results = []
        for row in (result.data or []):
            tickers = json.loads(row["affected_tickers"]) if row.get("affected_tickers") else []
            sectors = json.loads(row["affected_sectors"]) if row.get("affected_sectors") else []
            etfs = json.loads(row["affected_etfs"]) if row.get("affected_etfs") else []
            avail = json.loads(row["stock_availability"]) if row.get("stock_availability") else {}
            price_data = {}
            for t, v in avail.items():
                if isinstance(v, dict):
                    price_data[t] = {"price": v.get("price"), "change_pct": v.get("change_pct")}
            results.append({
                "type": "event",
                "id": row["event_id"],
                "ts": row["timestamp"] * 1000,
                "headline": row["headline"],
                "source": row["source"],
                "tier": row["source_tier"],
                "type": row["event_type"],
                "direction": row["direction"],
                "sentiment": row["sentiment"],
                "score": row["impact_score"],
                "tickers": tickers,
                "sectors": sectors,
                "etfs": etfs,
                "latency": row["latency_ms"],
                "brief": row["brief"],
                "buy_signal": row["buy_signal"],
                "buy_confidence": row["buy_confidence"],
                "reasoning": [],
                "risk": "",
                "time_horizon": "",
                "correlated_moves": [],
                "url": "",
                "stock_availability": avail,
                "price_data": price_data,
            })
        return results

    # ── Signal Outcome Tracking ───────────────────────────────────────────────

    def insert_signal(self, event_id: str, ticker: str, signal: str,
                      confidence: int, entry_price: float, entry_time: float):
        """Record a new signal to track."""
        try:
            data = {
                "event_id": event_id,
                "ticker": ticker,
                "signal": signal,
                "confidence": confidence,
                "entry_price": entry_price,
                "entry_time": entry_time,
                "completed": 0,
            }
            self.client.table("signal_outcomes").upsert(data).execute()
        except Exception as e:
            print(f"  [Supabase] Signal insert error: {e}")

    def get_pending_signals(self) -> list[dict]:
        """Get signals that still need price checkpoints."""
        result = (
            self.client.table("signal_outcomes")
            .select("event_id, ticker, signal, confidence, entry_price, entry_time, "
                    "price_1h, price_4h, price_1d, price_1w")
            .eq("completed", 0)
            .execute()
        )
        return result.data or []

    def update_signal_checkpoint(self, event_id: str, ticker: str,
                                  checkpoint: str, price: float, pct: float, outcome: str):
        """Update a specific time checkpoint (1h, 4h, 1d, 1w)."""
        valid = {"1h", "4h", "1d", "1w"}
        if checkpoint not in valid:
            return
        try:
            update_data = {
                f"price_{checkpoint}": price,
                f"pct_{checkpoint}": pct,
                f"outcome_{checkpoint}": outcome,
            }
            if checkpoint == "1w":
                update_data["completed"] = 1

            (
                self.client.table("signal_outcomes")
                .update(update_data)
                .eq("event_id", event_id)
                .eq("ticker", ticker)
                .execute()
            )
        except Exception as e:
            print(f"  [Supabase] Signal checkpoint update error: {e}")

    def get_signal_stats(self) -> dict:
        """Compute aggregate win/loss stats across all tracked signals."""
        stats = {"total": 0, "buy": {}, "sell": {}}

        for signal_type in ("BUY", "SELL"):
            result = (
                self.client.table("signal_outcomes")
                .select("*")
                .eq("signal", signal_type)
                .execute()
            )
            rows = result.data or []

            for cp in ("1h", "4h", "1d", "1w"):
                pct_key = f"pct_{cp}"
                outcome_key = f"outcome_{cp}"
                valid_rows = [r for r in rows if r.get(pct_key) is not None]
                total = len(valid_rows)
                wins = sum(1 for r in valid_rows if r.get(outcome_key) == "WIN")
                losses = sum(1 for r in valid_rows if r.get(outcome_key) == "LOSS")
                avg_pct = (
                    round(sum(r[pct_key] for r in valid_rows) / total, 2)
                    if total else 0
                )
                stats[signal_type.lower()][cp] = {
                    "total": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round((wins / total) * 100, 1) if total else 0,
                    "avg_return": avg_pct,
                }

        total_result = (
            self.client.table("signal_outcomes")
            .select("event_id", count="exact")
            .execute()
        )
        stats["total"] = total_result.count or 0
        return stats

    def get_recent_outcomes(self, limit: int = 20) -> list[dict]:
        """Get most recent signal outcomes for display."""
        result = (
            self.client.table("signal_outcomes")
            .select("*")
            .order("entry_time", desc=True)
            .limit(limit)
            .execute()
        )
        outcomes = result.data or []

        # Fetch matching headlines
        for outcome in outcomes:
            event_result = (
                self.client.table("events")
                .select("headline")
                .eq("event_id", outcome["event_id"])
                .limit(1)
                .execute()
            )
            outcome["headline"] = (
                event_result.data[0]["headline"] if event_result.data else ""
            )

        return outcomes

    def get_tracked_ids(self) -> list[dict]:
        """Get list of all currently tracked event_id + ticker pairs."""
        result = (
            self.client.table("signal_outcomes")
            .select("event_id, ticker")
            .order("entry_time", desc=True)
            .execute()
        )
        return [{"event_id": r["event_id"], "ticker": r["ticker"]} for r in (result.data or [])]

    def remove_signal(self, event_id: str, ticker: str = None):
        """Remove a tracked signal (untrack)."""
        try:
            if ticker:
                (
                    self.client.table("signal_outcomes")
                    .delete()
                    .eq("event_id", event_id)
                    .eq("ticker", ticker)
                    .execute()
                )
            else:
                (
                    self.client.table("signal_outcomes")
                    .delete()
                    .eq("event_id", event_id)
                    .execute()
                )
        except Exception as e:
            print(f"  [Supabase] Signal remove error: {e}")
