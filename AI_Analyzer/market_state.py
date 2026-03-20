"""
Live Market State for the NYSE Impact Screener.
"""

import time
import asyncio
from datetime import datetime, timezone, timedelta


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
        from server import broadcast_market_state

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
