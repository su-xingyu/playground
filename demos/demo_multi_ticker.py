"""
Demo: Multi-Ticker Momentum Rotation
--------------------------------------
Universe: AAPL, MSFT, GOOGL, AMZN (aligned daily bars, 2022-01-01 to ~2023-09-18)
Strategy: Every REBALANCE_PERIOD bars, rank all symbols by their LOOKBACK-bar return.
          Hold the top TOP_N performers in equal notional size; exit the rest.

Cash timing: sell and buy orders are both market orders that fill on the next bar's
open. To avoid spending cash that is tied up in pending fills, sells are submitted
one bar before buys: at rebalance bar N we sell exiting positions; at bar N+1 (when
sells have filled) we buy entering positions with the freed cash.

Data: data/multi/{symbol}_daily.csv
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import defaultdict

from paper_trading.broker import PaperBroker
from paper_trading.data import Bar, CsvDataFeed, MultiSymbolFeed
from paper_trading.engine import BacktestEngine, BacktestResult
from paper_trading.strategy import Strategy

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SYMBOLS   = ["AAPL", "MSFT", "GOOGL", "AMZN"]

REBALANCE_PERIOD = 20    # unique timestamps between rebalances
LOOKBACK         = 20    # bars used to compute momentum return
TOP_N            = 2     # number of top symbols to hold
CASH_BUFFER      = 0.95  # use 95% of available cash to avoid overspend at next open


class MomentumRotationStrategy(Strategy):
    def __init__(self, symbols: list[str], top_n: int,
                 rebalance_period: int, lookback: int):
        super().__init__()
        self.symbols         = symbols
        self.top_n           = top_n
        self.rebalance_period = rebalance_period
        self.lookback        = lookback

        self._prices: dict[str, list[float]] = defaultdict(list)
        self._bar_count   = 0
        self._last_ts     = None
        # Symbols we want to buy, deferred to the bar after sells fill
        self._pending_buys: set[str] = set()
        self._buy_bar     = -1   # bar_count at which to execute pending buys

    def on_bar(self, bar: Bar) -> None:
        self._prices[bar.symbol].append(bar.close)

        # Track unique timestamps to count bars
        if bar.timestamp != self._last_ts:
            self._last_ts = bar.timestamp
            self._bar_count += 1

        # Execute deferred buys on the bar after sells were submitted
        # Only act once per timestamp (when first symbol of that timestamp arrives)
        if self._bar_count == self._buy_bar and bar.symbol == self.symbols[0]:
            self._execute_buys()

        # Trigger rebalance
        if self._bar_count % self.rebalance_period == 0 and bar.symbol == self.symbols[-1]:
            self._rebalance()

    def _rebalance(self) -> None:
        if any(len(self._prices[s]) < self.lookback for s in self.symbols):
            return

        # Rank symbols by lookback-bar momentum
        returns = {
            s: (self._prices[s][-1] / self._prices[s][-self.lookback] - 1)
            for s in self.symbols
        }
        ranked = sorted(returns, key=returns.__getitem__, reverse=True)
        target  = set(ranked[:self.top_n])
        current = {s for s in self.symbols if self.position_qty(s) != 0}

        exiting  = current - target
        entering = target - current

        # Sell exiting positions now; buys will be placed next bar after sells fill
        for symbol in exiting:
            qty = self.position_qty(symbol)
            if qty > 0:
                self.sell(symbol, qty)

        if entering:
            self._pending_buys = entering
            self._buy_bar = self._bar_count + 1  # execute on next unique timestamp

    def _execute_buys(self) -> None:
        if not self._pending_buys:
            return

        cash = self.cash() * CASH_BUFFER
        if cash <= 0:
            self._pending_buys.clear()
            return

        per_symbol_cash = cash / len(self._pending_buys)
        for symbol in self._pending_buys:
            price = self._prices[symbol][-1]
            qty   = int(per_symbol_cash / price)
            if qty > 0:
                self.buy(symbol, qty)

        self._pending_buys.clear()

    def on_stop(self) -> None:
        # Close all open positions at end of backtest (orders won't fill — just for accounting)
        for symbol in self.symbols:
            qty = self.position_qty(symbol)
            if qty > 0:
                self.sell(symbol, qty)


def print_report(result: BacktestResult, initial_cash: float) -> None:
    s  = result.stats
    ec = result.equity_curve

    print(f"\n{'='*52}")
    print(f"  Period: {ec['timestamp'].iloc[0].date()} → {ec['timestamp'].iloc[-1].date()}")
    print(f"  Bars (unique timestamps): {ec['timestamp'].nunique()}")
    print(f"{'='*52}")
    print(f"  {'Initial Cash:':<26} ${initial_cash:>12,.2f}")
    print(f"  {'Final Equity:':<26} ${s['final_equity']:>12,.2f}")
    print(f"  {'Net P&L:':<26} ${s['final_equity'] - initial_cash:>+12,.2f}")
    print(f"  {'Total Return:':<26} {s['total_return_pct']:>+11.2f}%")
    print(f"  {'Annualized Return:':<26} {s['annualized_return_pct']:>+11.2f}%")
    print(f"  {'Max Drawdown:':<26} {s['max_drawdown_pct']:>11.2f}%")
    print(f"  {'Sharpe Ratio:':<26} {s['sharpe_ratio']:>12.3f}")
    print(f"  {'Num Round Trips:':<26} {s['num_trades']:>12}")
    print(f"  {'Win Rate:':<26} {s['win_rate_pct']:>11.1f}%")
    print(f"  {'Profit Factor:':<26} {s['profit_factor']:>12.2f}")
    print(f"  {'Total Commission:':<26} ${s['total_commission']:>12,.2f}")
    print(f"{'='*52}")

    fills = result.fills
    if not fills.empty:
        print("\nFills by symbol:")
        summary = (
            fills.groupby(["symbol", "side"])
            .agg(num_fills=("qty", "count"), total_qty=("qty", "sum"), avg_price=("fill_price", "mean"))
        )
        print(summary.to_string())


def main():
    INITIAL_CASH = 100_000.0
    print(f"=== Momentum Rotation: top {TOP_N} of {SYMBOLS} ===")
    print(f"    Rebalance every {REBALANCE_PERIOD} bars | {LOOKBACK}-bar momentum\n")

    feeds = [
        CsvDataFeed(sym, os.path.join(DATA_DIR, f"{sym.lower()}_daily.csv"))
        for sym in SYMBOLS
    ]
    feed     = MultiSymbolFeed(feeds)
    strategy = MomentumRotationStrategy(
        symbols=SYMBOLS, top_n=TOP_N,
        rebalance_period=REBALANCE_PERIOD, lookback=LOOKBACK,
    )
    broker = PaperBroker(INITIAL_CASH)
    engine = BacktestEngine(strategy, feed, broker)
    result = engine.run()

    print_report(result, INITIAL_CASH)


if __name__ == "__main__":
    main()
