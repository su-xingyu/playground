from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator


@dataclass
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class CsvDataFeed:
    """Reads OHLCV bars from a CSV file.

    Expected columns: timestamp, open, high, low, close, volume
    The timestamp column is parsed with the given format.
    """

    def __init__(self, symbol: str, path: str, timestamp_fmt: str = "%Y-%m-%d"):
        self.symbol = symbol
        self.path = path
        self.timestamp_fmt = timestamp_fmt

    def __iter__(self) -> Iterator[Bar]:
        with open(self.path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield Bar(
                    timestamp=datetime.strptime(row["timestamp"], self.timestamp_fmt),
                    symbol=self.symbol,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )


class MultiSymbolFeed:
    """Merges multiple feeds into a single chronological stream."""

    def __init__(self, feeds: list[CsvDataFeed]):
        self.feeds = feeds

    def __iter__(self) -> Iterator[Bar]:
        import heapq

        # Each entry: (timestamp, symbol, bar) — symbol breaks timestamp ties deterministically
        iters = [iter(feed) for feed in self.feeds]
        heap: list[tuple[datetime, str, Bar]] = []

        for it in iters:
            bar = next(it, None)
            if bar is not None:
                heapq.heappush(heap, (bar.timestamp, bar.symbol, bar))

        iter_map: dict[str, Iterator[Bar]] = {
            feed.symbol: it for feed, it in zip(self.feeds, iters)
        }

        while heap:
            ts, symbol, bar = heapq.heappop(heap)
            yield bar
            nxt = next(iter_map[symbol], None)
            if nxt is not None:
                heapq.heappush(heap, (nxt.timestamp, nxt.symbol, nxt))
