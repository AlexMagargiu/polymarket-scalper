from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class ExitReason(str, Enum):
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit_90c"
    DISCONNECT = "disconnect"
    DAILY_LOSS = "daily_loss_limit"
    MANUAL = "manual"


@dataclass
class Market:
    condition_id: str
    token_id_yes: str
    token_id_no: str
    name: str
    volume_24h: float
    category: str = ""
    is_sports: bool = False


@dataclass
class PricePoint:
    timestamp: float          # unix timestamp in seconds
    midpoint: float
    best_bid: float
    best_ask: float


@dataclass
class Surge:
    market_id: str            # condition_id
    token_id: str
    market_name: str
    direction: Direction
    magnitude: float          # how much the price moved
    window_seconds: float     # how fast the move happened
    price_at_detection: float
    timestamp: float          # unix timestamp


@dataclass
class Trend:
    market_id: str
    token_id: str
    market_name: str
    surge_count: int
    first_surge_price: float
    current_price: float
    window_seconds: float
    timestamp: float


@dataclass
class Position:
    id: Optional[int] = None  # DB id, set after insert
    market_id: str = ""
    token_id: str = ""
    market_name: str = ""
    direction: Direction = Direction.UP
    entry_price: float = 0.0
    entry_fee: float = 0.0
    entry_time: float = 0.0   # unix timestamp
    shares: float = 0.0       # position_size / entry_price
    position_size: float = 0.0
    trailing_peak: float = 0.0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    surge_id: Optional[int] = None


@dataclass
class Trade:
    id: Optional[int] = None
    surge_id: Optional[int] = None
    market_id: str = ""
    token_id: str = ""
    market_name: str = ""
    direction: Direction = Direction.UP
    entry_price: float = 0.0
    entry_fee: float = 0.0
    entry_time: float = 0.0
    exit_price: Optional[float] = None
    exit_fee: Optional[float] = None
    exit_time: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    shares: float = 0.0
    position_size: float = 0.0
    pnl: Optional[float] = None
    peak_price: Optional[float] = None
    max_favorable_excursion: Optional[float] = None
