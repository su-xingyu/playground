import pytest
from datetime import datetime

from paper_trading.orders import Side, OrderType, OrderStatus, Order, Fill


def make_market_order(**kwargs):
    defaults = dict(symbol="AAPL", side=Side.BUY, order_type=OrderType.MARKET, qty=10)
    defaults.update(kwargs)
    return Order(**defaults)


class TestOrder:
    def test_defaults(self):
        o = make_market_order()
        assert o.status == OrderStatus.PENDING
        assert o.filled_qty == 0
        assert o.remaining_qty == 10
        assert not o.is_active

    def test_is_active_when_open(self):
        o = make_market_order()
        o.status = OrderStatus.OPEN
        assert o.is_active

    def test_is_active_when_partially_filled(self):
        o = make_market_order()
        o.status = OrderStatus.PARTIALLY_FILLED
        assert o.is_active

    def test_is_not_active_when_filled(self):
        o = make_market_order()
        o.status = OrderStatus.FILLED
        assert not o.is_active

    def test_remaining_qty(self):
        o = make_market_order(qty=10)
        o.filled_qty = 4
        assert o.remaining_qty == 6

    def test_limit_order_requires_limit_price(self):
        with pytest.raises(ValueError, match="limit_price"):
            Order(symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, qty=10)

    def test_stop_order_requires_stop_price(self):
        with pytest.raises(ValueError, match="stop_price"):
            Order(symbol="AAPL", side=Side.BUY, order_type=OrderType.STOP, qty=10)

    def test_zero_qty_rejected(self):
        with pytest.raises(ValueError):
            Order(symbol="AAPL", side=Side.BUY, order_type=OrderType.MARKET, qty=0)

    def test_limit_order_ok(self):
        o = Order(symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, qty=5, limit_price=150.0)
        assert o.limit_price == 150.0

    def test_order_id_unique(self):
        a = make_market_order()
        b = make_market_order()
        assert a.order_id != b.order_id


class TestFill:
    def test_fill_construction(self):
        f = Fill(
            order_id="ord-1",
            symbol="AAPL",
            side=Side.BUY,
            qty=10,
            fill_price=150.0,
            commission=1.0,
            timestamp=datetime(2024, 1, 1),
        )
        assert f.qty == 10
        assert f.fill_price == 150.0
        assert f.fill_id  # auto-generated

    def test_fill_id_unique(self):
        kwargs = dict(order_id="x", symbol="AAPL", side=Side.BUY, qty=1, fill_price=100.0, commission=0.0, timestamp=datetime(2024, 1, 1))
        a = Fill(**kwargs)
        b = Fill(**kwargs)
        assert a.fill_id != b.fill_id
