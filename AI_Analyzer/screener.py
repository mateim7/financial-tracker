"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     NYSE IMPACT NEWS SCREENER v2.0 — Advanced Multi-Sector Engine          ║
║                                                                             ║
║  Expanded coverage: 300+ tickers across 20 sectors                         ║
║  Features: Supply chain contagion, cross-sector propagation, volatility    ║
║            regime detection, earnings surprise calibration, macro regime    ║
║            awareness, multi-entity resolution, indirect exposure mapping   ║
║                                                                             ║
║  Demonstrates: Ingestion → NLP Scoring → Entity Extraction → Alerting     ║
║  Author: Senior Financial Software Architect & Quantitative AI Specialist  ║
║  NOTE: Uses simulated feed. Swap DummyFeed for Benzinga/Reuters WS        ║
║        in production.                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import uuid
import time
from typing import Optional
from collections import defaultdict
import websockets

from models import Direction, RawNewsEvent, ScoredEvent
from rss_feed import RSSFeed
from ws_feed import WebSocketNewsFeed
from claude_scorer import ClaudeScorer
from stock_checker import StockAvailabilityChecker
from insider_checker import InsiderActivityChecker
from reference_db import NYSEReferenceDB
from entity_extractor import EntityExtractor
from scoring_engine import MarketImpactScoringEngine
from alert_dispatcher import AlertDispatcher
from signal_tracker import SignalOutcomeTracker
from supabase_db import SupabaseDatabase
from server import (
    ws_handler, start_http_server, WS_CLIENTS,
    _LIVE_MARKET_STATE, _SIGNAL_TRACKER_DB, _SIGNAL_TRACKER,
)
import server as _server_module


# ═══════════════════════════════════════════════════════════════════════════════
# EXPANDED SIMULATED NEWS FEED — 25 Events Across All Sectors
# ═══════════════════════════════════════════════════════════════════════════════

