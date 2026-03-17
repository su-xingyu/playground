import pytest
from datetime import datetime

from paper_trading.orders import Fill, Side
from paper_trading.position import Position, Portfolio


def make_fill(side: Side, qty: int, price: float, symbol: str = "AAPL", commission: float = 0.0) -> Fill:
    return Fill(
        order_id="ord-1",
        symbol=symbol,
        side=side,
        qty=qty,
        fill_price=price,
        commission=commission,
        timestamp=datetime(2024, 1, 1),
    )


class TestPosition:
    def test_initial_state(self):
        pos = Position("AAPL")
        assert pos.qty == 0
        assert pos.avg_cost == 0.0
        assert pos.realized_pnl == 0.0
        assert pos.is_flat()

    def test_buy_creates_long(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 100, 150.0))
        assert pos.qty == 100
        assert pos.avg_cost == 150.0
        assert not pos.is_flat()

    def test_avg_cost_two_lots(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 100, 100.0))
        pos.apply_fill(make_fill(Side.BUY, 100, 200.0))
        assert pos.qty == 200
        assert pos.avg_cost == 150.0

    def test_unrealized_pnl(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 100, 100.0))
        assert pos.unrealized_pnl(110.0) == pytest.approx(1000.0)
        assert pos.unrealized_pnl(90.0) == pytest.approx(-1000.0)

    def test_sell_full_position_realized_pnl(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 100, 100.0))
        realized = pos.apply_fill(make_fill(Side.SELL, 100, 120.0))
        assert realized == pytest.approx(2000.0)
        assert pos.realized_pnl == pytest.approx(2000.0)
        assert pos.qty == 0
        assert pos.is_flat()

    def test_fifo_partial_sell(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 50, 100.0))   # lot1: 50 @ 100
        pos.apply_fill(make_fill(Side.BUY, 50, 200.0))   # lot2: 50 @ 200
        # sell 50 — should consume lot1 first (FIFO)
        realized = pos.apply_fill(make_fill(Side.SELL, 50, 150.0))
        assert realized == pytest.approx(50 * (150.0 - 100.0))   # 2500
        assert pos.qty == 50
        assert pos.avg_cost == pytest.approx(200.0)  # only lot2 remains

    def test_fifo_spans_two_lots(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 30, 100.0))
        pos.apply_fill(make_fill(Side.BUY, 70, 150.0))
        realized = pos.apply_fill(make_fill(Side.SELL, 50, 200.0))
        # 30 @ 100 → P&L = 30*(200-100) = 3000
        # 20 @ 150 → P&L = 20*(200-150) = 1000  → total = 4000
        assert realized == pytest.approx(4000.0)

    def test_short_selling(self):
        pos = Position("AAPL")
        realized = pos.apply_fill(make_fill(Side.SELL, 50, 150.0))
        assert realized == 0.0  # opening a short: no realized P&L
        assert pos.qty == -50

    def test_short_cover_profit(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.SELL, 50, 150.0))
        realized = pos.apply_fill(make_fill(Side.BUY, 50, 100.0))
        assert realized == pytest.approx(50 * (150.0 - 100.0))
        assert pos.is_flat()

    def test_market_value(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.BUY, 100, 100.0))
        assert pos.market_value(120.0) == pytest.approx(12000.0)

    def test_market_value_short(self):
        pos = Position("AAPL")
        pos.apply_fill(make_fill(Side.SELL, 100, 150.0))
        assert pos.market_value(150.0) == pytest.approx(-15000.0)


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(100_000.0)
        assert p.cash == 100_000.0
        assert p.total_equity({}) == 100_000.0

    def test_negative_cash_rejected(self):
        with pytest.raises(ValueError):
            Portfolio(-1.0)

    def test_buy_reduces_cash(self):
        p = Portfolio(100_000.0)
        fill = make_fill(Side.BUY, 100, 150.0)
        p.apply_fill(fill)
        assert p.cash == pytest.approx(100_000.0 - 100 * 150.0)

    def test_sell_increases_cash(self):
        p = Portfolio(100_000.0)
        p.apply_fill(make_fill(Side.BUY, 100, 150.0))
        p.apply_fill(make_fill(Side.SELL, 100, 160.0))
        # cash after buy: 85000; after sell: 85000 + 16000 = 101000
        assert p.cash == pytest.approx(85_000.0 + 16_000.0)

    def test_commission_reduces_cash(self):
        p = Portfolio(100_000.0)
        fill = make_fill(Side.BUY, 100, 100.0, commission=10.0)
        p.apply_fill(fill)
        assert p.cash == pytest.approx(100_000.0 - 100 * 100.0 - 10.0)

    def test_total_equity_reflects_price_change(self):
        p = Portfolio(100_000.0)
        p.apply_fill(make_fill(Side.BUY, 100, 100.0))
        # cash: 90000, position: 100 shares * 110 = 11000 → equity = 101000
        assert p.total_equity({"AAPL": 110.0}) == pytest.approx(101_000.0)

    def test_unrealized_pnl(self):
        p = Portfolio(100_000.0)
        p.apply_fill(make_fill(Side.BUY, 100, 100.0))
        assert p.unrealized_pnl({"AAPL": 110.0}) == pytest.approx(1000.0)

    def test_realized_pnl(self):
        p = Portfolio(100_000.0)
        p.apply_fill(make_fill(Side.BUY, 100, 100.0))
        p.apply_fill(make_fill(Side.SELL, 100, 120.0))
        assert p.realized_pnl() == pytest.approx(2000.0)

    def test_snapshot_keys(self):
        p = Portfolio(100_000.0)
        snap = p.snapshot(datetime(2024, 1, 1), {})
        assert set(snap.keys()) == {"timestamp", "equity", "cash", "unrealized_pnl", "realized_pnl", "net_pnl"}

    def test_snapshot_net_pnl(self):
        p = Portfolio(100_000.0)
        p.apply_fill(make_fill(Side.BUY, 100, 100.0))
        p.apply_fill(make_fill(Side.SELL, 100, 120.0))
        snap = p.snapshot(datetime(2024, 1, 1), {})
        assert snap["net_pnl"] == pytest.approx(2000.0)
