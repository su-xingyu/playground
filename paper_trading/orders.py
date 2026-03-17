from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: Side
    order_type: OrderType
    qty: int
    limit_price: float | None = None
    stop_price: float | None = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    submitted_at: datetime | None = None

    def __post_init__(self):
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price required for LIMIT orders")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("stop_price required for STOP orders")

    @property
    def remaining_qty(self) -> int:
        return self.qty - self.filled_qty

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    fill_price: float
    commission: float
    timestamp: datetime
    fill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
