from __future__ import annotations

from datetime import datetime, timezone

from .data import Bar
from .matching import CommissionModel, MatchingEngine, SlippageModel
from .orders import Fill, Order, OrderType, Side
from .position import Portfolio, Position


class PaperBroker:
    """Simulated broker: manages orders, executes fills, and tracks portfolio state."""

    def __init__(
        self,
        initial_cash: float,
        slippage: SlippageModel | None = None,
        commission: CommissionModel | None = None,
    ):
        self._portfolio = Portfolio(initial_cash)
        self._engine = MatchingEngine(slippage=slippage, commission=commission)
        self._all_orders: dict[str, Order] = {}

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def submit_order(self, order: Order) -> str:
        order.submitted_at = order.submitted_at or datetime.now(timezone.utc)
        self._engine.submit(order)
        self._all_orders[order.order_id] = order
        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        return self._engine.cancel(order_id)

    def get_order(self, order_id: str) -> Order | None:
        return self._all_orders.get(order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        return self._engine.get_open_orders(symbol)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_position(self, symbol: str) -> Position | None:
        return self._portfolio.positions.get(symbol)

    def get_portfolio(self) -> Portfolio:
        return self._portfolio

    def get_cash(self) -> float:
        return self._portfolio.cash

    # ------------------------------------------------------------------
    # Engine hook (called by BacktestEngine each bar)
    # ------------------------------------------------------------------

    def _process_bar(self, bar: Bar) -> list[Fill]:
        fills = self._engine.process_bar(bar)
        for fill in fills:
            self._portfolio.apply_fill(fill)
        return fills

    # ------------------------------------------------------------------
    # Convenience order constructors
    # ------------------------------------------------------------------

    def create_market_order(self, symbol: str, side: Side, qty: int) -> Order:
        return Order(symbol=symbol, side=side, order_type=OrderType.MARKET, qty=qty)

    def create_limit_order(self, symbol: str, side: Side, qty: int, limit_price: float) -> Order:
        return Order(symbol=symbol, side=side, order_type=OrderType.LIMIT, qty=qty, limit_price=limit_price)

    def create_stop_order(self, symbol: str, side: Side, qty: int, stop_price: float) -> Order:
        return Order(symbol=symbol, side=side, order_type=OrderType.STOP, qty=qty, stop_price=stop_price)
