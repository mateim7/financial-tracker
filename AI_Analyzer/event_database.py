"""
Event Database (SQLite) for the NYSE Impact Screener.
"""

import sqlite3
import json
import time
import csv
import io
import uuid


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

    def insert(self, event):
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
