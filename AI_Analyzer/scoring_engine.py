"""
Market Impact Scoring Engine for the NYSE Impact Screener.
"""

import re
import time

from models import EventType, Direction, Urgency, RawNewsEvent, ScoredEvent
from reference_db import NYSEReferenceDB


class MarketImpactScoringEngine:
    """
    Enhanced three-stage scoring pipeline with:
    - Expanded event taxonomy (55+ types)
    - Beta-adjusted impact
    - VIX regime awareness
    - Supply chain amplification
    - Source credibility weighting
    - Earnings season context
    """

    EVENT_BASE_SCORES: dict[str, int] = {
        # Earnings
        "EARNINGS_BEAT": 55, "EARNINGS_MISS": 60,
        "REVENUE_BEAT": 50, "REVENUE_MISS": 55,
        "GUIDANCE_RAISE": 65, "GUIDANCE_CUT": 70,
        # M&A / Corporate
        "MA_ANNOUNCED": 80, "MA_BLOCKED": 75, "SPINOFF": 55,
        "STOCK_BUYBACK": 40, "DIVIDEND_CUT": 65, "DIVIDEND_HIKE": 35,
        "STOCK_SPLIT": 30,
        # Regulatory
        "FDA_APPROVAL": 85, "FDA_REJECTION": 90,
        "REGULATORY_ACTION": 70, "ANTITRUST": 75, "PATENT_RULING": 60,
        # Analyst
        "ANALYST_UPGRADE": 40, "ANALYST_DOWNGRADE": 45, "ANALYST_INITIATION": 30,
        # Leadership
        "CEO_DEPARTURE": 65, "CFO_DEPARTURE": 55, "BOARD_SHAKEUP": 50,
        # Insider
        "INSIDER_BUY": 35, "INSIDER_SELL": 45,
        # Macro
        "MACRO_CPI": 70, "MACRO_FOMC": 90, "MACRO_NFP": 75,
        "MACRO_GDP": 65, "MACRO_PPI": 55, "MACRO_RETAIL_SALES": 50,
        "MACRO_HOUSING": 45, "MACRO_PMI": 50,
        # Sector-Specific
        "CHIP_EXPORT_CONTROL": 85, "OIL_PRODUCTION_CUT": 80, "OIL_INVENTORY": 50,
        "PIPELINE_DISRUPTION": 70, "POWER_GRID_EVENT": 60, "DRUG_TRIAL_DATA": 80,
        "CYBER_BREACH": 65, "SUPPLY_CHAIN_DISRUPTION": 70,
        "PRODUCT_RECALL": 60, "CONTRACT_WIN": 55, "CONTRACT_LOSS": 60,
        # Distress
        "BANKRUPTCY": 95, "CREDIT_DOWNGRADE": 65, "CREDIT_UPGRADE": 50,
        "DEBT_DEFAULT": 90,
        # Special
        "ACTIVIST_STAKE": 60, "SHORT_SQUEEZE": 70,
        "GEOPOLITICAL": 75, "TARIFF": 75, "SANCTIONS": 80,
        "NATURAL_DISASTER": 65,
        "UNKNOWN": 20,
    }

    SOURCE_MULTIPLIERS: dict[int, float] = {
        1: 1.15,   # Institutional (Reuters, Bloomberg, Fed)
        2: 1.00,   # Professional (Benzinga, SEC EDGAR, CNBC)
        3: 0.70,   # Social (Twitter/X, Reddit)
    }

    MCAP_MULTIPLIERS: dict[str, float] = {
        "mega": 1.20,   # > $200B
        "large": 1.00,  # $10B-$200B
        "mid": 0.85,    # $2B-$10B
        "small": 0.70,  # < $2B
        "unknown": 0.80,
    }

    EVENT_PATTERNS: list[tuple[str, EventType, float]] = [
        # FDA / Drug
        (r"fda\s+approv", EventType.FDA_APPROVAL, 0.9),
        (r"fda\s+reject|fda\s+den|complete\s+response\s+letter|crl\b", EventType.FDA_REJECTION, 0.9),
        (r"phase\s+[123i]+.*(?:data|results|endpoint|efficacy)|clinical\s+trial.*(?:success|fail|miss)", EventType.DRUG_TRIAL_DATA, 0.85),
        # Earnings / Revenue / Guidance
        (r"beat.*(?:earnings|eps)|(?:earnings|eps).*beat|tops\s+estimates|(?:eps|earnings)\s+surprise", EventType.EARNINGS_BEAT, 0.85),
        (r"miss.*(?:earnings|eps)|(?:earnings|eps).*miss|falls?\s+short|disappointing\s+(?:earnings|eps)", EventType.EARNINGS_MISS, 0.85),
        (r"revenue.*beat|revenue.*tops|revenue.*exceed", EventType.REVENUE_BEAT, 0.8),
        (r"revenue.*miss|revenue.*falls?\s+short|revenue.*disappoint", EventType.REVENUE_MISS, 0.8),
        (r"rais(?:e[sd]?|ing)\s+(?:full.year\s+)?guidance|guidance\s+(?:raise|up|higher|above)", EventType.GUIDANCE_RAISE, 0.85),
        (r"(?:cut|lower|slash|reduce)[sd]?\s+guidance|guidance\s+(?:cut|down|below|lower)", EventType.GUIDANCE_CUT, 0.85),
        # M&A / Corporate Actions
        (r"acquir|merger|buyout|takeover|(?:to\s+buy)|(?:deal\s+to)", EventType.MA_ANNOUNCED, 0.9),
        (r"(?:block|reject|halt)\w*\s+(?:merger|acquisition|deal)|antitrust\s+(?:block|challenge)", EventType.MA_BLOCKED, 0.85),
        (r"spin\s*off|spin\s*out|separate\s+unit|split\s+into", EventType.SPINOFF, 0.8),
        (r"buyback|share\s+repurchas|stock\s+repurchas", EventType.STOCK_BUYBACK, 0.75),
        (r"(?:cut|slash|suspend|eliminat)\w*\s+dividend", EventType.DIVIDEND_CUT, 0.85),
        (r"(?:rais|hik|increas|boost)\w*\s+dividend|special\s+dividend", EventType.DIVIDEND_HIKE, 0.75),
        # Analyst
        (r"upgrade[sd]?|raises?\s+(?:price\s+)?target|overweight", EventType.ANALYST_UPGRADE, 0.75),
        (r"downgrade[sd]?|lower[sd]?\s+(?:price\s+)?target|underweight|sell\s+rating", EventType.ANALYST_DOWNGRADE, 0.75),
        (r"initiat\w+\s+coverage|new\s+coverage", EventType.ANALYST_INITIATION, 0.7),
        # Leadership
        (r"ceo\s+(?:resign|depart|step|fired|ousted|retire|leaves?)", EventType.CEO_DEPARTURE, 0.85),
        (r"cfo\s+(?:resign|depart|step|fired|ousted|retire|leaves?)", EventType.CFO_DEPARTURE, 0.8),
        (r"board.*(?:shakeup|overhaul|resign)|director.*resign", EventType.BOARD_SHAKEUP, 0.75),
        # Macro
        (r"cpi\s+(?:rise|fall|surge|drop|unexpect|surprise|higher|lower|hot)", EventType.MACRO_CPI, 0.8),
        (r"(?:fed|fomc)\s+(?:rate|hike|cut|hold|pause|hawkish|dovish|decision)", EventType.MACRO_FOMC, 0.9),
        (r"(?:nonfarm|non-farm|payroll|jobs?\s+report).*(?:surge|plunge|beat|miss|add)", EventType.MACRO_NFP, 0.8),
        (r"gdp\s+(?:grow|contract|surge|miss|beat|shrink|revis)", EventType.MACRO_GDP, 0.8),
        (r"ppi\s+(?:rise|fall|surge|drop|unexpect|hot)", EventType.MACRO_PPI, 0.75),
        (r"retail\s+sales?\s+(?:surge|plunge|beat|miss|drop|rise)", EventType.MACRO_RETAIL_SALES, 0.75),
        (r"(?:housing\s+starts?|existing\s+home|new\s+home)\s+(?:surge|plunge|drop|rise|fall)", EventType.MACRO_HOUSING, 0.7),
        (r"(?:pmi|manufacturing\s+index|ism)\s+(?:expand|contract|surge|fall|surprise)", EventType.MACRO_PMI, 0.75),
        # Sector-Specific
        (r"(?:chip|semiconductor)\s+(?:export|restrict|ban|sanction|control)|huawei.*chip|chip.*(?:china|beijing)", EventType.CHIP_EXPORT_CONTROL, 0.9),
        (r"opec.*(?:cut|reduce|curb|slash)|production\s+cut|oil\s+(?:cut|curtail)", EventType.OIL_PRODUCTION_CUT, 0.85),
        (r"(?:crude|oil)\s+inventor(?:y|ies)\s+(?:build|draw|surge|drop|surprise)", EventType.OIL_INVENTORY, 0.75),
        (r"pipeline\s+(?:explosi|ruptur|leak|shut|disrupt|attack)", EventType.PIPELINE_DISRUPTION, 0.85),
        (r"(?:power\s+grid|blackout|grid\s+failure|rolling\s+blackout|electricity.*outage)", EventType.POWER_GRID_EVENT, 0.8),
        (r"cyber\s*(?:attack|breach|hack|incident|ransomware)|data\s+breach|hack(?:ed|ing)", EventType.CYBER_BREACH, 0.85),
        (r"supply\s+chain\s+(?:disrupt|crisis|shortage|bottleneck)", EventType.SUPPLY_CHAIN_DISRUPTION, 0.8),
        (r"(?:product|vehicle|food)\s+recall|safety\s+recall|voluntary\s+recall", EventType.PRODUCT_RECALL, 0.75),
        (r"(?:award|win|secur)\w*\s+(?:\$[\d.]+[BbMm]?\s+)?contract|defense\s+contract", EventType.CONTRACT_WIN, 0.8),
        (r"(?:los[est]+|fail)\w*\s+contract|contract\s+(?:cancel|terminat|lost)", EventType.CONTRACT_LOSS, 0.8),
        # Insider
        (r"insider\s+(?:buy|purchas)", EventType.INSIDER_BUY, 0.7),
        (r"insider\s+(?:sell|sold|dump)", EventType.INSIDER_SELL, 0.7),
        # Distress
        (r"bankrupt|chapter\s+(?:7|11)|default|insolven", EventType.BANKRUPTCY, 0.95),
        (r"(?:moody|s&p|fitch)\s+(?:downgrad|cut|lower)\w*\s+(?:credit|rating|debt)", EventType.CREDIT_DOWNGRADE, 0.85),
        (r"(?:moody|s&p|fitch)\s+(?:upgrad|rais)\w*\s+(?:credit|rating|debt)", EventType.CREDIT_UPGRADE, 0.8),
        # Special
        (r"sec\s+(?:charg|investigat|probe|lawsuit|fine|enforcement)", EventType.REGULATORY_ACTION, 0.85),
        (r"antitrust|(?:doj|ftc)\s+(?:su|block|challenge|investigat)", EventType.ANTITRUST, 0.85),
        (r"activist|stake|13d|proxy\s+fight|hostile", EventType.ACTIVIST_STAKE, 0.8),
        (r"short\s+squeeze|gamma\s+squeeze|meme\s+stock", EventType.SHORT_SQUEEZE, 0.75),
        (r"sanction|tariff|trade\s+war|trade\s+restrict|embargo", EventType.TARIFF, 0.8),
        (r"geopolit|war\s+|military\s+strike|invasion|conflict\s+escalat", EventType.GEOPOLITICAL, 0.75),
        (r"hurricane|earthquake|wildfire|flood|tsunami|natural\s+disaster", EventType.NATURAL_DISASTER, 0.8),
        (r"patent.*(?:invalid|upheld|ruling|granted|infring)", EventType.PATENT_RULING, 0.75),
    ]

    BULLISH_KEYWORDS = {
        "beat", "surge", "soar", "rally", "approval", "upgrade", "record",
        "breakthrough", "growth", "bullish", "outperform", "buy", "strong",
        "exceeds", "raises", "dividend", "accelerat", "optimis", "boom",
        "profit", "recovery", "expand", "wins", "awarded", "above",
        "positive", "upside", "best", "tops", "surprise", "blowout",
        "hike", "buyback", "repurchas",
    }

    BEARISH_KEYWORDS = {
        "miss", "plunge", "crash", "decline", "rejection", "downgrade",
        "bankruptcy", "default", "warning", "layoff", "recall", "probe",
        "investigation", "fraud", "loss", "bearish", "underperform", "sell",
        "cuts", "slashes", "disappointing", "weak", "concern", "fear",
        "sanctions", "tariff", "halt", "suspend", "breach", "hack",
        "shortage", "crisis", "failure", "below", "worst", "downside",
        "slash", "negative", "resign", "depart", "oust", "restrict",
    }

    def __init__(self, reference_db: NYSEReferenceDB):
        self.db = reference_db

    def classify_event(self, headline: str, body: str = "") -> tuple[EventType, float]:
        text = f"{headline} {body}".lower()
        best_match = (EventType.UNKNOWN, 0.0)
        for pattern, event_type, base_conf in self.EVENT_PATTERNS:
            if re.search(pattern, text):
                if base_conf > best_match[1]:
                    best_match = (event_type, base_conf)
        return best_match

    def analyze_sentiment(self, headline: str, body: str = "") -> float:
        text = f"{headline} {body}".lower()
        words = set(re.findall(r'\b\w+\b', text))
        bull_count = len(words & self.BULLISH_KEYWORDS)
        bear_count = len(words & self.BEARISH_KEYWORDS)
        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return round((bull_count - bear_count) / total, 3)

    def compute_impact_score(
        self,
        event_type: EventType,
        sentiment: float,
        source_tier: int,
        affected_tickers: list[str],
        contagion_tickers: list[str],
    ) -> int:
        # Base score from event type
        base = self.EVENT_BASE_SCORES.get(event_type.value, 20)

        # Sentiment magnitude amplifier
        sentiment_amp = 1.0 + (abs(sentiment) * 0.3)

        # Source credibility
        source_mult = self.SOURCE_MULTIPLIERS.get(source_tier, 0.8)

        # Market cap significance (use highest mcap among affected)
        mcap_mult = max(
            (self.MCAP_MULTIPLIERS.get(self.db.get_market_cap_bucket(t), 0.8)
             for t in affected_tickers),
            default=0.8
        )

        # Beta amplifier — high-beta stocks react more violently
        max_beta = max((self.db.get_beta(t) for t in affected_tickers), default=1.0)
        beta_amp = 1.0 + max(0, (max_beta - 1.0) * 0.15)

        # VIX regime amplifier
        vix_mult = self.db.get_vix_regime_multiplier()

        # Time of day
        tod_mult = self.db.get_time_of_day_multiplier()

        # Multi-ticker / contagion bonus
        ticker_bonus = min(len(affected_tickers) * 3, 12)
        contagion_bonus = min(len(contagion_tickers) * 2, 10)

        # Earnings season dampener for earnings events (more noise)
        earnings_events = {"EARNINGS_BEAT", "EARNINGS_MISS", "REVENUE_BEAT",
                           "REVENUE_MISS", "GUIDANCE_RAISE", "GUIDANCE_CUT"}
        season_mult = 0.9 if (self.db.market_state.get("is_earnings_season")
                              and event_type.value in earnings_events) else 1.0

        # Compute raw score
        raw = (base * sentiment_amp * source_mult * mcap_mult * beta_amp
               * vix_mult * tod_mult * season_mult) + ticker_bonus + contagion_bonus

        return max(1, min(100, int(round(raw))))

    def determine_direction(self, event_type: EventType, sentiment: float) -> Direction:
        inherently_bearish = {
            EventType.EARNINGS_MISS, EventType.REVENUE_MISS, EventType.GUIDANCE_CUT,
            EventType.FDA_REJECTION, EventType.MA_BLOCKED,
            EventType.ANALYST_DOWNGRADE, EventType.CEO_DEPARTURE, EventType.CFO_DEPARTURE,
            EventType.INSIDER_SELL, EventType.BANKRUPTCY, EventType.DEBT_DEFAULT,
            EventType.CREDIT_DOWNGRADE, EventType.DIVIDEND_CUT,
            EventType.REGULATORY_ACTION, EventType.ANTITRUST,
            EventType.CYBER_BREACH, EventType.PRODUCT_RECALL, EventType.CONTRACT_LOSS,
            EventType.PIPELINE_DISRUPTION,
        }
        inherently_bullish = {
            EventType.EARNINGS_BEAT, EventType.REVENUE_BEAT, EventType.GUIDANCE_RAISE,
            EventType.FDA_APPROVAL, EventType.MA_ANNOUNCED,
            EventType.ANALYST_UPGRADE, EventType.ANALYST_INITIATION,
            EventType.INSIDER_BUY, EventType.CREDIT_UPGRADE,
            EventType.DIVIDEND_HIKE, EventType.STOCK_BUYBACK,
            EventType.CONTRACT_WIN, EventType.DRUG_TRIAL_DATA,
        }

        if event_type in inherently_bearish:
            return Direction.BEARISH
        elif event_type in inherently_bullish:
            return Direction.BULLISH
        elif sentiment > 0.2:
            return Direction.BULLISH
        elif sentiment < -0.2:
            return Direction.BEARISH
        return Direction.NEUTRAL

    def determine_urgency(self, impact_score: int, event_type: EventType) -> Urgency:
        flash_events = {
            EventType.MACRO_FOMC, EventType.BANKRUPTCY, EventType.DEBT_DEFAULT,
            EventType.GEOPOLITICAL, EventType.FDA_APPROVAL, EventType.FDA_REJECTION,
        }
        if impact_score >= 90 or (impact_score >= 80 and event_type in flash_events):
            return Urgency.FLASH
        elif impact_score >= 70:
            return Urgency.HIGH
        elif impact_score >= 45:
            return Urgency.STANDARD
        return Urgency.LOW

    def score_event(self, event: RawNewsEvent, entities: dict) -> ScoredEvent:
        t_start = time.perf_counter()

        event_type, confidence = self.classify_event(event.headline, event.body)
        sentiment = self.analyze_sentiment(event.headline, event.body)

        impact_score = self.compute_impact_score(
            event_type=event_type,
            sentiment=sentiment,
            source_tier=event.source_tier,
            affected_tickers=entities["tickers"],
            contagion_tickers=entities.get("contagion", []),
        )

        direction = self.determine_direction(event_type, sentiment)
        urgency = self.determine_urgency(impact_score, event_type)

        latency_ms = (time.perf_counter() - t_start) * 1000

        return ScoredEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            headline=event.headline,
            source=event.source,
            source_tier=event.source_tier,
            event_type=event_type,
            urgency=urgency,
            sentiment=sentiment,
            direction=direction,
            impact_score=impact_score,
            affected_tickers=entities["tickers"],
            affected_sectors=entities["sectors"],
            affected_etfs=entities["etfs"],
            supply_chain_exposure=entities.get("supply_chain", []),
            contagion_tickers=entities.get("contagion", []),
            url=event.url,
            latency_ms=round(latency_ms, 2),
            ws_source=event.ws_source,
        )
