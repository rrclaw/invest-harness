"""A-stock data adapter using Tushare API."""

from __future__ import annotations

from datetime import datetime

import tushare as ts

from adapters.market_data import MarketDataAdapter, Quote, OHLCBar


class TushareAdapter(MarketDataAdapter):
    def __init__(self, token: str):
        self._api = ts.pro_api(token)

    def get_quote(self, ticker: str) -> Quote:
        df = self._api.realtime_quote(ts_code=ticker)
        row = df.iloc[0]
        return Quote(
            ticker=row["TS_CODE"],
            price=float(row["PRICE"]),
            change_pct=float(row["CHANGE"]),
            volume=int(row["VOL"]),
            timestamp=datetime.strptime(row["DATETIME"], "%Y-%m-%d %H:%M:%S"),
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        df = self._api.realtime_quote(ts_code=",".join(tickers))
        results = []
        for _, row in df.iterrows():
            results.append(
                Quote(
                    ticker=row["TS_CODE"],
                    price=float(row["PRICE"]),
                    change_pct=float(row["CHANGE"]),
                    volume=int(row["VOL"]),
                    timestamp=datetime.strptime(
                        row["DATETIME"], "%Y-%m-%d %H:%M:%S"
                    ),
                )
            )
        return results

    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        # Tushare uses YYYYMMDD format
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        df = self._api.daily(ts_code=ticker, start_date=start, end_date=end)
        results = []
        for _, row in df.iterrows():
            trade_date = row["trade_date"]
            formatted = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            results.append(
                OHLCBar(
                    ticker=row["ts_code"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["vol"]),
                    date=formatted,
                )
            )
        return results

    def health_check(self) -> bool:
        try:
            self._api.trade_cal(exchange="SSE", start_date="20260101", end_date="20260101")
            return True
        except Exception:
            return False
