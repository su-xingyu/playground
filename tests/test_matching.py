import pytest
from datetime import datetime

from paper_trading.data import Bar
from paper_trading.matching import (
    MatchingEngine,
    ZeroSlippage, FixedSlippage, PercentSlippage,
    ZeroCommission, PerShareCommission, PercentCommission, FlatCommission,
)
from paper_trading.orders import Order, OrderType, OrderStatus, Side


def make_bar(open_=100.0, high=110.0, low=90.0, close=105.0, symbol="AAPL") -> Bar:
    return Bar(timestamp=datetime(2024, 1, 2), symbol=symbol, open=open_, high=high, low=low, close=close, volume=1_000_000)


def market_order(side=Side.BUY, qty=10, symbol="AAPL") -> Order:
    return Order(symbol=symbol, side=side, order_type=OrderType.MARKET, qty=qty)


def limit_order(side=Side.BUY, qty=10, price=100.0, symbol="AAPL") -> Order:
    return Order(symbol=symbol, side=side, order_type=OrderType.LIMIT, qty=qty, limit_price=price)


def stop_order(side=Side.BUY, qty=10, price=100.0, symbol="AAPL") -> Order:
    return Order(symbol=symbol, side=side, order_type=OrderType.STOP, qty=qty, stop_price=price)


class TestMarketOrders:
    def test_market_buy_fills_at_open(self):
        engine = MatchingEngine()
        o = market_order(Side.BUY)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=102.0))
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(102.0)
        assert o.status == OrderStatus.FILLED

    def test_market_sell_fills_at_open(self):
        engine = MatchingEngine()
        o = market_order(Side.SELL)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=98.0))
        assert fills[0].fill_price == pytest.approx(98.0)

    def test_market_order_different_symbol_not_filled(self):
        engine = MatchingEngine()
        engine.submit(market_order(symbol="AAPL"))
        fills = engine.process_bar(make_bar(symbol="MSFT"))
        assert len(fills) == 0


class TestLimitOrders:
    def test_limit_buy_fills_when_low_touches(self):
        engine = MatchingEngine()
        o = limit_order(Side.BUY, price=95.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0, low=90.0))
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(95.0)  # min(open=100, limit=95)

    def test_limit_buy_fills_at_open_if_open_below_limit(self):
        engine = MatchingEngine()
        o = limit_order(Side.BUY, price=105.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0, low=98.0))
        assert fills[0].fill_price == pytest.approx(100.0)  # min(open=100, limit=105)

    def test_limit_buy_does_not_fill_when_low_above_limit(self):
        engine = MatchingEngine()
        o = limit_order(Side.BUY, price=85.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(low=90.0))
        assert len(fills) == 0
        assert o.is_active

    def test_limit_sell_fills_when_high_touches(self):
        engine = MatchingEngine()
        o = limit_order(Side.SELL, price=108.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0, high=110.0))
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(108.0)  # max(open=100, limit=108)

    def test_limit_sell_fills_at_open_if_open_above_limit(self):
        engine = MatchingEngine()
        o = limit_order(Side.SELL, price=95.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0, high=110.0))
        assert fills[0].fill_price == pytest.approx(100.0)  # max(open=100, limit=95)

    def test_limit_sell_does_not_fill_when_high_below_limit(self):
        engine = MatchingEngine()
        o = limit_order(Side.SELL, price=115.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(high=110.0))
        assert len(fills) == 0


class TestStopOrders:
    def test_stop_buy_fills_when_high_touches(self):
        engine = MatchingEngine()
        o = stop_order(Side.BUY, price=108.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(high=110.0))
        assert len(fills) == 1
        assert fills[0].fill_price == pytest.approx(108.0)

    def test_stop_buy_does_not_fill_when_high_below(self):
        engine = MatchingEngine()
        o = stop_order(Side.BUY, price=115.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(high=110.0))
        assert len(fills) == 0

    def test_stop_sell_fills_when_low_touches(self):
        engine = MatchingEngine()
        o = stop_order(Side.SELL, price=92.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(low=90.0))
        assert fills[0].fill_price == pytest.approx(92.0)

    def test_stop_sell_does_not_fill_when_low_above(self):
        engine = MatchingEngine()
        o = stop_order(Side.SELL, price=88.0)
        engine.submit(o)
        fills = engine.process_bar(make_bar(low=90.0))
        assert len(fills) == 0


class TestCancelOrder:
    def test_cancel_open_order(self):
        engine = MatchingEngine()
        o = limit_order(Side.BUY, price=50.0)  # won't fill at bar high=110
        engine.submit(o)
        result = engine.cancel(o.order_id)
        assert result is True
        assert o.status == OrderStatus.CANCELLED

    def test_cancel_nonexistent_order(self):
        engine = MatchingEngine()
        assert engine.cancel("nonexistent") is False

    def test_cancelled_order_not_filled(self):
        engine = MatchingEngine()
        o = limit_order(Side.BUY, price=95.0)
        engine.submit(o)
        engine.cancel(o.order_id)
        fills = engine.process_bar(make_bar(low=90.0))
        assert len(fills) == 0


class TestSlippage:
    def test_zero_slippage(self):
        engine = MatchingEngine(slippage=ZeroSlippage())
        o = market_order(Side.BUY)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].fill_price == pytest.approx(100.0)

    def test_fixed_slippage_buy(self):
        engine = MatchingEngine(slippage=FixedSlippage(0.05))
        o = market_order(Side.BUY)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].fill_price == pytest.approx(100.05)

    def test_fixed_slippage_sell(self):
        engine = MatchingEngine(slippage=FixedSlippage(0.05))
        o = market_order(Side.SELL)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].fill_price == pytest.approx(99.95)

    def test_percent_slippage_buy(self):
        engine = MatchingEngine(slippage=PercentSlippage(0.001))
        o = market_order(Side.BUY)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].fill_price == pytest.approx(100.1)

    def test_percent_slippage_sell(self):
        engine = MatchingEngine(slippage=PercentSlippage(0.001))
        o = market_order(Side.SELL)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].fill_price == pytest.approx(99.9)


class TestCommission:
    def test_zero_commission(self):
        engine = MatchingEngine(commission=ZeroCommission())
        o = market_order(qty=100)
        engine.submit(o)
        fills = engine.process_bar(make_bar())
        assert fills[0].commission == pytest.approx(0.0)

    def test_per_share_commission(self):
        engine = MatchingEngine(commission=PerShareCommission(0.01))
        o = market_order(qty=100)
        engine.submit(o)
        fills = engine.process_bar(make_bar())
        assert fills[0].commission == pytest.approx(1.0)

    def test_percent_commission(self):
        engine = MatchingEngine(commission=PercentCommission(0.001))
        o = market_order(qty=100)
        engine.submit(o)
        fills = engine.process_bar(make_bar(open_=100.0))
        assert fills[0].commission == pytest.approx(10.0)

    def test_flat_commission(self):
        engine = MatchingEngine(commission=FlatCommission(5.0))
        o = market_order(qty=100)
        engine.submit(o)
        fills = engine.process_bar(make_bar())
        assert fills[0].commission == pytest.approx(5.0)
