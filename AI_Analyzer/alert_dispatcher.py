"""
Alert Dispatcher for the NYSE Impact Screener.
"""

import json
from dataclasses import asdict
from datetime import datetime, timezone

from models import Direction, ScoredEvent


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
        from server import broadcast_event

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
