from __future__ import annotations

from typing import Protocol

from .data import Bar
from .orders import Fill, Order, OrderStatus, OrderType, Side


# ---------------------------------------------------------------------------
# Slippage models
# ---------------------------------------------------------------------------

class SlippageModel(Protocol):
    def calc(self, side: Side, price: float) -> float: ...


class ZeroSlippage:
    def calc(self, side: Side, price: float) -> float:
        return price


class FixedSlippage:
    """Slippage as a fixed dollar amount per share."""

    def __init__(self, amount: float):
        self.amount = amount

    def calc(self, side: Side, price: float) -> float:
        return price + self.amount if side == Side.BUY else price - self.amount


class PercentSlippage:
    """Slippage as a percentage of price."""

    def __init__(self, pct: float):
        """pct: e.g. 0.001 for 0.1%"""
        self.pct = pct

    def calc(self, side: Side, price: float) -> float:
        adj = price * self.pct
        return price + adj if side == Side.BUY else price - adj


# ---------------------------------------------------------------------------
# Commission models
# ---------------------------------------------------------------------------

class CommissionModel(Protocol):
    def calc(self, qty: int, fill_price: float) -> float: ...


class ZeroCommission:
    def calc(self, qty: int, fill_price: float) -> float:
        return 0.0


class PerShareCommission:
    def __init__(self, rate: float):
        self.rate = rate

    def calc(self, qty: int, fill_price: float) -> float:
        return self.rate * qty


class PercentCommission:
    def __init__(self, rate: float):
        """rate: e.g. 0.001 for 0.1%"""
        self.rate = rate

    def calc(self, qty: int, fill_price: float) -> float:
        return self.rate * qty * fill_price


class FlatCommission:
    def __init__(self, fee: float):
        self.fee = fee

    def calc(self, qty: int, fill_price: float) -> float:
        return self.fee


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------

class MatchingEngine:
    """Simulates order matching against OHLCV bars."""

    def __init__(
        self,
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
    ):
        self._slippage = slippage or ZeroSlippage()
        self._commission = commission or ZeroCommission()
        self._orders: dict[str, Order] = {}  # order_id -> Order

    def submit(self, order: Order) -> None:
        order.status = OrderStatus.OPEN
        self._orders[order.order_id] = order

    def cancel(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.is_active:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.is_active and (symbol is None or o.symbol == symbol)
        ]

    def process_bar(self, bar: Bar) -> list[Fill]:
        """Match open orders against the given bar. Returns new fills."""
        fills: list[Fill] = []

        for order in list(self._orders.values()):
            if not order.is_active or order.symbol != bar.symbol:
                continue

            fill_price = self._try_match(order, bar)
            if fill_price is None:
                continue

            commission = self._commission.calc(order.remaining_qty, fill_price)
            fill = Fill(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                qty=order.remaining_qty,
                fill_price=fill_price,
                commission=commission,
                timestamp=bar.timestamp,
            )
            order.filled_qty += fill.qty
            order.status = OrderStatus.FILLED
            fills.append(fill)

        return fills

    def _try_match(self, order: Order, bar: Bar) -> float | None:
        """Return fill price if the order matches this bar, else None."""
        if order.order_type == OrderType.MARKET:
            return self._slippage.calc(order.side, bar.open)

        if order.order_type == OrderType.LIMIT:
            lp = order.limit_price
            if order.side == Side.BUY and bar.low <= lp:
                return min(bar.open, lp)
            if order.side == Side.SELL and bar.high >= lp:
                return max(bar.open, lp)

        if order.order_type == OrderType.STOP:
            sp = order.stop_price
            if order.side == Side.BUY and bar.high >= sp:
                return self._slippage.calc(order.side, sp)
            if order.side == Side.SELL and bar.low <= sp:
                return self._slippage.calc(order.side, sp)

        return None
