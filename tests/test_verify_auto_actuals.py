"""Tests for fetch_actuals with adapter fallback."""

import pytest
from unittest.mock import MagicMock
from adapters.market_data import OHLCBar
from lib.verification import fetch_actuals


def _make_adapter(bars=None, error=None):
    adapter = MagicMock()
    if error:
        adapter.get_daily_bars.side_effect = error
    else:
        adapter.get_daily_bars.return_value = bars or []
    return adapter


def test_fetch_actuals_primary_success():
    primary = _make_adapter([OHLCBar("000001.SZ", 10.98, 11.02, 10.95, 10.99, 330000, "2026-03-30")])
    result = fetch_actuals(ticker="000001.SZ", market="a_stock", date="20260330",
                           adapters={"primary": primary, "fallback": None})
    assert result is not None
    assert result["close"] == 10.99
    assert result["source"] == "primary"


def test_fetch_actuals_fallback():
    primary = _make_adapter(error=Exception("502"))
    fallback = _make_adapter([OHLCBar("000001.SZ", 10.98, 11.02, 10.95, 10.99, 330000, "2026-03-30")])
    result = fetch_actuals(ticker="000001.SZ", market="a_stock", date="20260330",
                           adapters={"primary": primary, "fallback": fallback})
    assert result is not None
    assert result["close"] == 10.99
    assert result["source"] == "fallback"


def test_fetch_actuals_all_fail():
    primary = _make_adapter(error=Exception("fail"))
    result = fetch_actuals(ticker="000001.SZ", market="a_stock", date="20260330",
                           adapters={"primary": primary, "fallback": None})
    assert result is None


def test_fetch_actuals_primary_empty_bars():
    primary = _make_adapter([])  # empty bars
    fallback = _make_adapter([OHLCBar("MSFT", 383.0, 390.0, 380.0, 356.77, 37763600, "2026-03-27")])
    result = fetch_actuals(ticker="MSFT", market="us_stock", date="20260327",
                           adapters={"primary": primary, "fallback": fallback})
    assert result is not None
    assert result["source"] == "fallback"
