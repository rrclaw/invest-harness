"""HK and US stock data adapter using yfinance.

Uses yf.Ticker.info for quotes and yf.Ticker.history() for OHLC bars.
Supports bare US symbols (MSFT) and HK suffixed symbols (0700.HK) directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from adapters.market_data import MarketDataAdapter, OHLCBar, Quote


class YfinanceAdapter(MarketDataAdapter):
    """Market data adapter backed by the yfinance library."""

    def __init__(self):
        self._yf = yf

    def get_quote(self, ticker: str) -> Quote:
        """Fetch latest quote snapshot for a single ticker."""
        t = self._yf.Ticker(ticker)
        info = t.info
        return Quote(
            ticker=ticker,
            price=float(info["regularMarketPrice"]),
            change_pct=float(info.get("regularMarketChangePercent", 0.0)),
            volume=int(info.get("regularMarketVolume", 0)),
            timestamp=datetime.now(timezone.utc),
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch latest quote snapshots for multiple tickers."""
        return [self.get_quote(ticker) for ticker in tickers]

    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        """Fetch daily OHLC bars for *ticker* over [start_date, end_date)."""
        t = self._yf.Ticker(ticker)
        df = t.history(start=start_date, end=end_date)
        results = []
        for idx, row in df.iterrows():
            results.append(
                OHLCBar(
                    ticker=ticker,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    date=idx.strftime("%Y-%m-%d"),
                )
            )
        return results

    def health_check(self) -> bool:
        """Return True if yfinance can reach its data source."""
        try:
            t = self._yf.Ticker("AAPL")
            return "regularMarketPrice" in t.info
        except Exception:
            return False
