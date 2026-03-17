"""
Demo: Moving Average Crossover
-------------------------------
Go long when SMA(20) crosses above SMA(50).
Exit when SMA(20) crosses below SMA(50).
Data: data/synth_daily.csv  (uptrend → downtrend → uptrend regime)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import deque

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar, CsvDataFeed
from paper_trading.engine import BacktestEngine
from paper_trading.orders import Fill
from paper_trading.strategy import Strategy

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_PATH = os.path.join(DATA_DIR, "googl_daily.csv")


class SMACrossoverStrategy(Strategy):
    def __init__(self, symbol: str, qty: int, fast: int = 20, slow: int = 50):
        super().__init__()
        self.symbol = symbol
        self.qty = qty
        self._fast_window: deque[float] = deque(maxlen=fast)
        self._slow_window: deque[float] = deque(maxlen=slow)
        self._prev_signal: int = 0

    def on_bar(self, bar: Bar) -> None:
        self._fast_window.append(bar.close)
        self._slow_window.append(bar.close)

        if len(self._slow_window) < self._slow_window.maxlen:
            return

        fast_sma = sum(self._fast_window) / len(self._fast_window)
        slow_sma = sum(self._slow_window) / len(self._slow_window)
        signal = 1 if fast_sma > slow_sma else -1

        if signal != self._prev_signal:
            pos_qty = self.position_qty(self.symbol)
            if signal == 1 and pos_qty == 0:
                self.buy(self.symbol, self.qty)
            elif signal == -1 and pos_qty > 0:
                self.sell(self.symbol, pos_qty)
            self._prev_signal = signal

    def on_fill(self, fill: Fill) -> None:
        action = "BUY " if fill.side.value == "buy" else "SELL"
        print(f"  {fill.timestamp.date()}  {action} {fill.qty} {fill.symbol} @ ${fill.fill_price:.2f}")


def main():
    SYMBOL = "GOOGL"
    QTY = 100
    INITIAL_CASH = 100_000.0

    print("=== SMA(20)/SMA(50) Crossover Demo ===\n")
    print("Trades:")

    feed = CsvDataFeed(SYMBOL, DATA_PATH)
    strategy = SMACrossoverStrategy(SYMBOL, QTY)
    broker = PaperBroker(INITIAL_CASH)
    engine = BacktestEngine(strategy, feed, broker)
    result = engine.run()

    s = result.stats
    print(f"\n{'='*45}")
    print(f"  Bars traded:        {len(result.equity_curve):>12}")
    print(f"  Initial Cash:       ${s['initial_cash']:>12,.2f}")
    print(f"  Final Equity:       ${s['final_equity']:>12,.2f}")
    print(f"  Net P&L:            ${s['final_equity'] - s['initial_cash']:>+12,.2f}")
    print(f"  Total Return:       {s['total_return_pct']:>+11.2f}%")
    print(f"  Annualized Return:  {s['annualized_return_pct']:>+11.2f}%")
    print(f"  Max Drawdown:       {s['max_drawdown_pct']:>11.2f}%")
    print(f"  Sharpe Ratio:       {s['sharpe_ratio']:>12.3f}")
    print(f"  Num Trades (fills): {s['num_trades']:>12}")
    print(f"  Win Rate:           {s['win_rate_pct']:>11.1f}%")
    print(f"  Avg Win:            ${s['avg_win']:>+12,.2f}")
    print(f"  Avg Loss:           ${s['avg_loss']:>+12,.2f}")
    print(f"  Profit Factor:      {s['profit_factor']:>12.2f}")
    print(f"{'='*45}")


if __name__ == "__main__":
    main()