DUMMY_NEWS_FEED: list[dict] = [
    # ── SEMICONDUCTORS ──────────────────────────────────────────────────────
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

    # ── ENERGY ──────────────────────────────────────────────────────────────
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

    # ── FINANCIALS ──────────────────────────────────────────────────────────
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

    # ── HEALTHCARE / PHARMA ─────────────────────────────────────────────────
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
        "headline": "UnitedHealth Group CEO under DOJ investigation for insider trading — shares halted",
        "body": "The Department of Justice has opened a criminal investigation into UnitedHealth "
                "Group's CEO for alleged insider trading ahead of a major acquisition announcement. "
                "Trading in UNH shares has been halted pending further information.",
        "tickers": ["UNH"],
    },

    # ── DEFENSE / AEROSPACE ─────────────────────────────────────────────────
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

    # ── MACRO EVENTS ────────────────────────────────────────────────────────
    {
        "source": "BLS",
        "source_tier": 1,
        "headline": "CPI rises 0.6% in March, hotter than expected — core inflation surges to 4.1%",
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
        "headline": "Nonfarm payrolls surge by 353K in January, crushing 180K estimate — wages rise 0.6%",
        "body": "The U.S. economy added 353,000 jobs in January, nearly double the consensus forecast. "
                "Average hourly earnings rose 0.6%, also above expectations. The unemployment rate "
                "held at 3.7%. Markets repriced rate cut expectations sharply.",
        "tickers": [],
    },

    # ── MATERIALS / MINING ──────────────────────────────────────────────────
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Copper prices surge to all-time high on China stimulus + AI data center demand",
        "body": "Copper futures hit a record $5.20/lb, driven by China's massive infrastructure "
                "stimulus package and surging demand from AI data center construction. Freeport-McMoRan, "
                "the world's largest public copper miner, is the primary beneficiary.",
        "tickers": ["FCX"],
    },

    # ── UTILITIES / DATA CENTERS ────────────────────────────────────────────
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

    # ── REITs ───────────────────────────────────────────────────────────────
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

    # ── GEOPOLITICAL ────────────────────────────────────────────────────────
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

    # ── CONSUMER ────────────────────────────────────────────────────────────
    {
        "source": "Benzinga",
        "source_tier": 2,
        "headline": "Walmart beats Q3 earnings estimates, raises full-year guidance on strong grocery and e-commerce",
        "body": "Walmart reported Q3 EPS of $1.53, beating consensus of $1.32. Revenue came in at "
                "$160.8B vs. $159.7B expected. The company raised its full-year guidance citing "
                "strong grocery demand and e-commerce growth.",
        "tickers": ["WMT"],
    },

    # ── CYBER / TECH ────────────────────────────────────────────────────────
    {
        "source": "Bloomberg",
        "source_tier": 1,
        "headline": "Massive cyberattack hits AT&T — 70M customer records exposed, FCC launches probe",
        "body": "AT&T disclosed a major data breach affecting approximately 70 million current and "
                "former customers. Social security numbers, account details, and passcodes were "
                "compromised. The FCC has opened a formal investigation. AT&T faces potential "
                "fines exceeding $1 billion.",
        "tickers": ["T"],
    },

    # ── LOW NOISE — Should score low ────────────────────────────────────────
    {
        "source": "Twitter/X",
        "source_tier": 3,
        "headline": "Rumor: Nike may be exploring strategic options including potential sale",
        "body": "Unconfirmed reports suggest Nike's board has engaged advisors to explore "
                "strategic alternatives. No official statement from the company.",
        "tickers": ["NKE"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class NYSEImpactScreener:

    def __init__(self, alert_threshold: int = 0):
        self.reference_db = NYSEReferenceDB()
        self.entity_extractor = EntityExtractor(self.reference_db)
        self.scoring_engine = MarketImpactScoringEngine(self.reference_db)
        self.alert_dispatcher = AlertDispatcher()
        self.availability_checker = StockAvailabilityChecker()
        self.insider_checker = InsiderActivityChecker()
        from supabase_db import SupabaseDatabase
        self.db = SupabaseDatabase()
        self.claude_scorer = ClaudeScorer(known_tickers=self.entity_extractor._all_known_tickers, db=self.db)
        self.signal_tracker = SignalOutcomeTracker(self.db)
        self.rss = None
        self.alert_threshold = alert_threshold
        self.processed_count = 0
        self.alert_count = 0
        self.sector_heat: dict[str, list[int]] = defaultdict(list)

    def ingest_raw(self, raw: dict) -> RawNewsEvent:
        # Use original publication timestamp if available, fallback to now
        ts = raw.get("pub_ts") or time.time()
        return RawNewsEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=ts,
            source=raw["source"],
            source_tier=raw["source_tier"],
            headline=raw["headline"],
            body=raw.get("body", ""),
            raw_tickers=raw.get("tickers", []),
            url=raw.get("link", ""),
            ws_source=raw.get("ws_source", False),
        )

    async def process_event(self, raw: dict) -> Optional[ScoredEvent]:
        event = self.ingest_raw(raw)
        entities = self.entity_extractor.extract(event.headline, event.body)
        scored = self.scoring_engine.score_event(event, entities)

        # ── LOW-IMPACT FILTER — comment out the next 2 lines to re-enable low-impact events ──
        if scored.impact_score < 40:
            return None
        # ─────────────────────────────────────────────────────────────────────────────────────

        # Check stock availability + live price BEFORE Claude (free, no tokens)
        if scored.affected_tickers:
            availability = await self.availability_checker.check_tickers(scored.affected_tickers)
            scored.stock_availability = availability
            scored.price_data = {t: {"price": v.get("price"), "change_pct": v.get("change_pct"), "volume": v.get("volume"), "rvol": v.get("rvol")} for t, v in availability.items()}

            # Fetch SEC Form 4 insider activity (Finnhub, cached 30 min)
            insider_data = await self.insider_checker.check_tickers(scored.affected_tickers)
            scored.insider_activity = {t: txs for t, txs in insider_data.items() if txs}

        # Skip Claude for LOW impact events (score < 40)
        if scored.impact_score >= 40:
            scored = await self.claude_scorer.enhance(scored, event.headline, event.body)

            # Validate BUY signal > 50% against other sources
            if scored.buy_signal == "BUY" and scored.buy_confidence > 50 and self.rss:
                tickers_set = set(scored.affected_tickers)
                corroborating = [
                    a for a in self.rss._recent_articles
                    if a.get("source") != event.source
                    and any(t in a.get("headline", "") for t in tickers_set)
                ]
                if corroborating:
                    print(f"  [Claude] Validating BUY signal with {len(corroborating[:3])} corroborating source(s)...")
                    scored = await self.claude_scorer.validate_buy(scored, corroborating[:3])

            # Check availability + price for correlated_moves and ticker_signals tickers
            # that weren't already checked in the pre-Claude pass
            extra_tickers = set()
            extra_tickers.update(scored.correlated_moves)
            extra_tickers.update(scored.ticker_signals.keys())
            extra_tickers -= set(scored.stock_availability.keys())  # skip already checked
            if extra_tickers:
                extra_avail = await self.availability_checker.check_tickers(list(extra_tickers))
                scored.stock_availability.update(extra_avail)
                for t, v in extra_avail.items():
                    scored.price_data[t] = {"price": v.get("price"), "change_pct": v.get("change_pct"), "volume": v.get("volume"), "rvol": v.get("rvol")}

            # ── Fix "Volume data unavailable" when RVOL was fetched post-Claude ──
            # Claude ran before correlated tickers had price data, so it may have
            # defaulted to "Volume data unavailable." Now that we have the data,
            # auto-generate a momentum_context from the actual numbers.
            if scored.momentum_context and "unavailable" in scored.momentum_context.lower():
                # Build a human-readable narrative from post-fetch volume data
                green_tickers = []
                red_tickers = []
                dead_vol_tickers = []
                hot_vol_tickers = []
                for t in list(scored.affected_tickers) + list(scored.correlated_moves):
                    pd = scored.price_data.get(t, {})
                    if pd.get("rvol") is not None and pd.get("change_pct") is not None:
                        if pd["change_pct"] > 0:
                            green_tickers.append((t, pd["change_pct"], pd["rvol"]))
                        else:
                            red_tickers.append((t, pd["change_pct"], pd["rvol"]))
                        if pd["rvol"] < 0.5:
                            dead_vol_tickers.append(t)
                        elif pd["rvol"] >= 1.5:
                            hot_vol_tickers.append(t)

                if dead_vol_tickers or hot_vol_tickers or green_tickers or red_tickers:
                    parts = []
                    if dead_vol_tickers:
                        parts.append(
                            f"Volume is uniformly LOW ({', '.join(dead_vol_tickers)}) — "
                            f"no institutional conviction behind today's moves"
                        )
                    if hot_vol_tickers:
                        parts.append(
                            f"Heavy volume on {', '.join(hot_vol_tickers)} confirms "
                            f"institutional participation"
                        )
                    if green_tickers and red_tickers:
                        green_str = ", ".join(f"{t} {c:+.1f}%" for t, c, _ in green_tickers[:3])
                        red_str = ", ".join(f"{t} {c:+.1f}%" for t, c, _ in red_tickers[:3])
                        parts.append(f"Mixed tape: {green_str} rising while {red_str} falling")
                    elif green_tickers and not red_tickers:
                        all_str = ", ".join(f"{t} {c:+.1f}%" for t, c, _ in green_tickers[:4])
                        max_change = max(c for _, c, _ in green_tickers)
                        if max_change >= 3.0:
                            parts.append(
                                f"Strong rally across tickers ({all_str}) — market is ignoring the bearish headline. "
                                f"Shorting into a {max_change:+.1f}% surge is high-risk"
                            )
                        else:
                            parts.append(f"All tickers green ({all_str}) on low volume — modest drift, not a catalyst-driven move")
                    elif red_tickers and not green_tickers:
                        all_str = ", ".join(f"{t} {c:+.1f}%" for t, c, _ in red_tickers[:4])
                        parts.append(f"Broad weakness across sector ({all_str})")
                    scored.momentum_context = ". ".join(parts) + "."

            # ══════════════════════════════════════════════════════════════════
            # SECOND-PASS TAPE ENFORCEMENT — runs AFTER correlated ticker
            # prices are fetched. The first pass (in ClaudeScorer) only had
            # primary ticker data; this pass catches correlated tickers too.
            # ══════════════════════════════════════════════════════════════════
            all_signal_tickers_2 = set(scored.affected_tickers)
            all_signal_tickers_2.update(scored.ticker_signals.keys())

            for t in all_signal_tickers_2:
                pd = scored.price_data.get(t)
                if not pd:
                    continue
                change = pd.get("change_pct")
                rvol = pd.get("rvol")
                ts = scored.ticker_signals.get(t, {})
                ticker_signal = ts.get("signal", scored.buy_signal if t in scored.affected_tickers else None)
                ticker_conf = ts.get("confidence", scored.buy_confidence)

                # ── SELL on green stock ──
                if ticker_signal == "SELL" and change is not None and change > 0:
                    if change >= 3.0:
                        new_conf = min(ticker_conf, 30)
                    elif change >= 1.0:
                        new_conf = min(ticker_conf, 40)
                    else:
                        new_conf = min(ticker_conf, 50)
                    print(f"  [Enforce-2] Fighting the tape: SELL {t} at {change:+.2f}% "
                          f"→ overriding to HOLD (conf {ticker_conf} → {new_conf})")
                    if t in scored.ticker_signals:
                        scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                    if t in scored.affected_tickers and scored.buy_signal == "SELL":
                        scored.buy_signal = "HOLD"
                        scored.buy_confidence = new_conf

                # ── BUY on red stock (Second Pass) ──
                # NO exceptions — tape always wins
                if ticker_signal == "BUY" and change is not None and change < 0:
                    if change <= -3.0:
                        new_conf = min(ticker_conf, 30)
                    elif change <= -1.0:
                        if rvol is not None and rvol >= 1.5:
                            new_conf = min(ticker_conf, 25)
                        elif rvol is not None and rvol >= 0.8:
                            new_conf = min(ticker_conf, 40)
                        else:
                            new_conf = min(ticker_conf, 35)
                    else:
                        if rvol is not None and rvol >= 1.5:
                            new_conf = min(ticker_conf, 50)
                        elif rvol is not None and rvol >= 0.8:
                            new_conf = min(ticker_conf, 55)
                        else:
                            new_conf = min(ticker_conf, 45)
                    print(f"  [Enforce-2] BUY on red tape: {t} at {change:+.2f}% RVOL {rvol}x "
                          f"→ overriding to HOLD (conf {ticker_conf} → {new_conf})")
                    if t in scored.ticker_signals:
                        scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                    if t in scored.affected_tickers and scored.buy_signal == "BUY":
                        scored.buy_signal = "HOLD"
                        scored.buy_confidence = new_conf

                # ── BEARISH DIRECTION + BUY CONTRADICTION (Second Pass) ──
                if (scored.direction == Direction.BEARISH
                        and ticker_signal == "BUY"
                        and change is not None and change < 0):
                    if change <= -1.0:
                        new_conf = min(ticker_conf, 30)
                    else:
                        new_conf = min(ticker_conf, 40)
                    print(f"  [Enforce] Bearish direction + red tape: {t} at {change:+.2f}% "
                          f"with BEARISH news -> forced HOLD (conf {ticker_conf} -> {new_conf})")
                    if t in scored.ticker_signals:
                        scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                    if t in scored.affected_tickers and scored.buy_signal == "BUY":
                        scored.buy_signal = "HOLD"
                        scored.buy_confidence = new_conf

                # ── SYMMETRICAL VOLUME VETO (Second Pass) ──
                TIER1_CATALYSTS_2 = {
                    "EARNINGS_BEAT", "EARNINGS_MISS", "FDA_APPROVAL", "FDA_REJECTION",
                    "MA_ANNOUNCED", "MA_COMPLETED", "MA_BLOCKED", "BANKRUPTCY",
                    "STOCK_SPLIT", "BUYBACK_ANNOUNCED",
                }
                is_tier1_2 = scored.event_type in TIER1_CATALYSTS_2 if hasattr(scored, 'event_type') else False

                if rvol is not None and rvol < 0.8 and not is_tier1_2:
                    # Re-read signal after possible SELL→HOLD override above
                    ts2 = scored.ticker_signals.get(t, {})
                    ticker_signal_2 = ts2.get("signal", scored.buy_signal if t in scored.affected_tickers else None)
                    ticker_conf_2 = ts2.get("confidence", scored.buy_confidence)

                    if ticker_signal_2 in ("BUY", "SELL"):
                        new_conf = max(20, min(ticker_conf_2, 45))
                        print(f"  [Enforce-2] Symmetrical Volume Veto for {t}: RVOL {rvol}x < 0.8 "
                              f"→ {ticker_signal_2} overridden to HOLD (conf {ticker_conf_2} → {new_conf})")
                        if t in scored.ticker_signals:
                            scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                        if t in scored.affected_tickers:
                            scored.buy_signal = "HOLD"
                            scored.buy_confidence = new_conf

            # ══════════════════════════════════════════════════════════════════
            # GLOBAL SCORE AGGREGATOR — Blended Claude + Conviction
            # Claude's impact_score anchors news significance (60%).
            # Ticker conviction adjusts for actionability (40%).
            # Divergence penalty if BUY/SELL signals conflict.
            # Breadth bonus for wide-impact multi-ticker events.
            # ══════════════════════════════════════════════════════════════════
            if scored.ticker_signals:
                primary_set = set(scored.affected_tickers or [])
                claude_score = scored.impact_score

                total_w = 0.0
                weighted_conf_sum = 0.0
                buy_weight = 0.0
                sell_weight = 0.0
                for ticker, sig in scored.ticker_signals.items():
                    conf = sig.get("confidence", 50)
                    w = 2.0 if ticker in primary_set else 1.0
                    weighted_conf_sum += conf * w
                    total_w += w
                    signal = sig.get("signal", "HOLD")
                    if signal == "BUY":
                        buy_weight += conf * w
                    elif signal == "SELL":
                        sell_weight += conf * w

                old_score = scored.impact_score
                if total_w > 0:
                    avg_conviction = weighted_conf_sum / total_w
                    directional_total = buy_weight + sell_weight
                    if directional_total > 0:
                        agreement = abs(buy_weight - sell_weight) / directional_total
                    else:
                        agreement = 0.5
                    n_signals = len(scored.ticker_signals)
                    breadth = min(1.0, n_signals / 6.0)

                    raw_blend = claude_score * 0.6 + avg_conviction * 0.4
                    adjusted = raw_blend * (0.7 + 0.3 * agreement) + breadth * 5
                    scored.impact_score = max(1, min(100, round(adjusted)))

                if old_score != scored.impact_score:
                    print(f"  [Aggregate] Global score: {old_score} -> {scored.impact_score} "
                          f"(claude={claude_score}, conviction={avg_conviction:.0f}, "
                          f"agreement={agreement:.2f}, breadth={breadth:.2f})")

            # ── POST-CLAUDE FILTER — drop if Claude re-scored below threshold ──
            if scored.impact_score < 40:
                return None

        self.processed_count += 1
        self.db.insert(scored)

        for sector in scored.affected_sectors:
            self.sector_heat[sector].append(scored.impact_score)
        if scored.impact_score >= self.alert_threshold:
            self.alert_count += 1
            await self.alert_dispatcher.dispatch(scored)
        return scored

    def print_sector_heatmap(self):
        """Print a sector activity heatmap from the session."""
        c = AlertDispatcher.COLORS
        print(f"    {c['WHITE']}{'─' * 72}{c['RESET']}")
        print(f"    {c['WHITE']}SECTOR HEATMAP{c['RESET']}")
        print(f"    {c['WHITE']}{'─' * 72}{c['RESET']}")

        sector_stats = []
        for sector, scores in self.sector_heat.items():
            avg = sum(scores) / len(scores)
            sector_stats.append((sector, len(scores), avg, max(scores)))

        sector_stats.sort(key=lambda x: -x[2])

        for sector, count, avg, peak in sector_stats:
            bar_len = int(avg / 5)
            if avg >= 80:
                color = c["CRITICAL"]
            elif avg >= 60:
                color = c["HIGH"]
            elif avg >= 40:
                color = c["MEDIUM"]
            else:
                color = c["LOW"]
            bar = f"{color}{'█' * bar_len}{'░' * (20 - bar_len)}{c['RESET']}"
            print(f"      {sector:22s} {bar} avg:{avg:5.1f}  peak:{peak:3d}  events:{count}")
        print()

    async def run_feed(self, feed: list[dict], delay: float = 0.8):
        c = AlertDispatcher.COLORS

        print()
        print(f"  {c['WHITE']}╔══════════════════════════════════════════════════════════════════╗{c['RESET']}")
        print(f"  {c['WHITE']}║      NYSE IMPACT NEWS SCREENER v2.0 — Engine Online             ║{c['RESET']}")
        print(f"  {c['WHITE']}║      Sectors: 16  │  Tickers: {len(self.reference_db.tickers):3d}  │  "
              f"Aliases: {len(self.reference_db.aliases):3d}          ║{c['RESET']}")
        vix = self.reference_db.market_state['vix']
        regime = self.reference_db.market_state['market_regime'].upper()
        print(f"  {c['WHITE']}║      Alert Threshold: {self.alert_threshold}/100  │  "
              f"VIX: {vix:.1f} ({regime})  │  Feed: {len(feed)} events   ║{c['RESET']}")
        print(f"  {c['WHITE']}╚══════════════════════════════════════════════════════════════════╝{c['RESET']}")
        print()

        results = []
        for item in feed:
            scored = await self.process_event(item)
            if scored:
                results.append(scored)
            await asyncio.sleep(delay)

        # Session Summary
        print()
        print(f"  {c['WHITE']}{'═' * 76}{c['RESET']}")
        print(f"  {c['WHITE']}SESSION SUMMARY{c['RESET']}")
        print(f"  {c['WHITE']}{'═' * 76}{c['RESET']}")
        print(f"    Events processed:  {self.processed_count}")
        print(f"    Alerts triggered:  {self.alert_count}")

        # Claude API usage stats
        usage = self.claude_scorer.usage_stats
        print(f"    Claude API calls:  {usage['total_calls']}  (skipped: {usage['calls_skipped']})")
        print(f"    Tokens used:       {usage['input_tokens']:,} in / {usage['output_tokens']:,} out")
        print(f"    Estimated cost:    ${usage['estimated_cost_usd']:.4f}")

        if results:
            scores = [r.impact_score for r in results]
            critical = [r for r in results if r.impact_score >= 80]
            high = [r for r in results if 60 <= r.impact_score < 80]
            bullish = [r for r in results if r.direction == Direction.BULLISH]
            bearish = [r for r in results if r.direction == Direction.BEARISH]

            print(f"    Score range:       {min(scores)} — {max(scores)}")
            print(f"    Average score:     {sum(scores) / len(scores):.1f}")
            print(f"    Critical: {len(critical)}  │  High: {len(high)}  │  "
                  f"Bullish: {len(bullish)}  │  Bearish: {len(bearish)}")
            print()

            # Sector Heatmap
            self.print_sector_heatmap()

            if critical:
                print(f"    {c['CRITICAL']}🚨 Critical Events Requiring Immediate Attention:{c['RESET']}")
                for ev in sorted(critical, key=lambda x: -x.impact_score):
                    dir_sym = "▲" if ev.direction == Direction.BULLISH else "▼" if ev.direction == Direction.BEARISH else "●"
                    tickers_str = ', '.join(ev.affected_tickers[:4]) or 'MACRO'
                    contagion_str = f" → +{len(ev.contagion_tickers)} contagion" if ev.contagion_tickers else ""
                    print(f"      [{ev.impact_score:3d}] {ev.urgency.value:8s} {dir_sym} "
                          f"{tickers_str:16s}{contagion_str:20s} │ {ev.headline[:52]}")
        print()

        return results


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    screener = NYSEImpactScreener(alert_threshold=0)
    rss = RSSFeed()
    ws_news = WebSocketNewsFeed()  # auto-detects providers from env vars
    screener.rss = rss
    await start_http_server(screener.db)

    # Wire up global references so WS handler can send state on connect
    _server_module._LIVE_MARKET_STATE = screener.reference_db.live_market
    _server_module._SIGNAL_TRACKER_DB = screener.db
    _server_module._SIGNAL_TRACKER = screener.signal_tracker

    # Initial live market state fetch (VIX, SPY, pre-market, earnings season)
    print("  [MarketState] Fetching initial live market data...")
    await screener.reference_db.live_market.update(force=True)

    # Start signal outcome tracker as a background task
    asyncio.create_task(screener.signal_tracker.run_loop())

    # Start WebSocket news feed listeners (Finnhub, Benzinga, Polygon — whichever has API keys)
    ws_news.start()

    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print("  WebSocket server listening on ws://localhost:8765")
        active = ws_news.active_providers
        if active:
            print(f"  WebSocket news feeds active: {', '.join(active)}")
        print("  Polling RSS feeds every 60 seconds. Press Ctrl+C to stop.\n")
        while True:
            # Refresh market state each cycle (auto-skips if within cooldown)
            await screener.reference_db.live_market.update()

            # ── Drain WebSocket news (real-time, arrives between RSS polls) ───
            ws_items = await ws_news.drain()
            if ws_items:
                print(f"  [WS-News] {len(ws_items)} new articles from WebSocket feeds")
                await screener.run_feed(ws_items, delay=0.1)

            # ── Poll RSS feeds (bulk, every 60s) ─────────────────────────────
            items = await rss.fetch()
            if items:
                print(f"  [RSS] {len(items)} new articles fetched")
                await screener.run_feed(items, delay=0.3)
            else:
                print("  [RSS] No new articles, waiting...")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
