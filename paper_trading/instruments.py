from dataclasses import dataclass, field


@dataclass
class Instrument:
    symbol: str
    tick_size: float = 0.01
    lot_size: int = 1
    currency: str = "USD"

    def __post_init__(self):
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.lot_size < 1:
            raise ValueError("lot_size must be >= 1")
