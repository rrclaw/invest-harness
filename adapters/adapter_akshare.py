"""A-stock market data adapter using akshare (fallback for tushare)."""

from __future__ import annotations

from datetime import datetime

import akshare as ak

from adapters.market_data import MarketDataAdapter, Quote, OHLCBar


def _strip_suffix(ticker: str) -> str:
    """Convert 'XXXXXX.SZ' / 'XXXXXX.SH' to bare code 'XXXXXX' for akshare."""
    return ticker.split(".")[0]


class AkshareAdapter(MarketDataAdapter):
    """MarketDataAdapter backed by akshare -- no API token required."""

    def get_quote(self, ticker: str) -> Quote:
        code = _strip_suffix(ticker)
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code].iloc[0]
        return Quote(
            ticker=ticker,
            price=float(row["最新价"]),
            change_pct=float(row["涨跌幅"]),
            volume=int(row["成交量"]),
            timestamp=datetime.now(),
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        codes = {_strip_suffix(t): t for t in tickers}
        df = ak.stock_zh_a_spot_em()
        results = []
        for code, original_ticker in codes.items():
            match = df[df["代码"] == code]
            if match.empty:
                continue
            row = match.iloc[0]
            results.append(
                Quote(
                    ticker=original_ticker,
                    price=float(row["最新价"]),
                    change_pct=float(row["涨跌幅"]),
                    volume=int(row["成交量"]),
                    timestamp=datetime.now(),
                )
            )
        return results

    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        code = _strip_suffix(ticker)
        # akshare uses YYYYMMDD format for dates
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="",
        )
        results = []
        for _, row in df.iterrows():
            results.append(
                OHLCBar(
                    ticker=ticker,
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=int(row["成交量"]),
                    date=str(row["日期"])[:10],
                )
            )
        return results

    def health_check(self) -> bool:
        try:
            df = ak.stock_zh_a_spot_em()
            return not df.empty
        except Exception:
            return False
