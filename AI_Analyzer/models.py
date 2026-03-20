"""
Domain models and enumerations for the NYSE Impact Screener.
"""

from dataclasses import dataclass, field
from enum import Enum


class Direction(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Urgency(Enum):
    FLASH = "FLASH"          # Breaking — requires immediate action
    HIGH = "HIGH"            # Significant — act within minutes
    STANDARD = "STANDARD"    # Notable — review within the hour
    LOW = "LOW"              # Informational — end-of-day digest


class EventType(Enum):
    # Earnings & Revenue
    EARNINGS_BEAT = "EARNINGS_BEAT"
    EARNINGS_MISS = "EARNINGS_MISS"
    REVENUE_BEAT = "REVENUE_BEAT"
    REVENUE_MISS = "REVENUE_MISS"
    GUIDANCE_RAISE = "GUIDANCE_RAISE"
    GUIDANCE_CUT = "GUIDANCE_CUT"
    # M&A and Corporate Actions
    MA_ANNOUNCED = "MA_ANNOUNCED"
    MA_BLOCKED = "MA_BLOCKED"
    SPINOFF = "SPINOFF"
    STOCK_BUYBACK = "STOCK_BUYBACK"
    DIVIDEND_CUT = "DIVIDEND_CUT"
    DIVIDEND_HIKE = "DIVIDEND_HIKE"
    STOCK_SPLIT = "STOCK_SPLIT"
    # Regulatory & Legal
    FDA_APPROVAL = "FDA_APPROVAL"
    FDA_REJECTION = "FDA_REJECTION"
    REGULATORY_ACTION = "REGULATORY_ACTION"
    ANTITRUST = "ANTITRUST"
    PATENT_RULING = "PATENT_RULING"
    # Analyst Actions
    ANALYST_UPGRADE = "ANALYST_UPGRADE"
    ANALYST_DOWNGRADE = "ANALYST_DOWNGRADE"
    ANALYST_INITIATION = "ANALYST_INITIATION"
    # Leadership
    CEO_DEPARTURE = "CEO_DEPARTURE"
    CFO_DEPARTURE = "CFO_DEPARTURE"
    BOARD_SHAKEUP = "BOARD_SHAKEUP"
    # Insider Activity
    INSIDER_BUY = "INSIDER_BUY"
    INSIDER_SELL = "INSIDER_SELL"
    # Macro Events
    MACRO_CPI = "MACRO_CPI"
    MACRO_FOMC = "MACRO_FOMC"
    MACRO_NFP = "MACRO_NFP"
    MACRO_GDP = "MACRO_GDP"
    MACRO_PPI = "MACRO_PPI"
    MACRO_RETAIL_SALES = "MACRO_RETAIL_SALES"
    MACRO_HOUSING = "MACRO_HOUSING"
    MACRO_PMI = "MACRO_PMI"
    # Sector-Specific
    CHIP_EXPORT_CONTROL = "CHIP_EXPORT_CONTROL"
    OIL_PRODUCTION_CUT = "OIL_PRODUCTION_CUT"
    OIL_INVENTORY = "OIL_INVENTORY"
    PIPELINE_DISRUPTION = "PIPELINE_DISRUPTION"
    POWER_GRID_EVENT = "POWER_GRID_EVENT"
    DRUG_TRIAL_DATA = "DRUG_TRIAL_DATA"
    CYBER_BREACH = "CYBER_BREACH"
    SUPPLY_CHAIN_DISRUPTION = "SUPPLY_CHAIN_DISRUPTION"
    PRODUCT_RECALL = "PRODUCT_RECALL"
    CONTRACT_WIN = "CONTRACT_WIN"
    CONTRACT_LOSS = "CONTRACT_LOSS"
    # Distress
    BANKRUPTCY = "BANKRUPTCY"
    CREDIT_DOWNGRADE = "CREDIT_DOWNGRADE"
    CREDIT_UPGRADE = "CREDIT_UPGRADE"
    DEBT_DEFAULT = "DEBT_DEFAULT"
    # Special
    ACTIVIST_STAKE = "ACTIVIST_STAKE"
    SHORT_SQUEEZE = "SHORT_SQUEEZE"
    GEOPOLITICAL = "GEOPOLITICAL"
    TARIFF = "TARIFF"
    SANCTIONS = "SANCTIONS"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    UNKNOWN = "UNKNOWN"


@dataclass
class RawNewsEvent:
    """Normalized news event from any source."""
    event_id: str
    timestamp: float
    source: str
    source_tier: int          # 1=institutional, 2=professional, 3=social
    headline: str
    body: str = ""
    raw_tickers: list[str] = field(default_factory=list)
    url: str = ""
    ws_source: bool = False   # True if from WebSocket feed, False if RSS


@dataclass
class ScoredEvent:
    """Fully processed and scored news event."""
    event_id: str
    timestamp: float
    headline: str
    source: str
    source_tier: int
    event_type: EventType
    urgency: Urgency
    sentiment: float          # -1.0 to +1.0
    direction: Direction
    impact_score: int         # 1-100
    affected_tickers: list[str] = field(default_factory=list)
    affected_sectors: list[str] = field(default_factory=list)
    affected_etfs: list[str] = field(default_factory=list)
    supply_chain_exposure: list[str] = field(default_factory=list)
    contagion_tickers: list[str] = field(default_factory=list)
    brief: str = ""
    buy_signal: str = ""
    buy_confidence: int = 0
    reasoning: list[str] = field(default_factory=list)
    risk: str = ""
    time_horizon: str = ""
    correlated_moves: list[str] = field(default_factory=list)
    ticker_signals: dict = field(default_factory=dict)  # {ticker: {"signal": "BUY"/"SELL"/"HOLD", "confidence": int}}
    url: str = ""
    stock_availability: dict = field(default_factory=dict)
    price_data: dict = field(default_factory=dict)
    momentum_context: str = ""  # Claude's explanation of volume/price momentum alignment
    insider_activity: dict = field(default_factory=dict)   # {ticker: [insider_tx, ...]} from SEC Form 4
    insider_context: str = ""   # Claude's explanation of how insider activity influenced the signal
    latency_ms: float = 0.0
    ws_source: bool = False   # True if from WebSocket feed
