import asyncio
import os
import time
from typing import Awaitable, Callable, Optional
from backend.algorithm.StockAvailabilityChecker import StockAvailabilityChecker

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

    def __init__(self, db: "EventDatabase",
                 broadcast_callback: Optional[Callable[[], Awaitable[None]]] = None):
        self.db = db
        self._running = False
        self._broadcast_callback = broadcast_callback

    def set_broadcast_callback(self, callback: Optional[Callable[[], Awaitable[None]]]):
        self._broadcast_callback = callback

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

        # Batch fetch current prices (Finnhub for real-time, yfinance fallback)
        prices = {}
        import requests as _requests
        finnhub_key = os.getenv("FINNHUB_API_KEY", "")

        def _fetch_prices():
            for t in tickers_needed:
                try:
                    # Try Finnhub first (includes pre/post-market)
                    if finnhub_key:
                        resp = _requests.get(
                            "https://finnhub.io/api/v1/quote",
                            params={"symbol": t, "token": finnhub_key},
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            c = resp.json().get("c")
                            if c and c > 0:
                                prices[t] = round(c, 2)
                                continue
                    # Fallback to yfinance
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
                      f"${entry_price:.2f} â†’ ${current_price:.2f} ({pct:+.2f}%) = {outcome}")

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

        # Fetch current price as entry point (Finnhub for real-time, yfinance fallback)
        import requests as _requests
        finnhub_key = os.getenv("FINNHUB_API_KEY", "")

        def _get_price():
            try:
                if finnhub_key:
                    resp = _requests.get(
                        "https://finnhub.io/api/v1/quote",
                        params={"symbol": ticker, "token": finnhub_key},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        c = resp.json().get("c")
                        if c and c > 0:
                            return round(c, 2)
                info = yf.Ticker(StockAvailabilityChecker._yf_symbol(ticker)).fast_info
                return getattr(info, "last_price", None)
            except Exception:
                return None

        price = await asyncio.to_thread(_get_price)
        if not price:
            print(f"  [Tracker] Could not fetch price for ${ticker}, skipping track")
            return

        self.record_signal(event_id, ticker, signal, confidence, round(price, 2))
        await self._broadcast_stats()

    async def _broadcast_stats(self):
        """Send signal performance stats to all WS clients."""
        if self._broadcast_callback is not None:
            await self._broadcast_callback()

    async def run_loop(self):
        """Background loop â€” checks pending signals every 5 minutes."""
        self._running = True
        print("  [Tracker] Signal outcome tracker started (checking every 5 min)")
        while self._running:
            try:
                await self.check_pending()
            except Exception as e:
                print(f"  [Tracker] Error checking signals: {e}")
            await asyncio.sleep(300)  # 5 minutes


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# EVENT DATABASE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


