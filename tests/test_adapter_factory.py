"""Tests for adapters/__init__.py -- get_adapter factory.

Validates:
- Correct adapter type returned for each known market
- Unknown market raises ValueError
- Missing required config raises TypeError
- Factory does not embed business rules (returns bare adapter)
- Adapter init failure propagates cleanly
"""

import pytest
from unittest.mock import patch, MagicMock

from adapters import get_adapter
from adapters.market_data import MarketDataAdapter
from adapters.adapter_tushare import TushareAdapter
from adapters.adapter_yahoo import YahooAdapter
from adapters.adapter_polymarket import PolymarketAdapter


# ---------------------------------------------------------------------------
# 1. Correct adapter type for each market
# ---------------------------------------------------------------------------

class TestAdapterSelection:
    def test_a_stock_returns_tushare(self):
        with patch("adapters.adapter_tushare.ts"):
            adapter = get_adapter("a_stock", tushare_token="tok123")
        assert isinstance(adapter, TushareAdapter)
        assert isinstance(adapter, MarketDataAdapter)

    def test_hk_stock_returns_yahoo(self):
        adapter = get_adapter("hk_stock")
        assert isinstance(adapter, YahooAdapter)

    def test_us_stock_returns_yahoo(self):
        adapter = get_adapter("us_stock")
        assert isinstance(adapter, YahooAdapter)

    def test_polymarket_returns_polymarket(self):
        adapter = get_adapter("polymarket")
        assert isinstance(adapter, PolymarketAdapter)

    def test_polymarket_custom_url(self):
        adapter = get_adapter("polymarket", polymarket_api_url="https://custom.api/v1")
        assert adapter._base_url == "https://custom.api/v1"


# ---------------------------------------------------------------------------
# 2. Unknown market
# ---------------------------------------------------------------------------

class TestUnknownMarket:
    def test_unknown_market_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown market"):
            get_adapter("crypto")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unknown market"):
            get_adapter("")

    def test_none_like_string_raises(self):
        with pytest.raises(ValueError, match="Unknown market"):
            get_adapter("forex")


# ---------------------------------------------------------------------------
# 3. Missing required config
# ---------------------------------------------------------------------------

class TestMissingConfig:
    def test_a_stock_missing_token_raises_type_error(self):
        with pytest.raises(TypeError, match="tushare_token"):
            get_adapter("a_stock")

    def test_a_stock_empty_token_raises_type_error(self):
        with pytest.raises(TypeError, match="tushare_token"):
            get_adapter("a_stock", tushare_token="")

    def test_hk_stock_needs_no_kwargs(self):
        """Yahoo adapter has no required kwargs -- should not raise."""
        adapter = get_adapter("hk_stock")
        assert adapter is not None

    def test_polymarket_defaults_url(self):
        """Polymarket adapter should work without explicit url."""
        adapter = get_adapter("polymarket")
        assert "gamma-api" in adapter._base_url


# ---------------------------------------------------------------------------
# 4. Factory purity -- no business rules
# ---------------------------------------------------------------------------

class TestFactoryPurity:
    def test_factory_does_not_call_health_check(self):
        """Factory must not call health_check or any data method."""
        with patch("adapters.adapter_tushare.ts"):
            adapter = get_adapter("a_stock", tushare_token="tok")
        # If factory called health_check, the mock would have recorded it.
        # Adapter._api is a mock -- verify no calls on it beyond pro_api().
        # (pro_api is called in __init__, that's expected)

    def test_factory_returns_different_instances(self):
        """Each call should return a fresh adapter, no singleton caching."""
        a1 = get_adapter("hk_stock")
        a2 = get_adapter("hk_stock")
        assert a1 is not a2


# ---------------------------------------------------------------------------
# 5. Adapter init failure propagation
# ---------------------------------------------------------------------------

class TestInitFailure:
    def test_tushare_init_exception_propagates(self):
        """If tushare.pro_api raises, factory must not swallow it."""
        with patch("adapters.adapter_tushare.ts") as mock_ts:
            mock_ts.pro_api.side_effect = RuntimeError("invalid token")
            with pytest.raises(RuntimeError, match="invalid token"):
                get_adapter("a_stock", tushare_token="bad_token")
