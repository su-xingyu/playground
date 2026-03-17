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
pytest-cov (dev)
```

---

## Repository Structure

```
paper_trading/
  __init__.py
  instruments.py      # Instrument dataclass
  data.py             # Bar dataclass, CsvDataFeed, MultiSymbolFeed
  orders.py           # Order, Fill, enums (Side, OrderType, OrderStatus)
  position.py         # Position (FIFO lots), Portfolio
  matching.py         # MatchingEngine, slippage models, commission models
  broker.py           # PaperBroker
  strategy.py         # Strategy base class
  engine.py           # BacktestEngine, BacktestResult

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

data/                         # All tickers share identical timestamps (2021-01-01, 550 bars)
  aapl_daily.csv            # trending (generate_bars)
  msft_daily.csv            # trending (generate_bars)
  googl_daily.csv           # regime-change (generate_regime_bars)
  amzn_daily.csv            # regime-change (generate_regime_bars)
  generate_sample_data.py   # Script to regenerate all CSV files

DESIGN.md
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

**DataFeed** is an iterable that yields `Bar` objects in chronological order. `CsvDataFeed` reads from a CSV file with columns `[timestamp, open, high, low, close, volume]`.

```python
class CsvDataFeed:
    def __init__(self, symbol: str, path: str, timestamp_fmt: str = "%Y-%m-%d"): ...
    def __iter__(self) -> Iterator[Bar]: ...
```

For multi-symbol backtests, `MultiSymbolFeed` merges several `CsvDataFeed` instances, yielding bars sorted by timestamp via a heap merge.

```python
class MultiSymbolFeed:
    def __init__(self, feeds: list[CsvDataFeed]): ...
    def __iter__(self) -> Iterator[Bar]: ...
```

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
    symbol: str
    side: Side
    order_type: OrderType
    qty: int
    limit_price: float | None = None
    stop_price: float | None = None
    order_id: str = field(default_factory=uuid4)   # auto-generated
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    submitted_at: datetime | None = None

    @property
    def remaining_qty(self) -> int: ...
    @property
    def is_active(self) -> bool: ...   # True when OPEN or PARTIALLY_FILLED

@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    fill_price: float
    commission: float
    timestamp: datetime
    fill_id: str = field(default_factory=uuid4)    # auto-generated
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

Tracks a single symbol using a FIFO lot queue. Each lot is a mutable `[qty, cost_price]` list so it can be partially consumed in-place.

```python
class Position:
    symbol: str
    realized_pnl: float

    @property
    def qty(self) -> int: ...                          # net signed quantity (+ long, - short)
    @property
    def avg_cost(self) -> float: ...                   # weighted average cost of net position
    def unrealized_pnl(self, current_price: float) -> float: ...
    def market_value(self, current_price: float) -> float: ...
    def apply_fill(self, fill: Fill) -> float: ...     # returns realized P&L from this fill
    def is_flat(self) -> bool: ...
```

**FIFO P&L rule:** sell fills are matched against the oldest buy lots first. Realized P&L per matched lot = `(fill_price - lot_cost) * matched_qty`. Short selling is supported: excess sell qty opens a short lot; covering buys are matched FIFO against short lots.

#### Portfolio

```python
class Portfolio:
    cash: float
    initial_cash: float
    positions: dict[str, Position]
    fills: list[Fill]

    def apply_fill(self, fill: Fill) -> None: ...
    def total_equity(self, current_prices: dict[str, float]) -> float: ...
    def realized_pnl(self) -> float: ...
    def unrealized_pnl(self, current_prices: dict[str, float]) -> float: ...
    def snapshot(self, timestamp: datetime, prices: dict[str, float]) -> dict: ...
```

`snapshot()` returns a dict with keys `timestamp, equity, cash, unrealized_pnl, realized_pnl, net_pnl`.

---

### Matching Engine (`matching.py`)

The engine holds the open order book and matches orders against each new bar.

```python
class MatchingEngine:
    def __init__(self, slippage: SlippageModel | None, commission: CommissionModel | None): ...
    def submit(self, order: Order) -> None: ...
    def cancel(self, order_id: str) -> bool: ...
    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...
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

All orders fill in full (no partial fills from bar data).

#### Slippage Models

```python
class SlippageModel(Protocol):
    def calc(self, side: Side, price: float) -> float: ...

