"""US/HK-stock data adapter using yfinance."""

from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf

from adapters.market_data import MarketDataAdapter, Quote, OHLCBar


class YahooAdapter(MarketDataAdapter):
    def __init__(self):
        self._yf = yf

    def get_quote(self, ticker: str) -> Quote:
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
        results = []
        for ticker in tickers:
            results.append(self.get_quote(ticker))
        return results

    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        df = self._yf.download(ticker, start=start_date, end=end_date, progress=False)
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
        try:
            t = self._yf.Ticker("AAPL")
            return "regularMarketPrice" in t.info
        except Exception:
            return False
