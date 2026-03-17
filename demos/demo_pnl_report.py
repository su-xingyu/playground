"""
Demo: P&L Report with Text Charts
-----------------------------------
Runs the SMA crossover strategy and prints:
- Full stats table
- Text-based equity curve
- Text-based drawdown chart
Data: data/googl_daily.csv
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import deque

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar, CsvDataFeed
from paper_trading.engine import BacktestEngine, BacktestResult
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


def text_chart(values: list[float], width: int = 70, height: int = 15, title: str = "") -> str:
    if not values:
        return ""
    mn, mx = min(values), max(values)
    span = mx - mn or 1.0
    rows = []
    if title:
        rows.append(title.center(width))

    step = max(1, len(values) // width)
    sampled = values[::step][:width]

    for row in range(height, -1, -1):
        threshold = mn + span * row / height
        line = ""
        for v in sampled:
            line += "█" if v >= threshold else " "
        label = f"${threshold:>10,.0f} |" if row % 5 == 0 else " " * 12 + "|"
        rows.append(label + line)

    rows.append(" " * 12 + "+" + "-" * len(sampled))
    return "\n".join(rows)


def drawdown_chart(equity: list[float], width: int = 70, height: int = 8, title: str = "") -> str:
    peak = equity[0]
    drawdowns = []
    for v in equity:
        peak = max(peak, v)
        drawdowns.append((v - peak) / peak * 100)

    mn = min(drawdowns)
    rows = []
    if title:
        rows.append(title.center(width))

    step = max(1, len(drawdowns) // width)
    sampled = drawdowns[::step][:width]

    for row in range(height, -1, -1):
        threshold = mn * (1 - row / height)
        line = ""
        for v in sampled:
            line += "▄" if v <= threshold else " "
        label = f"{threshold:>10.1f}% |" if row % 2 == 0 else " " * 12 + "|"
        rows.append(label + line)

    rows.append(" " * 12 + "+" + "-" * len(sampled))
    return "\n".join(rows)


def print_report(result: BacktestResult) -> None:
    s = result.stats
    ec = result.equity_curve
    equity_vals = ec["equity"].tolist()

    print("\n" + "=" * 70)
    print("  BACKTEST REPORT".center(70))
    print("=" * 70)
    print(f"\n  Period: {ec['timestamp'].iloc[0].date()} → {ec['timestamp'].iloc[-1].date()}")
    print(f"  Bars:   {len(ec)}\n")

    print(f"  {'Metric':<28} {'Value':>15}")
    print(f"  {'-'*28} {'-'*15}")
    rows = [
        ("Initial Cash",         f"${s['initial_cash']:>14,.2f}"),
        ("Final Equity",         f"${s['final_equity']:>14,.2f}"),
        ("Net P&L",              f"${s['final_equity']-s['initial_cash']:>+14,.2f}"),
        ("Total Return",         f"{s['total_return_pct']:>+14.2f}%"),
        ("Annualized Return",    f"{s['annualized_return_pct']:>+14.2f}%"),
        ("Max Drawdown",         f"{s['max_drawdown_pct']:>14.2f}%"),
        ("Sharpe Ratio",         f"{s['sharpe_ratio']:>15.3f}"),
        ("Num Trades (fills)",   f"{s['num_trades']:>15}"),
        ("Win Rate",             f"{s['win_rate_pct']:>14.1f}%"),
        ("Avg Win",              f"${s['avg_win']:>+14,.2f}"),
        ("Avg Loss",             f"${s['avg_loss']:>+14,.2f}"),
        ("Profit Factor",        f"{s['profit_factor']:>15.2f}"),
        ("Total Commission",     f"${s['total_commission']:>14,.2f}"),
    ]
    for label, val in rows:
        print(f"  {label:<28} {val:>15}")

    print()
    print(text_chart(equity_vals, title="Equity Curve"))
    print()
    print(drawdown_chart(equity_vals, title="Drawdown (%)"))
    print()


def main():
    feed = CsvDataFeed("GOOGL", DATA_PATH)
    strategy = SMACrossoverStrategy("GOOGL", qty=100)
    broker = PaperBroker(100_000.0)
    engine = BacktestEngine(strategy, feed, broker)
    result = engine.run()
    print_report(result)


if __name__ == "__main__":
    main()
