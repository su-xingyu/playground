# Paper Trading Framework — Design Document

## Overview

A lightweight, single-threaded Python paper trading framework for backtesting equity strategies against historical OHLCV bar data. No real capital is used; the framework simulates order execution and tracks positions and P&L.

**Scope constraints:**
- Bar-level granularity only (no tick/quote data)
- Equities only
- Single-threaded backtest execution
- Minimal dependencies: stdlib + `pandas` + `numpy`
- FIFO cost basis for P&L calculation

---

## Dependencies

```
python >= 3.11
pandas
numpy
pytest (dev)
```

---

## Repository Structure

```
paper_trading/
  __init__.py
  instruments.py      # Instrument dataclass
  data.py             # Bar dataclass, CsvDataFeed
  orders.py           # Order, Fill, enums (Side, OrderType, OrderStatus)
  position.py         # Position (FIFO lots), Portfolio
  matching.py         # MatchingEngine, slippage models, commission models
  broker.py           # PaperBroker
  strategy.py         # Strategy base class
  engine.py           # BacktestEngine

tests/
  test_orders.py
  test_position_pnl.py
  test_matching.py
  test_broker.py
  test_engine.py

demos/
  demo_buy_and_hold.py
  demo_moving_average_crossover.py
  demo_pnl_report.py

data/                 # Sample CSV data for demos
DESIGN.md
README.md
pyproject.toml
```

---

## Core Abstractions

### Instrument (`instruments.py`)

```python
@dataclass
class Instrument:
    symbol: str
    tick_size: float = 0.01   # minimum price increment
    lot_size: int = 1          # minimum order quantity
    currency: str = "USD"
```

### Bar (`data.py`)

```python
@dataclass
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
```

**DataFeed** is an iterable that yields `Bar` objects in chronological order. The initial implementation reads from CSV files with columns `[timestamp, open, high, low, close, volume]`.

```python
class CsvDataFeed:
    def __init__(self, symbol: str, path: str): ...
    def __iter__(self) -> Iterator[Bar]: ...
```

For multi-symbol backtests, a `MultiSymbolFeed` merges several `CsvDataFeed` instances, yielding bars sorted by timestamp.

---

### Orders (`orders.py`)

```python
class Side(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"          # stop-market

class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    order_id: str
    symbol: str
    side: Side
    order_type: OrderType
    qty: int
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    submitted_at: datetime | None = None

@dataclass
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: Side
    qty: int
    fill_price: float
    commission: float
    timestamp: datetime
```

**Order lifecycle:**

```
PENDING → OPEN → FILLED
                → PARTIALLY_FILLED → FILLED
         → REJECTED
OPEN    → CANCELLED
```

---

### Position & Portfolio (`position.py`)

#### Position

Tracks a single symbol using a FIFO lot queue.

```python
class Position:
    symbol: str
    lots: deque[tuple[int, float]]   # (qty, cost_price) FIFO
    realized_pnl: float

    @property
    def qty(self) -> int: ...                          # net signed quantity
    @property
    def avg_cost(self) -> float: ...                   # weighted average cost
    def unrealized_pnl(self, current_price: float) -> float: ...
    def market_value(self, current_price: float) -> float: ...
    def apply_fill(self, fill: Fill) -> float: ...     # returns realized pnl from this fill
```

**FIFO P&L rule:** when a sell fill arrives, it is matched against the oldest buy lots first. The realized P&L for each matched lot is `(fill_price - lot_cost) * matched_qty`.

Short selling is supported: if a sell fill exceeds current long quantity, the excess creates a short lot at `fill_price`; covering buys are matched FIFO against short lots.

#### Portfolio

```python
class Portfolio:
    cash: float
    positions: dict[str, Position]
    fills: list[Fill]

    def apply_fill(self, fill: Fill) -> None: ...
    def total_equity(self, current_prices: dict[str, float]) -> float: ...
    def realized_pnl(self) -> float: ...
    def unrealized_pnl(self, current_prices: dict[str, float]) -> float: ...
    def snapshot(self, timestamp: datetime, prices: dict[str, float]) -> dict: ...
```

`snapshot()` returns a dict suitable for appending to an equity curve DataFrame.

---

### Matching Engine (`matching.py`)

The engine holds the open order book and matches orders against each new bar.

```python
class MatchingEngine:
    def __init__(self, slippage: SlippageModel, commission: CommissionModel): ...
    def submit(self, order: Order) -> None: ...
    def cancel(self, order_id: str) -> bool: ...
    def process_bar(self, bar: Bar) -> list[Fill]: ...
```

**Matching rules (per bar):**

| Order type | Fill condition | Fill price |
|---|---|---|
| Market | Always fills on next bar open | `open ± slippage` |
| Limit buy | `bar.low <= limit_price` | `min(open, limit_price)` |
| Limit sell | `bar.high >= limit_price` | `max(open, limit_price)` |
| Stop buy | `bar.high >= stop_price` | `stop_price + slippage` |
| Stop sell | `bar.low <= stop_price` | `stop_price - slippage` |

