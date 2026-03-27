"""Adapter factory -- returns the correct MarketDataAdapter for a market.

Pure selection + instantiation. No business rules live here.
"""

from __future__ import annotations

from adapters.market_data import MarketDataAdapter


def get_adapter(market: str, **kwargs) -> MarketDataAdapter:
    """Return the appropriate adapter for a given market.

    Returns a lazy instance -- no network connectivity check is performed.
    The adapter will only contact its data source when a method like
    ``get_quote()`` or ``get_daily_bars()`` is actually called.

    Args:
        market: One of 'a_stock', 'hk_stock', 'us_stock', 'polymarket'.
        **kwargs: Adapter-specific config (e.g., tushare_token, polymarket_api_url).

    Raises:
        ValueError: If market is not recognised.
        TypeError: If required adapter kwargs are missing.
    """
    if market == "a_stock":
        from adapters.adapter_tushare import TushareAdapter

        token = kwargs.get("tushare_token")
        if not token:
            raise TypeError(
                "a_stock adapter requires 'tushare_token' kwarg"
            )
        return TushareAdapter(token=token)

    if market in ("hk_stock", "us_stock"):
        from adapters.adapter_yahoo import YahooAdapter

        return YahooAdapter()

    if market == "polymarket":
        from adapters.adapter_polymarket import PolymarketAdapter

        return PolymarketAdapter(
            api_url=kwargs.get(
                "polymarket_api_url", "https://gamma-api.polymarket.com"
            )
        )

    raise ValueError(f"Unknown market: {market!r}")
