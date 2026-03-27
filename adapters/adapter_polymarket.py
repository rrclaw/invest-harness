"""Polymarket data adapter using Gamma API.

Polymarket has no open/close semantics. Uses odds-slope monitoring
instead of time-based snapshots.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from adapters.market_data import MarketDataAdapter, Quote, OHLCBar


class PolymarketAdapter(MarketDataAdapter):
    def __init__(self, api_url: str = "https://gamma-api.polymarket.com"):
        self._base_url = api_url.rstrip("/")

    def get_quote(self, ticker: str) -> Quote:
        """Fetch latest odds for a market by slug."""
        resp = requests.get(f"{self._base_url}/markets/{ticker}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        prices = data["outcomePrices"]
        yes_price = float(prices[0])
        no_price = float(prices[1])
        return Quote(
            ticker=data.get("slug", ticker),
            price=yes_price,
            change_pct=0.0,  # No native change % from API
            volume=int(data.get("volume", 0)),
            timestamp=datetime.now(timezone.utc),
            extra={
                "question": data.get("question"),
                "no_price": no_price,
                "market_id": data.get("id"),
            },
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        """Fetch quotes for multiple market slugs."""
        slugs_param = ",".join(tickers)
        resp = requests.get(
            f"{self._base_url}/markets",
            params={"slug": slugs_param},
            timeout=10,
        )
        resp.raise_for_status()
        markets = resp.json()
        results = []
        for data in markets:
            prices = data["outcomePrices"]
            results.append(
                Quote(
                    ticker=data.get("slug", ""),
                    price=float(prices[0]),
                    change_pct=0.0,
                    volume=int(data.get("volume", 0)),
                    timestamp=datetime.now(timezone.utc),
                    extra={
                        "question": data.get("question"),
                        "no_price": float(prices[1]),
                        "market_id": data.get("id"),
                    },
                )
            )
        return results

    def get_daily_bars(
        self, ticker: str, start_date: str, end_date: str
    ) -> list[OHLCBar]:
        """Polymarket has no OHLC bars. Returns empty list."""
        return []

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                f"{self._base_url}/markets", params={"limit": 1}, timeout=10
            )
            return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def calculate_odds_slope(old_price: float, new_price: float) -> float:
        """Calculate absolute percentage point change between two odds snapshots.

        Returns absolute change in percentage points (e.g., 0.50 -> 0.62 = 12.0).
        Compare against risk_triggers.odds_slope.threshold_pct to fire alerts.
        """
        return abs(new_price - old_price) * 100