class ZeroSlippage:       # fill at exact price
class FixedSlippage:      # fill_price ± fixed dollar amount
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

    # Order constructors
    def create_market_order(self, symbol: str, side: Side, qty: int) -> Order: ...
    def create_limit_order(self, symbol: str, side: Side, qty: int, limit_price: float) -> Order: ...
    def create_stop_order(self, symbol: str, side: Side, qty: int, stop_price: float) -> Order: ...

    # Called by BacktestEngine each bar
    def _process_bar(self, bar: Bar) -> list[Fill]: ...
```

---

### Strategy Base Class (`strategy.py`)

```python
class Strategy(ABC):
    broker: PaperBroker
    current_bar: Bar | None

    def on_start(self) -> None: ...              # called once before first bar
    def on_bar(self, bar: Bar) -> None: ...      # called on every bar (implement this)
    def on_fill(self, fill: Fill) -> None: ...   # called when a fill occurs
    def on_stop(self) -> None: ...               # called once after last bar

    # Order helpers
    def buy(self, symbol: str, qty: int, order_type: OrderType = MARKET,
            limit_price: float | None = None, stop_price: float | None = None) -> str: ...
    def sell(self, symbol: str, qty: int, order_type: OrderType = MARKET,
             limit_price: float | None = None, stop_price: float | None = None) -> str: ...

    # State helpers
    def position_qty(self, symbol: str) -> int: ...
    def cash(self) -> float: ...
```

---

### Backtest Engine (`engine.py`)

```python
@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame   # timestamp, equity, cash, unrealized_pnl, realized_pnl, net_pnl
    fills: pd.DataFrame          # fill_id, order_id, symbol, side, qty, fill_price, commission, timestamp
    orders: pd.DataFrame         # order_id, symbol, side, order_type, qty, status, submitted_at
    stats: dict

class BacktestEngine:
    def __init__(self, strategy: Strategy, feed, broker: PaperBroker): ...
    def run(self) -> BacktestResult: ...
```

**Execution loop (per bar):**

1. Deliver bar to `MatchingEngine.process_bar()` — collect fills
2. Apply fills to `Portfolio`; call `strategy.on_fill()` for each
3. Call `strategy.on_bar(bar)` — strategy may submit new orders
4. Record equity snapshot

Orders submitted in step 3 fill at the **next bar's open**, preventing look-ahead bias.

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

`BacktestResult.stats` keys:

| Key | Description |
|---|---|
| `initial_cash` | Starting capital |
| `final_equity` | Ending total equity |
| `total_return_pct` | End equity vs initial cash |
| `annualized_return_pct` | CAGR (252 trading days/year) |
| `max_drawdown_pct` | Peak-to-trough equity drop |
| `sharpe_ratio` | Annualized (risk-free = 0) |
| `num_trades` | Number of sell fills (round trips) |
| `win_rate_pct` | % of round trips with positive realized P&L |
| `avg_win` / `avg_loss` | Average winning/losing round-trip P&L |
| `gross_profit` / `gross_loss` | Sum of all wins / abs sum of all losses |
| `profit_factor` | `gross_profit / gross_loss` |
| `total_commission` | Sum of all commissions paid |

---

## Testing Strategy

Each module has a dedicated test file. Tests use only `pytest` + stdlib with inline synthetic data (no CSV files).

| Test file | What it covers |
|---|---|
| `test_orders.py` | Order/Fill dataclass construction, status transitions, validation |
| `test_position_pnl.py` | FIFO lot matching, realized/unrealized P&L, short selling |
| `test_matching.py` | Market/limit/stop fill logic, slippage models, commission models |
| `test_broker.py` | Order submission, cancellation, portfolio state after fills |
| `test_engine.py` | Full backtest loop, equity curve shape, stats, lifecycle hooks |

---

## Demos

All demos read from CSV files in `data/`. Run `data/generate_sample_data.py` to regenerate the CSV files.

| Demo | Data file | Description |
|---|---|---|
| `demo_buy_and_hold.py` | `aapl_daily.csv` | Buy 100 shares on day 1, hold to end; print P&L report |
| `demo_moving_average_crossover.py` | `googl_daily.csv` | SMA(20)/SMA(50) crossover on a regime-change price series |
| `demo_pnl_report.py` | `googl_daily.csv` | Full stats table + text-based equity curve and drawdown chart |
| `demo_multi_ticker.py` | `aapl/msft/googl/amzn_daily.csv` | Momentum rotation across 4 tickers using `MultiSymbolFeed` |
