from dataclasses import dataclass, field
from backend.algorithm.Direction import Direction
from backend.algorithm.EventType import EventType
from backend.algorithm.Urgency import Urgency

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

