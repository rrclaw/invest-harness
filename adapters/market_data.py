"""Unified market data adapter interface.

All adapters implement this ABC. Adapters are pure data fetchers --
no trading logic, no subjective judgment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Quote:
    """Single ticker quote snapshot."""

    ticker: str
    price: float
    change_pct: float
    volume: int
    timestamp: datetime
    extra: dict | None = None  # adapter-specific fields


@dataclass
class OHLCBar:
    """OHLC bar for a single period."""

    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    date: str  # YYYY-MM-DD
    extra: dict | None = None


class MarketDataAdapter(ABC):
    """Abstract base for all market data adapters."""

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Fetch latest quote for a single ticker."""
        ...

    @abstractmethod
    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch latest quotes for multiple tickers."""
        ...

    @abstractmethod
    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        """Fetch daily OHLC bars for a date range."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if adapter can reach its data source."""
        ...
