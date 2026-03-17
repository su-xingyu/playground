import pytest
from datetime import datetime

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar
from paper_trading.orders import Order, OrderType, OrderStatus, Side


def make_bar(open_=100.0, high=110.0, low=90.0, close=105.0, symbol="AAPL", ts=None) -> Bar:
    return Bar(
        timestamp=ts or datetime(2024, 1, 2),
        symbol=symbol,
        open=open_, high=high, low=low, close=close,
        volume=1_000_000,
    )


class TestPaperBroker:
    def test_initial_cash(self):
        broker = PaperBroker(100_000.0)
        assert broker.get_cash() == 100_000.0

    def test_submit_market_order_returns_id(self):
        broker = PaperBroker(100_000.0)
        order = broker.create_market_order("AAPL", Side.BUY, 100)
        oid = broker.submit_order(order)
        assert oid == order.order_id

    def test_market_buy_fills_and_updates_position(self):
        broker = PaperBroker(100_000.0)
        order = broker.create_market_order("AAPL", Side.BUY, 100)
        broker.submit_order(order)
        fills = broker._process_bar(make_bar(open_=100.0))
        assert len(fills) == 1
        pos = broker.get_position("AAPL")
        assert pos is not None
        assert pos.qty == 100

    def test_cash_decreases_after_buy_fill(self):
        broker = PaperBroker(100_000.0)
        broker.submit_order(broker.create_market_order("AAPL", Side.BUY, 100))
        broker._process_bar(make_bar(open_=100.0))
        assert broker.get_cash() == pytest.approx(90_000.0)

    def test_sell_position_after_buy(self):
        broker = PaperBroker(100_000.0)
        broker.submit_order(broker.create_market_order("AAPL", Side.BUY, 100))
        broker._process_bar(make_bar(open_=100.0))
        broker.submit_order(broker.create_market_order("AAPL", Side.SELL, 100))
        broker._process_bar(make_bar(open_=110.0))
        pos = broker.get_position("AAPL")
        assert pos.qty == 0
        assert broker.get_cash() == pytest.approx(101_000.0)

    def test_cancel_open_order(self):
        broker = PaperBroker(100_000.0)
        order = broker.create_limit_order("AAPL", Side.BUY, 100, limit_price=50.0)
        oid = broker.submit_order(order)
        assert broker.cancel_order(oid) is True
        assert broker.get_order(oid).status == OrderStatus.CANCELLED

    def test_get_open_orders(self):
        broker = PaperBroker(100_000.0)
        o1 = broker.create_limit_order("AAPL", Side.BUY, 10, limit_price=50.0)
        o2 = broker.create_limit_order("MSFT", Side.BUY, 10, limit_price=50.0)
        broker.submit_order(o1)
        broker.submit_order(o2)
        all_open = broker.get_open_orders()
        aapl_open = broker.get_open_orders("AAPL")
        assert len(all_open) == 2
        assert len(aapl_open) == 1

    def test_get_order_nonexistent_returns_none(self):
        broker = PaperBroker(100_000.0)
        assert broker.get_order("nonexistent") is None

    def test_get_position_nonexistent_returns_none(self):
        broker = PaperBroker(100_000.0)
        assert broker.get_position("AAPL") is None

    def test_limit_order_not_filled_when_price_not_reached(self):
        broker = PaperBroker(100_000.0)
        order = broker.create_limit_order("AAPL", Side.BUY, 100, limit_price=80.0)
        broker.submit_order(order)
        fills = broker._process_bar(make_bar(open_=100.0, low=90.0))
        assert len(fills) == 0
        assert order.is_active

    def test_create_stop_order(self):
        broker = PaperBroker(100_000.0)
        order = broker.create_stop_order("AAPL", Side.SELL, 10, stop_price=95.0)
        broker.submit_order(order)
        fills = broker._process_bar(make_bar(low=90.0))
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(95.0)
