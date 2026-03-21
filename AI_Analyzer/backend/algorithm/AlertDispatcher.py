from dataclasses import asdict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from backend.algorithm.Direction import Direction
from backend.algorithm.ScoredEvent import ScoredEvent
import json


def _to_builtin(value):
    """Recursively convert numpy scalars/containers to JSON-serializable Python types."""
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {k: _to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(v) for v in value]
    return value


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
        "FLASH": "âš¡âš¡",
        "HIGH": "âš¡",
        "STANDARD": "â—",
        "LOW": "â—‹",
    }

    def __init__(self, broadcast_callback: Optional[Callable[[ScoredEvent], Awaitable[None]]] = None):
        self._broadcast_callback = broadcast_callback

    def set_broadcast_callback(self, callback: Optional[Callable[[ScoredEvent], Awaitable[None]]]):
        self._broadcast_callback = callback

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
            return f"{c['GREEN']}â–² BULLISH{c['RESET']}"
        elif direction == Direction.BEARISH:
            return f"{c['RED']}â–¼ BEARISH{c['RESET']}"
        return f"{c['WHITE']}â— NEUTRAL{c['RESET']}"

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
        return f"{color}{'â–ˆ' * filled}{'â–‘' * empty}{self.COLORS['RESET']} {score}/100"

    async def dispatch(self, event: ScoredEvent):
        severity = self.classify_severity(event.impact_score)
        c = self.COLORS

        timestamp = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
        ts_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
        urgency_sym = self.URGENCY_SYMBOLS.get(event.urgency.value, "â—")

        print()
        print(f"  {c[severity]}{'â”' * 76}{c['RESET']}")
        print(f"  {c[severity]}{urgency_sym} {severity} ALERT{c['RESET']}  â”‚  {ts_str} UTC  â”‚  "
              f"Urgency: {event.urgency.value}  â”‚  Processed in {event.latency_ms:.1f}ms")
        print(f"  {c[severity]}{'â”' * 76}{c['RESET']}")
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
                label = "HOLD â€” NEUTRAL"
                color = c['DIM']
            print(f"    {c['WHITE']}Signal:{c['RESET']}     {color}{event.buy_signal} â€” {label} ({conf}% confidence){c['RESET']}")
        if event.stock_availability:
            print(f"    {c['WHITE']}Platforms:{c['RESET']}")
            for ticker, info in event.stock_availability.items():
                platforms = [p for p, ok in [("Revolut", info.get("revolut")), ("XTB", info.get("xtb"))] if ok]
                status = "âœ“ " + ", ".join(platforms) if platforms else "âœ— Not on major platforms"
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

        if self._broadcast_callback is not None:
            await self._broadcast_callback(event)

    async def _send_webhook(self, event: ScoredEvent):
        dir_emoji = {"BULLISH": "ðŸŸ¢â–²", "BEARISH": "ðŸ”´â–¼", "NEUTRAL": "âšªâ—"}
        event_dict = _to_builtin(asdict(event))
        event_dict["event_type"] = event.event_type.value
        event_dict["direction"] = event.direction.value
        event_dict["urgency"] = event.urgency.value
        payload = _to_builtin({
            "content": (
                f"**{self.URGENCY_SYMBOLS.get(event.urgency.value, '')} "
                f"{event.urgency.value} â€” Impact: {event.impact_score}/100**\n"
                f"{dir_emoji.get(event.direction.value, '')} **{event.direction.value}**\n\n"
                f"ðŸ“° {event.headline}\n"
                f"ðŸ·ï¸ Tickers: {', '.join(event.affected_tickers) or 'MACRO'}\n"
                f"ðŸ“Š Sectors: {', '.join(event.affected_sectors)}\n"
                f"ðŸ“ˆ ETFs: {', '.join(event.affected_etfs)}\n"
                f"ðŸ”— Supply Chain: {', '.join(event.supply_chain_exposure[:5]) or 'N/A'}\n"
                f"ðŸ”¬ Type: {event.event_type.value} | Sentiment: {event.sentiment:+.3f}\n"
                f"â±ï¸ Source: {event.source} | Latency: {event.latency_ms:.1f}ms"
            ),
            "event_data": event_dict,
        })
        print(f"    ðŸ“¡ Webhook payload prepared ({len(json.dumps(payload))} bytes)")
        print()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SECTION 6: EXPANDED SIMULATED NEWS FEED â€” 25 Events Across All Sectors
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

