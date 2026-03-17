from __future__ import annotations

from collections import deque
from datetime import datetime

from .orders import Fill, Side


class Position:
    """Tracks a single symbol's holdings using FIFO lot accounting."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        # Each lot: [qty, cost_price]  (mutable so we can partially consume)
        self._long_lots: deque[list] = deque()   # each lot: [qty, cost_price]
        self._short_lots: deque[list] = deque()  # each lot: [qty, cost_price]
        self.realized_pnl: float = 0.0

    @property
    def qty(self) -> int:
        """Net signed quantity. Positive = long, negative = short."""
        long_qty = sum(lot[0] for lot in self._long_lots)
        short_qty = sum(lot[0] for lot in self._short_lots)
        return long_qty - short_qty

    @property
    def avg_cost(self) -> float:
        """Weighted average cost of the current net position."""
        net = self.qty
        if net == 0:
            return 0.0
        if net > 0:
            total_cost = sum(lot[0] * lot[1] for lot in self._long_lots)
            return total_cost / net
        else:
            total_cost = sum(lot[0] * lot[1] for lot in self._short_lots)
            return total_cost / abs(net)

    def unrealized_pnl(self, current_price: float) -> float:
        long_pnl = sum(lot[0] * (current_price - lot[1]) for lot in self._long_lots)
        short_pnl = sum(lot[0] * (lot[1] - current_price) for lot in self._short_lots)
        return long_pnl + short_pnl

    def market_value(self, current_price: float) -> float:
        """Signed market value of the position."""
        return self.qty * current_price

    def apply_fill(self, fill: Fill) -> float:
        """Apply a fill to this position. Returns realized P&L from this fill."""
        realized = 0.0

        if fill.side == Side.BUY:
            if self._short_lots:
                # Cover shorts FIFO
                remaining = fill.qty
                while remaining > 0 and self._short_lots:
                    lot = self._short_lots[0]
                    matched = min(lot[0], remaining)
                    realized += matched * (lot[1] - fill.fill_price)
                    lot[0] -= matched
                    remaining -= matched
                    if lot[0] == 0:
                        self._short_lots.popleft()
                if remaining > 0:
                    self._long_lots.append([remaining, fill.fill_price])
            else:
                self._long_lots.append([fill.qty, fill.fill_price])

        else:  # SELL
            if self._long_lots:
                # Reduce longs FIFO
                remaining = fill.qty
                while remaining > 0 and self._long_lots:
                    lot = self._long_lots[0]
                    matched = min(lot[0], remaining)
                    realized += matched * (fill.fill_price - lot[1])
                    lot[0] -= matched
                    remaining -= matched
                    if lot[0] == 0:
                        self._long_lots.popleft()
                if remaining > 0:
                    self._short_lots.append([remaining, fill.fill_price])
            else:
                self._short_lots.append([fill.qty, fill.fill_price])

        self.realized_pnl += realized
        return realized

    def is_flat(self) -> bool:
        return self.qty == 0


class Portfolio:
    """Tracks cash, positions across all symbols, and fill history."""

    def __init__(self, initial_cash: float):
        if initial_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        self.cash: float = initial_cash
        self.initial_cash: float = initial_cash
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []

    def _get_or_create_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol)
        return self.positions[symbol]

    def apply_fill(self, fill: Fill) -> None:
        pos = self._get_or_create_position(fill.symbol)
        pos.apply_fill(fill)

        # Adjust cash: buys cost money, sells raise cash; commission always reduces cash
        sign = -1 if fill.side == Side.BUY else 1
        self.cash += sign * fill.qty * fill.fill_price - fill.commission

        self.fills.append(fill)

    def total_equity(self, current_prices: dict[str, float]) -> float:
        mkt = sum(
            pos.market_value(current_prices[sym])
            for sym, pos in self.positions.items()
            if sym in current_prices and not pos.is_flat()
        )
        return self.cash + mkt

    def realized_pnl(self) -> float:
        return sum(pos.realized_pnl for pos in self.positions.values())

    def unrealized_pnl(self, current_prices: dict[str, float]) -> float:
        return sum(
            pos.unrealized_pnl(current_prices[sym])
            for sym, pos in self.positions.items()
            if sym in current_prices
        )

    def snapshot(self, timestamp: datetime, prices: dict[str, float]) -> dict:
        equity = self.total_equity(prices)
        return {
            "timestamp": timestamp,
            "equity": equity,
            "cash": self.cash,
            "unrealized_pnl": self.unrealized_pnl(prices),
            "realized_pnl": self.realized_pnl(),
            "net_pnl": equity - self.initial_cash,
        }
