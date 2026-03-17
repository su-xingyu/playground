import pytest
from datetime import datetime, timedelta

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar
from paper_trading.engine import BacktestEngine
from paper_trading.orders import Fill, OrderType, Side
from paper_trading.strategy import Strategy


def make_bars(prices: list[float], symbol: str = "AAPL") -> list[Bar]:
    """Generate a list of bars from a list of prices (open=close=price, high=price*1.01, low=price*0.99)."""
    start = datetime(2024, 1, 1)
    bars = []
    for i, p in enumerate(prices):
        bars.append(Bar(
            timestamp=start + timedelta(days=i),
            symbol=symbol,
            open=p,
            high=p * 1.01,
            low=p * 0.99,
            close=p,
            volume=1_000_000,
        ))
    return bars


class BuyAndHoldStrategy(Strategy):
    """Buys 100 shares on bar 0, holds forever."""

    def __init__(self, symbol: str, qty: int):
        super().__init__()
        self.symbol = symbol
        self.qty = qty
        self.bar_count = 0
        self.fills_received: list[Fill] = []

    def on_bar(self, bar: Bar) -> None:
        if self.bar_count == 0:
            self.buy(self.symbol, self.qty)
        self.bar_count += 1

    def on_fill(self, fill: Fill) -> None:
        self.fills_received.append(fill)


class DoNothingStrategy(Strategy):
    def on_bar(self, bar: Bar) -> None:
        pass


class TestBacktestEngine:
    def _run(self, strategy, bars, initial_cash=100_000.0, **broker_kwargs):
        broker = PaperBroker(initial_cash, **broker_kwargs)
        engine = BacktestEngine(strategy, iter(bars), broker)
        return engine.run()

    def test_equity_curve_has_one_row_per_bar(self):
        bars = make_bars([100, 110, 120, 130])
        result = self._run(DoNothingStrategy(), bars)
        assert len(result.equity_curve) == 4

    def test_equity_curve_columns(self):
        bars = make_bars([100])
        result = self._run(DoNothingStrategy(), bars)
        cols = set(result.equity_curve.columns)
        assert {"timestamp", "equity", "cash", "unrealized_pnl", "realized_pnl", "net_pnl"}.issubset(cols)

    def test_do_nothing_equity_stays_flat(self):
        bars = make_bars([100, 110, 120])
        result = self._run(DoNothingStrategy(), bars, initial_cash=50_000.0)
        assert (result.equity_curve["equity"] == 50_000.0).all()

    def test_buy_and_hold_equity_grows_with_price(self):
        # Order submitted on bar 0's on_bar; fills at bar 1's open (125).
        # cash after fill = 100000 - 100*125 = 87500
        # bar 2 close = 150; equity = 87500 + 100*150 = 102500
        bars = make_bars([100, 125, 150])
        strategy = BuyAndHoldStrategy("AAPL", 100)
        result = self._run(strategy, bars)
        final_equity = result.equity_curve["equity"].iloc[-1]
        assert final_equity == pytest.approx(102_500.0)

    def test_fills_dataframe(self):
        bars = make_bars([100, 110])
        strategy = BuyAndHoldStrategy("AAPL", 100)
        result = self._run(strategy, bars)
        assert len(result.fills) == 1
        assert result.fills.iloc[0]["qty"] == 100

    def test_orders_dataframe(self):
        bars = make_bars([100, 110])
        strategy = BuyAndHoldStrategy("AAPL", 100)
        result = self._run(strategy, bars)
        assert len(result.orders) == 1

    def test_stats_keys_present(self):
        bars = make_bars([100, 110])
        result = self._run(DoNothingStrategy(), bars)
        required = {"total_return_pct", "max_drawdown_pct", "sharpe_ratio", "num_trades", "win_rate_pct"}
        assert required.issubset(result.stats.keys())

    def test_stats_zero_return_for_do_nothing(self):
        bars = make_bars([100, 110, 120])
        result = self._run(DoNothingStrategy(), bars)
        assert result.stats["total_return_pct"] == pytest.approx(0.0)

    def test_positive_return_stats(self):
        bars = make_bars([100, 100, 150])  # buy on bar0, price goes to 150
        strategy = BuyAndHoldStrategy("AAPL", 100)
        result = self._run(strategy, bars, initial_cash=100_000.0)
        assert result.stats["total_return_pct"] > 0

    def test_on_start_and_on_stop_called(self):
        class TrackedStrategy(Strategy):
            def __init__(self):
                super().__init__()
                self.started = False
                self.stopped = False

            def on_start(self):
                self.started = True

            def on_bar(self, bar):
                pass

            def on_stop(self):
                self.stopped = True

        strategy = TrackedStrategy()
        self._run(strategy, make_bars([100]))
        assert strategy.started
        assert strategy.stopped

    def test_on_fill_called_for_each_fill(self):
        bars = make_bars([100, 110, 120])
        strategy = BuyAndHoldStrategy("AAPL", 100)
        self._run(strategy, bars)
        assert len(strategy.fills_received) == 1

    def test_empty_feed_produces_empty_result(self):
        result = self._run(DoNothingStrategy(), [], initial_cash=10_000.0)
        assert result.equity_curve.empty
        assert result.stats == {}