DUMMY_NEWS_FEED: list[dict] = [
    # â”€â”€ SEMICONDUCTORS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "U.S. Commerce Dept announces sweeping new chip export controls targeting China's AI sector",
        "body": "The Biden administration unveiled new restrictions on semiconductor exports to China, "
                "specifically targeting advanced AI chips and lithography equipment. NVIDIA, AMD, and "
                "ASML are expected to be most affected. The rules take effect in 90 days and close "
                "prior loopholes that allowed modified chip designs to bypass controls.",
        "tickers": ["NVDA", "AMD", "ASML"],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "TSMC reports record Q4 revenue, raises 2026 capex to $40B on AI chip demand surge",
        "body": "Taiwan Semiconductor Manufacturing Company posted record quarterly revenue of $23.6B, "
                "beating estimates by 8%. The company raised its 2026 capital expenditure forecast to "
                "$40B, citing unprecedented demand for advanced 3nm and 2nm AI chips from NVIDIA and AMD.",
        "tickers": ["TSM"],
    },
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Micron Technology beats earnings, HBM memory demand exceeds all forecasts",
        "body": "Micron reported EPS of $1.82 vs $1.45 expected. High-bandwidth memory (HBM) revenue "
                "tripled year-over-year, driven by AI accelerator demand from NVIDIA and AMD. The "
                "company raised guidance for the next two quarters.",
        "tickers": ["MU"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "Intel CEO Pat Gelsinger resigns amid foundy struggles; board names interim leadership",
        "body": "Intel CEO Pat Gelsinger has stepped down effective immediately after the board lost "
                "confidence in the company's foundry turnaround plan. Intel's contract manufacturing "
                "business has consistently missed yield targets. CFO David Zinsner and VP MJ Holthaus "
                "named interim co-CEOs.",
        "tickers": ["INTC"],
    },

    # â”€â”€ ENERGY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "OPEC+ agrees to deepen oil production cuts by 1.5M barrels/day starting January",
        "body": "OPEC+ ministers agreed to an additional 1.5 million barrel-per-day production cut, "
                "the largest surprise reduction since 2020. Saudi Arabia will shoulder 500K bpd, "
                "with Russia and UAE splitting the remainder. Brent crude surged 6% on the news.",
        "tickers": [],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Exxon Mobil declares force majeure on Permian Basin operations after pipeline explosion",
        "body": "An explosion at a major Exxon Mobil pipeline junction in the Permian Basin has "
                "forced the company to declare force majeure on approximately 200K bpd of production. "
                "Halliburton and Schlumberger crews are responding. Full restoration expected in 4-6 weeks.",
        "tickers": ["XOM"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "First Solar surges after IRA tax credit extension confirmed through 2035",
        "body": "First Solar shares rallied in pre-market after Congress confirmed the extension "
                "of Inflation Reduction Act solar manufacturing tax credits through 2035. Enphase "
                "Energy also expected to benefit from the expanded timeline.",
        "tickers": ["FSLR", "ENPH"],
    },

    # â”€â”€ FINANCIALS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "JPMorgan to acquire regional bank First Republic in $10.6B deal",
        "body": "JPMorgan Chase has agreed to acquire substantially all of First Republic Bank's "
                "assets in a deal valued at $10.6 billion. The FDIC-assisted transaction includes "
                "all deposits and most assets. Jamie Dimon called it a 'responsible resolution.'",
        "tickers": ["JPM"],
    },
    {
        "source": "SEC EDGAR",
        "source_tier": 2,
        "headline": "SEC charges Goldman Sachs with misleading investors on ESG fund practices",
        "body": "The Securities and Exchange Commission has charged Goldman Sachs Asset Management "
                "with failing to follow its own policies for ESG investing. Goldman neither admitted "
                "nor denied the findings and agreed to pay a $4M fine.",
        "tickers": ["GS"],
    },
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Visa reports record Q4 transaction volume, announces $10B buyback program",
        "body": "Visa reported Q4 earnings above estimates with payment volume reaching an all-time "
                "high of $3.5 trillion. The board authorized a new $10B share repurchase program. "
                "Cross-border transactions grew 15% year-over-year.",
        "tickers": ["V"],
    },

    # â”€â”€ HEALTHCARE / PHARMA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "BREAKING: FDA approves Pfizer's new RSV vaccine for elderly adults",
        "body": "The FDA granted full approval to Pfizer's respiratory syncytial virus vaccine, "
                "making it the first approved RSV shot for adults over 60. Analysts estimate "
                "peak sales of $5B annually.",
        "tickers": ["PFE"],
    },
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Eli Lilly obesity drug Mounjaro Phase 3 data shows 26% weight loss, surpassing Ozempic",
        "body": "Eli Lilly released Phase 3 clinical trial data showing its obesity drug achieved "
                "26.2% average weight loss at 72 weeks, significantly exceeding Novo Nordisk's "
                "Ozempic at 16.9%. The data positions Mounjaro as the potential market leader in "
                "the $100B+ obesity treatment market.",
        "tickers": ["LLY"],
    },
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "UnitedHealth Group CEO under DOJ investigation for insider trading â€” shares halted",
        "body": "The Department of Justice has opened a criminal investigation into UnitedHealth "
                "Group's CEO for alleged insider trading ahead of a major acquisition announcement. "
                "Trading in UNH shares has been halted pending further information.",
        "tickers": ["UNH"],
    },

    # â”€â”€ DEFENSE / AEROSPACE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Pentagon awards Lockheed Martin $22B contract for next-generation fighter jet",
        "body": "The Department of Defense awarded Lockheed Martin a $22 billion contract for "
                "the Next Generation Air Dominance (NGAD) program, the largest single defense "
                "contract in a decade. Northrop Grumman and RTX will serve as key subcontractors.",
        "tickers": ["LMT"],
    },
    {
        "source": "CNBC",
        "source_tier": 2,
        "headline": "Boeing 737 MAX deliveries halted again after new fuselage quality defect found",
        "body": "Boeing has paused deliveries of its 737 MAX aircraft after discovering a new "
                "manufacturing defect in the fuselage. The FAA is investigating. This marks the "
                "third delivery halt in 18 months. GE Aerospace engine deliveries also impacted.",
        "tickers": ["BA"],
    },

    # â”€â”€ MACRO EVENTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "BLS",
        "source_tier": 1,
        "headline": "CPI rises 0.6% in March, hotter than expected â€” core inflation surges to 4.1%",
        "body": "The Bureau of Labor Statistics reported the Consumer Price Index rose 0.6% in March, "
                "well above the 0.3% consensus. Core CPI hit 4.1% year-over-year, raising fears "
                "the Fed will maintain hawkish stance longer than markets anticipated.",
        "tickers": [],
    },
    {
        "source": "Federal Reserve",
        "source_tier": 1,
        "headline": "FOMC holds rate steady at 5.25-5.50%, signals hawkish stance with dot plot showing no cuts until Q3",
        "body": "The Federal Reserve held the federal funds rate unchanged at 5.25-5.50% as expected. "
                "However, the updated dot plot surprised markets by signaling no rate cuts until at "
                "least Q3, with two governors dissenting in favor of a hike.",
        "tickers": [],
    },
    {
        "source": "BLS",
        "source_tier": 1,
        "headline": "Nonfarm payrolls surge by 353K in January, crushing 180K estimate â€” wages rise 0.6%",
        "body": "The U.S. economy added 353,000 jobs in January, nearly double the consensus forecast. "
                "Average hourly earnings rose 0.6%, also above expectations. The unemployment rate "
                "held at 3.7%. Markets repriced rate cut expectations sharply.",
        "tickers": [],
    },

    # â”€â”€ MATERIALS / MINING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Copper prices surge to all-time high on China stimulus + AI data center demand",
        "body": "Copper futures hit a record $5.20/lb, driven by China's massive infrastructure "
                "stimulus package and surging demand from AI data center construction. Freeport-McMoRan, "
                "the world's largest public copper miner, is the primary beneficiary.",
        "tickers": ["FCX"],
    },

    # â”€â”€ UTILITIES / DATA CENTERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "Vistra Energy surges after securing $4.2B in long-term nuclear power contracts with hyperscalers",
        "body": "Vistra Corp announced $4.2 billion in long-term power purchase agreements with "
                "major tech companies for its Comanche Peak nuclear facility. The contracts, "
                "spanning 15-20 years, will power AI data centers. This follows similar deals "
                "by Constellation Energy.",
        "tickers": ["VST"],
    },

    # â”€â”€ REITs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Equinix announces $5B data center expansion across 8 markets to meet AI demand",
        "body": "Equinix, the world's largest data center REIT, announced a $5 billion expansion "
                "plan targeting 8 new metropolitan markets. The investment is driven by surging "
                "demand from cloud providers and AI workloads. Prologis also benefits from "
                "industrial logistics supporting these buildouts.",
        "tickers": ["EQIX"],
    },

    # â”€â”€ GEOPOLITICAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Reuters",
        "source_tier": 1,
        "headline": "China announces retaliatory tariffs of 25% on U.S. agricultural and semiconductor equipment exports",
        "body": "China's Commerce Ministry announced 25% tariffs on U.S. agricultural machinery, "
                "semiconductor manufacturing equipment, and selected energy products in retaliation "
                "for new U.S. chip export controls. Deere, Applied Materials, and Lam Research "
                "are directly impacted. Markets selling off broadly.",
        "tickers": [],
    },

    # â”€â”€ CONSUMER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Walmart beats Q3 earnings estimates, raises full-year guidance on strong grocery and e-commerce",
        "body": "Walmart reported Q3 EPS of $1.53, beating consensus of $1.32. Revenue came in at "
                "$160.8B vs. $159.7B expected. The company raised its full-year guidance citing "
                "strong grocery demand and e-commerce growth.",
        "tickers": ["WMT"],
    },

    # â”€â”€ CYBER / TECH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Massive cyberattack hits AT&T â€” 70M customer records exposed, FCC launches probe",
        "body": "AT&T disclosed a major data breach affecting approximately 70 million current and "
                "former customers. Social security numbers, account details, and passcodes were "
                "compromised. The FCC has opened a formal investigation. AT&T faces potential "
                "fines exceeding $1 billion.",
        "tickers": ["T"],
    },

    # â”€â”€ LOW NOISE â€” Should score low â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "source": "Twitter/X",
        "source_tier": 3,
        "headline": "Rumor: Nike may be exploring strategic options including potential sale",
        "body": "Unconfirmed reports suggest Nike's board has engaged advisors to explore "
                "strategic alternatives. No official statement from the company.",
        "tickers": ["NKE"],
    },
]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SECTION 7: MAIN ENGINE ORCHESTRATOR
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


