"""
Technical Indicators Module
────────────────────────────
Computes RSI, MACD, and volume analysis for tickers using yfinance.
Designed for fast, cached lookups during event processing.
"""

import asyncio
import time
import yfinance as yf


class TechnicalIndicators:
    """
    Fetches and caches technical indicators (RSI, MACD, volume) per ticker.
    Uses yfinance intraday/daily data with a 5-minute cache TTL.
    """

    CACHE_TTL = 300  # 5 minutes

    def __init__(self):
        self._cache = {}  # {ticker: {"data": {...}, "ts": float}}

    def _yf_symbol(self, ticker: str) -> str:
        return ticker.replace(".", "-")

    def _compute_rsi(self, closes, period=14):
        """Compute RSI from a pandas Series of close prices."""
        if closes is None or len(closes) < period + 1:
            return None
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        last_avg_gain = avg_gain.iloc[-1]
        last_avg_loss = avg_loss.iloc[-1]
        if last_avg_loss == 0:
            return 100.0
        rs = last_avg_gain / last_avg_loss
        return round(100 - (100 / (1 + rs)), 1)

    def _compute_macd(self, closes):
        """Compute MACD line, signal line, and histogram."""
        if closes is None or len(closes) < 35:
            return None
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_val = round(macd_line.iloc[-1], 4)
        signal_val = round(signal_line.iloc[-1], 4)
        hist_val = round(histogram.iloc[-1], 4)

        # Detect crossover
        if len(histogram) >= 2:
            prev_hist = histogram.iloc[-2]
            curr_hist = histogram.iloc[-1]
            if prev_hist <= 0 and curr_hist > 0:
                crossover = "BULLISH"
            elif prev_hist >= 0 and curr_hist < 0:
                crossover = "BEARISH"
            else:
                crossover = "NONE"
        else:
            crossover = "NONE"

        return {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": hist_val,
            "crossover": crossover,
        }

    def _compute_volume(self, volume_series, closes):
        """Compute volume analysis: current vs 20-day average, spike detection."""
        if volume_series is None or len(volume_series) < 2:
            return None

        current_vol = int(volume_series.iloc[-1])
        avg_20 = volume_series.tail(20).mean()
        avg_20_int = int(avg_20) if avg_20 else 0

        if avg_20 and avg_20 > 0:
            ratio = round(current_vol / avg_20, 2)
        else:
            ratio = 0

        # Spike = volume > 2x the 20-day average
        spike = ratio >= 2.0

        return {
            "current": current_vol,
            "avg_20d": avg_20_int,
            "ratio": ratio,
            "spike": spike,
        }

    def _fetch_single(self, ticker: str) -> dict:
        """Fetch indicators for a single ticker (blocking — run in thread)."""
        symbol = self._yf_symbol(ticker)
        try:
            tk = yf.Ticker(symbol)
            # Get 3 months of daily data (enough for MACD 26+9 period)
            hist = tk.history(period="3mo", interval="1d")
            if hist is None or hist.empty or len(hist) < 5:
                return {"ticker": ticker, "available": False}

            closes = hist["Close"]
            volumes = hist["Volume"]

            rsi = self._compute_rsi(closes)
            macd = self._compute_macd(closes)
            volume = self._compute_volume(volumes, closes)

            # RSI interpretation
            if rsi is not None:
                if rsi >= 70:
                    rsi_label = "OVERBOUGHT"
                elif rsi <= 30:
                    rsi_label = "OVERSOLD"
                elif rsi >= 60:
                    rsi_label = "BULLISH"
                elif rsi <= 40:
                    rsi_label = "BEARISH"
                else:
                    rsi_label = "NEUTRAL"
            else:
                rsi_label = None

            # Overall technical signal
            signals = []
            if rsi is not None:
                if rsi <= 30:
                    signals.append("BUY")   # oversold
                elif rsi >= 70:
                    signals.append("SELL")  # overbought
            if macd and macd["crossover"] == "BULLISH":
                signals.append("BUY")
            elif macd and macd["crossover"] == "BEARISH":
                signals.append("SELL")
            if volume and volume["spike"]:
                signals.append("CONFIRM")  # volume confirms the move

            buy_count = signals.count("BUY")
            sell_count = signals.count("SELL")
            has_confirm = "CONFIRM" in signals

            if buy_count > sell_count:
                tech_signal = "BULLISH"
            elif sell_count > buy_count:
                tech_signal = "BEARISH"
            else:
                tech_signal = "NEUTRAL"

            # Agreement score: how strongly technicals agree (0-100)
            total_indicators = 0
            agreeing = 0
            if rsi is not None:
                total_indicators += 1
                if (tech_signal == "BULLISH" and rsi <= 50) or (tech_signal == "BEARISH" and rsi >= 50):
                    agreeing += 1
            if macd:
                total_indicators += 1
                if (tech_signal == "BULLISH" and macd["histogram"] > 0) or \
                   (tech_signal == "BEARISH" and macd["histogram"] < 0):
                    agreeing += 1
            if volume:
                total_indicators += 1
                if volume["spike"]:
                    agreeing += 1

            strength = round((agreeing / total_indicators) * 100) if total_indicators else 0

            return {
                "ticker": ticker,
                "available": True,
                "rsi": {"value": rsi, "label": rsi_label} if rsi is not None else None,
                "macd": macd,
                "volume": volume,
                "tech_signal": tech_signal,
                "strength": strength,
                "volume_confirms": has_confirm,
            }

        except Exception as e:
            print(f"  [TechInd] Error fetching {ticker}: {e}")
            return {"ticker": ticker, "available": False}

    async def get_indicators(self, tickers: list[str]) -> dict:
        """
        Fetch technical indicators for a list of tickers.
        Returns {ticker: indicators_dict} with caching.
        """
        now = time.time()
        result = {}
        to_fetch = []

        for t in tickers:
            cached = self._cache.get(t)
            if cached and (now - cached["ts"]) < self.CACHE_TTL:
                result[t] = cached["data"]
            else:
                to_fetch.append(t)

        if to_fetch:
            def _batch_fetch():
                fetched = {}
                for t in to_fetch:
                    fetched[t] = self._fetch_single(t)
                return fetched

            fetched = await asyncio.to_thread(_batch_fetch)
            for t, data in fetched.items():
                self._cache[t] = {"data": data, "ts": now}
                result[t] = data

        return result
