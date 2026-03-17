from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .broker import PaperBroker
from .data import Bar
from .orders import Fill, Order
from .strategy import Strategy


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame   # timestamp, equity, cash, unrealized_pnl, realized_pnl, net_pnl
    fills: pd.DataFrame          # fill_id, order_id, symbol, side, qty, fill_price, commission, timestamp
    orders: pd.DataFrame         # order_id, symbol, side, order_type, qty, status, submitted_at
    stats: dict


class BacktestEngine:
    """Drives a strategy through a data feed bar by bar."""

    def __init__(self, strategy: Strategy, feed, broker: PaperBroker):
        self._strategy = strategy
        self._feed = feed
        self._broker = broker
        strategy._broker = broker

    def run(self) -> BacktestResult:
        strategy = self._strategy
        broker = self._broker

        snapshots: list[dict] = []
        all_fills: list[Fill] = []

        strategy.on_start()

        last_prices: dict[str, float] = {}

        for bar in self._feed:
            last_prices[bar.symbol] = bar.close

            # 1. Match pending orders against this bar
            fills = broker._process_bar(bar)

            # 2. Notify strategy of fills
            for fill in fills:
                all_fills.append(fill)
                strategy.on_fill(fill)

            # 3. Let strategy act on the bar
            strategy.current_bar = bar
            strategy.on_bar(bar)

            # 4. Record equity snapshot
            snap = broker.get_portfolio().snapshot(bar.timestamp, last_prices)
            snapshots.append(snap)

        strategy.on_stop()

        return self._build_result(snapshots, all_fills, broker)

    def _build_result(
        self,
        snapshots: list[dict],
        fills: list[Fill],
        broker: PaperBroker,
    ) -> BacktestResult:
        equity_curve = pd.DataFrame(snapshots)

        fills_df = pd.DataFrame([
            {
                "fill_id": f.fill_id,
                "order_id": f.order_id,
                "symbol": f.symbol,
                "side": f.side.value,
                "qty": f.qty,
                "fill_price": f.fill_price,
                "commission": f.commission,
                "timestamp": f.timestamp,
            }
            for f in fills
        ]) if fills else pd.DataFrame(columns=["fill_id", "order_id", "symbol", "side", "qty", "fill_price", "commission", "timestamp"])

        all_orders = list(broker._all_orders.values())
        orders_df = pd.DataFrame([
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side.value,
                "order_type": o.order_type.value,
                "qty": o.qty,
                "status": o.status.value,
                "submitted_at": o.submitted_at,
            }
            for o in all_orders
        ]) if all_orders else pd.DataFrame(columns=["order_id", "symbol", "side", "order_type", "qty", "status", "submitted_at"])

        stats = self._compute_stats(equity_curve, fills, broker)

        return BacktestResult(
            equity_curve=equity_curve,
            fills=fills_df,
            orders=orders_df,
            stats=stats,
        )

    def _compute_stats(
        self,
        equity_curve: pd.DataFrame,
        fills: list[Fill],
        broker: PaperBroker,
    ) -> dict:
        if equity_curve.empty:
            return {}

        portfolio = broker.get_portfolio()
        initial_cash = portfolio.initial_cash
        final_equity = equity_curve["equity"].iloc[-1]

        total_return_pct = (final_equity / initial_cash - 1) * 100

        # Annualized return (CAGR)
        n_days = len(equity_curve)
        years = n_days / 252
        if years > 0 and final_equity > 0:
            annualized_return_pct = ((final_equity / initial_cash) ** (1 / years) - 1) * 100
        else:
            annualized_return_pct = 0.0

        # Max drawdown
        eq = equity_curve["equity"]
        rolling_max = eq.cummax()
        drawdown = (eq - rolling_max) / rolling_max * 100
        max_drawdown_pct = drawdown.min()

        # Sharpe ratio (daily returns, annualized, risk-free = 0)
        daily_returns = eq.pct_change().dropna()
        if daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * math.sqrt(252)
        else:
            sharpe = 0.0

        # Trade-level stats — pair fills into round trips
        trade_pnls = self._compute_trade_pnls(fills)
        num_trades = len(trade_pnls)
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p <= 0]
        win_rate = len(wins) / num_trades * 100 if num_trades > 0 else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return {
            "initial_cash": initial_cash,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "sharpe_ratio": sharpe,
            "num_trades": num_trades,
            "win_rate_pct": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "total_commission": sum(f.commission for f in fills),
        }

    def _compute_trade_pnls(self, fills: list[Fill]) -> list[float]:
        """Compute realized P&L per round trip using FIFO matching."""
        from collections import deque
        pnls: list[float] = []
        long_lots: dict[str, deque] = {}

        for fill in sorted(fills, key=lambda f: f.timestamp):
            sym = fill.symbol
            if sym not in long_lots:
                long_lots[sym] = deque()

            if fill.side.value == "buy":
                long_lots[sym].append([fill.qty, fill.fill_price])
            else:
                remaining = fill.qty
                trade_pnl = 0.0
                while remaining > 0 and long_lots[sym]:
                    lot = long_lots[sym][0]
                    matched = min(lot[0], remaining)
                    trade_pnl += matched * (fill.fill_price - lot[1])
                    lot[0] -= matched
                    remaining -= matched
                    if lot[0] == 0:
                        long_lots[sym].popleft()
                trade_pnl -= fill.commission
                pnls.append(trade_pnl)

        return pnls
