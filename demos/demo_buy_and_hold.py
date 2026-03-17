"""
Demo: Buy and Hold
------------------
Buy 100 shares on the first bar, hold to the end. Print a P&L report.
Data: data/aapl_daily.csv
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar, CsvDataFeed
from paper_trading.engine import BacktestEngine
from paper_trading.orders import Fill
from paper_trading.strategy import Strategy

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
DATA_PATH = os.path.join(DATA_DIR, "aapl_daily.csv")


class BuyAndHoldStrategy(Strategy):
    def __init__(self, symbol: str, qty: int):
        super().__init__()
        self.symbol = symbol
        self.qty = qty
        self._bought = False

    def on_bar(self, bar: Bar) -> None:
        if not self._bought:
            self.buy(self.symbol, self.qty)
            self._bought = True

    def on_fill(self, fill: Fill) -> None:
        print(f"  Fill: {fill.side.value.upper()} {fill.qty} {fill.symbol} @ ${fill.fill_price:.2f}")


def main():
    SYMBOL = "AAPL"
    QTY = 100
    INITIAL_CASH = 100_000.0

    print(f"=== Buy and Hold Demo: {SYMBOL} x{QTY} shares ===\n")

    feed = CsvDataFeed(SYMBOL, DATA_PATH)
    strategy = BuyAndHoldStrategy(SYMBOL, QTY)
    broker = PaperBroker(INITIAL_CASH)
    engine = BacktestEngine(strategy, feed, broker)
    result = engine.run()

    s = result.stats
    ec = result.equity_curve

    print(f"\n{'='*45}")
    print(f"  Initial Cash:       ${s['initial_cash']:>12,.2f}")
    print(f"  Final Equity:       ${s['final_equity']:>12,.2f}")
    print(f"  Net P&L:            ${s['final_equity'] - s['initial_cash']:>+12,.2f}")
    print(f"  Total Return:       {s['total_return_pct']:>+11.2f}%")
    print(f"  Annualized Return:  {s['annualized_return_pct']:>+11.2f}%")
    print(f"  Max Drawdown:       {s['max_drawdown_pct']:>11.2f}%")
    print(f"  Sharpe Ratio:       {s['sharpe_ratio']:>12.3f}")
    print(f"  Total Commission:   ${s['total_commission']:>12,.2f}")
    print(f"  Num Trades:         {s['num_trades']:>12}")
    print(f"{'='*45}")

    print(f"\nFirst bar: {ec.iloc[0]['timestamp'].date()}  equity=${ec.iloc[0]['equity']:,.2f}")
    print(f"Last bar:  {ec.iloc[-1]['timestamp'].date()}  equity=${ec.iloc[-1]['equity']:,.2f}")


if __name__ == "__main__":
    main()
