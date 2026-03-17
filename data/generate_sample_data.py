"""Generate sample CSV data files used by demos.

All tickers are written with identical timestamps so feeds are aligned.
Single-ticker demos just pick one file; multi-ticker demos use several.
"""

import csv
import os
import random
from datetime import datetime, timedelta


def trading_dates(start_date: datetime, n: int) -> list[str]:
    """Generate n consecutive calendar dates (no weekend filtering for simplicity)."""
    return [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def generate_bars(dates: list[str], start_price: float, drift: float,
                  vol: float, seed: int) -> list[dict]:
    random.seed(seed)
    bars = []
    price = start_price
    for ts in dates:
        pct = random.gauss(drift, vol)
        close = round(price * (1 + pct), 2)
        open_ = round(price * (1 + random.gauss(0, 0.003)), 2)
        high  = round(max(open_, close) * (1 + abs(random.gauss(0, 0.004))), 2)
        low   = round(min(open_, close) * (1 - abs(random.gauss(0, 0.004))), 2)
        bars.append({
            "timestamp": ts,
            "open": open_, "high": high, "low": low, "close": close,
            "volume": random.randint(500_000, 5_000_000),
        })
        price = close
    return bars


def generate_regime_bars(dates: list[str], seed: int) -> list[dict]:
    """Bars across 3 price regimes: uptrend → downtrend → uptrend."""
    regimes = [
        (200, +0.0008, 0.012),
        (150, -0.0010, 0.012),
        (200, +0.0009, 0.012),
    ]
    assert len(dates) >= sum(n for n, *_ in regimes)
    random.seed(seed)
    bars = []
    price = 100.0
    idx = 0
    for n, drift, vol in regimes:
        for _ in range(n):
            pct = random.gauss(drift, vol)
            close = round(price * (1 + pct), 2)
            open_ = round(price * (1 + random.gauss(0, 0.003)), 2)
            high  = round(max(open_, close) * (1 + abs(random.gauss(0, 0.004))), 2)
            low   = round(min(open_, close) * (1 - abs(random.gauss(0, 0.004))), 2)
            bars.append({
                "timestamp": dates[idx],
                "open": open_, "high": high, "low": low, "close": close,
                "volume": random.randint(500_000, 5_000_000),
            })
            price = close
            idx += 1
    return bars


def write_csv(path: str, bars: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(bars)
    print(f"Wrote {len(bars)} rows → {path}")


if __name__ == "__main__":
    out = os.path.dirname(os.path.abspath(__file__))

    # All tickers share the same 550 timestamps (2021-01-01 onwards)
    dates = trading_dates(datetime(2021, 1, 1), 550)

    # 50% generate_bars, 50% generate_regime_bars
    trending_tickers = [
        ("aapl", 150.0, +0.0006, 0.014, 101),
        ("msft", 300.0, +0.0004, 0.013, 202),
    ]
    for name, start_price, drift, vol, seed in trending_tickers:
        write_csv(
            os.path.join(out, f"{name}_daily.csv"),
            generate_bars(dates, start_price=start_price, drift=drift, vol=vol, seed=seed),
        )

    regime_tickers = [
        ("googl", 7),
        ("amzn",  13),
    ]
    for name, seed in regime_tickers:
        write_csv(
            os.path.join(out, f"{name}_daily.csv"),
            generate_regime_bars(dates, seed=seed),
        )
