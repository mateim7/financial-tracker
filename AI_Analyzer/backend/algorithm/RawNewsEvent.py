from dataclasses import dataclass, field

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


