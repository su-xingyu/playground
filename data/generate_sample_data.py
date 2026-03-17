"""Generate sample CSV data files used by demos."""

import csv
import random
from datetime import datetime, timedelta


def write_csv(path: str, symbol: str, bars: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(bars)
    print(f"Wrote {len(bars)} rows → {path}")


def generate_bars(n: int, start_price: float, drift: float, vol: float,
                  start_date: datetime, seed: int) -> list[dict]:
    random.seed(seed)
    bars = []
    price = start_price
    for i in range(n):
        pct = random.gauss(drift, vol)
        close = round(price * (1 + pct), 2)
        open_ = round(price * (1 + random.gauss(0, 0.003)), 2)
        high = round(max(open_, close) * (1 + abs(random.gauss(0, 0.004))), 2)
        low = round(min(open_, close) * (1 - abs(random.gauss(0, 0.004))), 2)
        bars.append({
            "timestamp": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": open_, "high": high, "low": low, "close": close,
            "volume": random.randint(500_000, 5_000_000),
        })
        price = close
    return bars


def generate_regime_bars(start_date: datetime, seed: int) -> list[dict]:
    random.seed(seed)
    bars = []
    price = 100.0
    regimes = [
        (200, +0.0008, 0.012),
        (150, -0.0010, 0.012),
        (200, +0.0009, 0.012),
    ]
    day = 0
    for n, drift, vol in regimes:
        for _ in range(n):
            pct = random.gauss(drift, vol)
            close = round(price * (1 + pct), 2)
            open_ = round(price * (1 + random.gauss(0, 0.003)), 2)
            high = round(max(open_, close) * (1 + abs(random.gauss(0, 0.004))), 2)
            low = round(min(open_, close) * (1 - abs(random.gauss(0, 0.004))), 2)
            bars.append({
                "timestamp": (start_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "open": open_, "high": high, "low": low, "close": close,
                "volume": random.randint(500_000, 5_000_000),
            })
            price = close
            day += 1
    return bars


if __name__ == "__main__":
    import os
    out = os.path.dirname(__file__)

    write_csv(
        os.path.join(out, "aapl_daily.csv"),
        "AAPL",
        generate_bars(252, start_price=150.0, drift=0.0005, vol=0.015,
                      start_date=datetime(2023, 1, 1), seed=42),
    )

    write_csv(
        os.path.join(out, "synth_daily.csv"),
        "SYNTH",
        generate_regime_bars(start_date=datetime(2021, 1, 1), seed=7),
    )