All orders are assumed to fill in full (no partial fills from bar data).

#### Slippage Models

```python
class SlippageModel(Protocol):
    def calc(self, side: Side, price: float) -> float: ...

class ZeroSlippage:       # fill at exact price
class FixedSlippage:      # fill_price ± fixed ticks
class PercentSlippage:    # fill_price ± pct%
```

#### Commission Models

```python
class CommissionModel(Protocol):
    def calc(self, qty: int, fill_price: float) -> float: ...

class ZeroCommission:
class PerShareCommission:   # rate * qty
class PercentCommission:    # rate * qty * fill_price
class FlatCommission:       # fixed fee per order
```

---

### Paper Broker (`broker.py`)

Thin facade over `MatchingEngine` + `Portfolio`. This is the interface strategies interact with.

```python
class PaperBroker:
    def __init__(self, initial_cash: float,
                 slippage: SlippageModel | None = None,
                 commission: CommissionModel | None = None): ...

    # Order management
    def submit_order(self, order: Order) -> str: ...          # returns order_id
    def cancel_order(self, order_id: str) -> bool: ...
    def get_order(self, order_id: str) -> Order | None: ...
    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...

    # State queries
    def get_position(self, symbol: str) -> Position | None: ...
    def get_portfolio(self) -> Portfolio: ...
    def get_cash(self) -> float: ...

    # Called by engine each bar
    def _process_bar(self, bar: Bar) -> list[Fill]: ...
```

---

### Strategy Base Class (`strategy.py`)

```python
class Strategy(ABC):
    broker: PaperBroker
    current_bar: Bar | None

    def on_start(self) -> None: ...         # called once before backtest
    def on_bar(self, bar: Bar) -> None: ... # called for every bar (implement this)
    def on_fill(self, fill: Fill) -> None: ...  # called when a fill occurs
    def on_stop(self) -> None: ...          # called once after backtest

    # Convenience helpers
    def buy(self, symbol: str, qty: int, order_type=OrderType.MARKET, **kwargs) -> str: ...
    def sell(self, symbol: str, qty: int, order_type=OrderType.MARKET, **kwargs) -> str: ...
```

---

### Backtest Engine (`engine.py`)

```python
class BacktestResult:
    equity_curve: pd.DataFrame       # columns: timestamp, equity, cash, unrealized_pnl, realized_pnl
    fills: pd.DataFrame
    orders: pd.DataFrame
    stats: dict                      # see Reporting section

class BacktestEngine:
    def __init__(self, strategy: Strategy, feed: DataFeed, broker: PaperBroker): ...
    def run(self) -> BacktestResult: ...
```

**Execution loop (per bar):**

1. Deliver bar to `MatchingEngine.process_bar()` — collect fills
2. Apply fills to `Portfolio`; call `strategy.on_fill()` for each
3. Call `strategy.on_bar(bar)` — strategy may submit new orders
4. Record equity snapshot

---

## P&L Computation

| Metric | Formula |
|---|---|
| Unrealized P&L | `Σ (current_price - avg_cost) * qty` for open positions |
| Realized P&L | Sum of P&L from all closed/reduced lots (FIFO) |
| Total equity | `cash + Σ market_value(position)` |
| Net P&L | `total_equity - initial_cash` |
| Return % | `(total_equity / initial_cash - 1) * 100` |

---

## Reporting / Stats

`BacktestResult.stats` includes:

| Stat | Description |
|---|---|
| `total_return_pct` | End equity vs initial cash |
| `annualized_return_pct` | CAGR over backtest period |
| `max_drawdown_pct` | Peak-to-trough equity drop |
| `sharpe_ratio` | Annualized (risk-free = 0) |
| `num_trades` | Total fills |
| `win_rate` | % of trades with positive realized P&L |
| `avg_win` / `avg_loss` | Average winning/losing trade P&L |
| `profit_factor` | Gross profit / gross loss |

---

## Testing Strategy

Each module has a dedicated test file. Tests use only `pytest` + stdlib (no external market data required — all data is synthesized inline).

| Test file | What it covers |
|---|---|
| `test_orders.py` | Order/Fill dataclass construction, status transitions |
| `test_position_pnl.py` | FIFO lot matching, realized/unrealized P&L, short selling |
| `test_matching.py` | Market/limit/stop fill logic, slippage, commission |
| `test_broker.py` | Order submission, cancellation, portfolio state after fills |
| `test_engine.py` | Full backtest loop, equity curve shape, stats computation |

---

## Demos

| Demo | Description |
|---|---|
| `demo_buy_and_hold.py` | Buy 100 shares on day 1, hold to end; print P&L report |
| `demo_moving_average_crossover.py` | SMA(20) / SMA(50) crossover strategy on synthetic data |
| `demo_pnl_report.py` | Print equity curve, drawdown chart (text-based), and stats table |
