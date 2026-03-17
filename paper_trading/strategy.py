from __future__ import annotations

from abc import ABC, abstractmethod

from .broker import PaperBroker
from .data import Bar
from .orders import Fill, Order, OrderType, Side


class Strategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self):
        self._broker: PaperBroker | None = None
        self.current_bar: Bar | None = None

    @property
    def broker(self) -> PaperBroker:
        if self._broker is None:
            raise RuntimeError("Strategy not attached to a broker. Use BacktestEngine to run.")
        return self._broker

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Called once before the first bar."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> None:
        """Called on every bar. Implement your trading logic here."""

    def on_fill(self, fill: Fill) -> None:
        """Called whenever a fill occurs."""

    def on_stop(self) -> None:
        """Called once after the last bar."""

    # ------------------------------------------------------------------
    # Order helpers
    # ------------------------------------------------------------------

    def buy(
        self,
        symbol: str,
        qty: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> str:
        order = Order(
            symbol=symbol,
            side=Side.BUY,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        return self.broker.submit_order(order)

    def sell(
        self,
        symbol: str,
        qty: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> str:
        order = Order(
            symbol=symbol,
            side=Side.SELL,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        return self.broker.submit_order(order)

    def position_qty(self, symbol: str) -> int:
        pos = self.broker.get_position(symbol)
        return pos.qty if pos else 0

    def cash(self) -> float:
        return self.broker.get_cash()
