# How It Works

## Entry Point

The typical entry point for a backtest is:

```python
feed     = CsvDataFeed("AAPL", "data/aapl_daily.csv")
broker   = PaperBroker(initial_cash=100_000)
strategy = MyStrategy()
engine   = BacktestEngine(strategy, feed, broker)
result   = engine.run()
```

`BacktestEngine.run()` drives everything. You only need to implement `on_bar()` in your strategy.

---

## Component Map

```
┌─────────────┐     bars      ┌──────────────────────────────────────────┐
│  CsvDataFeed│ ────────────► │              BacktestEngine               │
└─────────────┘               │                                          │
                               │  for each bar:                           │
┌─────────────┐                │    1. MatchingEngine.process_bar()       │
│ PaperBroker │ ◄────────────► │    2. strategy.on_fill()                 │
│             │                │    3. strategy.on_bar()                  │
│  ┌────────┐ │                │    4. record equity snapshot             │
│  │Matching│ │                └──────────────────────────────────────────┘
│  │Engine  │ │
│  └────────┘ │                ┌──────────────────────────────────────────┐
│  ┌────────┐ │                │             Your Strategy                │
│  │Port-   │ │ ◄────────────► │                                          │
│  │folio   │ │  submit_order  │  def on_bar(self, bar):                  │
│  └────────┘ │  get_position  │      self.buy("AAPL", qty=100)           │
└─────────────┘  get_cash      └──────────────────────────────────────────┘
```

---

## What Happens Each Bar

```
                        ┌──────────────────┐
                        │   New Bar arrives │
                        │  (open/high/low/  │
                        │   close/volume)   │
                        └────────┬─────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  1. Match open orders   │
                    │                         │
                    │  Market → fill @ open   │
                    │  Limit  → fill if price │
                    │           touched       │
                    │  Stop   → fill if price │
                    │           triggered     │
                    └────────────┬────────────┘
                                 │ fills
                    ┌────────────▼────────────┐
                    │  2. Apply fills          │
                    │                         │
                    │  • update Position      │
                    │    (FIFO lots)          │
                    │  • update cash          │
                    │  • call on_fill()       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  3. Call on_bar()        │
                    │                         │
                    │  Strategy sees bar,     │
                    │  submits new orders     │
                    │  (queued for NEXT bar)  │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  4. Record snapshot     │
                    │                         │
                    │  equity, cash,          │
                    │  unrealized P&L,        │
                    │  realized P&L           │
                    └─────────────────────────┘
```

---

## Why Orders Fill on the Next Bar

When your strategy calls `self.buy(...)` inside `on_bar(bar_N)`, the order sits in the book and fills at the **open of bar N+1**:

```
Bar N    │ strategy sees close=$150, submits BUY
         │         ↓ order queued
Bar N+1  │ order fills @ open=$151   ← first thing that happens
         │ strategy sees new bar
```

This prevents look-ahead bias: your strategy never trades on prices it couldn't have known.

---

## Order Lifecycle

```
submit_order()
      │
      ▼
   PENDING ──► OPEN ──────────────► FILLED
                 │                    ▲
                 │    (partial fill)  │
                 └──► PARTIALLY_FILLED┘
                 │
                 ├──► CANCELLED  (cancel_order called)
                 └──► REJECTED   (invalid order)
```

---

## P&L Accounting

Positions use **FIFO lot tracking**. Each buy creates a lot; sells consume the oldest lot first.

```
Buys:                     Lots queue (FIFO):
  BUY  50 @ $100   ──►   [ (50, $100) ]
  BUY  50 @ $120   ──►   [ (50, $100) | (50, $120) ]

Sell:
  SELL 70 @ $130   ──►   consume (50, $100) fully  → P&L = 50 × ($130−$100) = +$1,500
                          consume (20, $120) partial → P&L = 20 × ($130−$120) = +$200
                          remaining lot: [ (30, $120) ]

  Realized P&L this sell: $1,700
  Unrealized P&L:         30 × ($130−$120) = $300  (at current price)
```

---

## BacktestResult

After `engine.run()` you get:

```
BacktestResult
  ├── equity_curve   DataFrame   one row per bar: equity, cash, P&L
  ├── fills          DataFrame   every execution: price, qty, commission
  ├── orders         DataFrame   every order and its final status
  └── stats          dict
        ├── total_return_pct
        ├── annualized_return_pct   (CAGR, 252 trading days/year)
        ├── max_drawdown_pct
        ├── sharpe_ratio            (annualized, risk-free = 0)
        ├── num_trades              (closed round trips)
        ├── win_rate_pct
        ├── avg_win / avg_loss
        ├── profit_factor
        └── total_commission
```

---

## Multi-Ticker Backtest

For multiple symbols, swap `CsvDataFeed` for `MultiSymbolFeed`. It merges feeds
chronologically and delivers one bar at a time — the engine and strategy are unchanged.

```
CsvDataFeed("AAPL") ──┐
CsvDataFeed("MSFT") ──┼──► MultiSymbolFeed ──► BacktestEngine
CsvDataFeed("GOOGL")──┘        (heap merge,
CsvDataFeed("AMZN") ──         sorted by timestamp)
```

In `on_bar`, route logic by `bar.symbol`:

```python
def on_bar(self, bar):
    self._prices[bar.symbol].append(bar.close)
    # make decisions using self._prices for any symbol
```
