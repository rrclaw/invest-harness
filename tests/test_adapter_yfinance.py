"""Tests for YfinanceAdapter -- all network calls mocked."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from adapters.adapter_yfinance import YfinanceAdapter
from adapters.market_data import OHLCBar, Quote


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    """Return a YfinanceAdapter with yf module replaced by a MagicMock."""
    with patch("adapters.adapter_yfinance.yf") as mock_yf:
        a = YfinanceAdapter()
        a._yf = mock_yf
        yield a, mock_yf


# ---------------------------------------------------------------------------
# get_quote -- US stock
# ---------------------------------------------------------------------------


def test_get_quote_us_stock(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "regularMarketPrice": 415.50,
        "regularMarketChangePercent": 1.25,
        "regularMarketVolume": 25_000_000,
    }
    mock_yf.Ticker.return_value = mock_ticker

    quote = a.get_quote("MSFT")

    mock_yf.Ticker.assert_called_once_with("MSFT")
    assert isinstance(quote, Quote)
    assert quote.ticker == "MSFT"
    assert quote.price == 415.50
    assert quote.change_pct == 1.25
    assert quote.volume == 25_000_000
    assert isinstance(quote.timestamp, datetime)


# ---------------------------------------------------------------------------
# get_quote -- HK stock
# ---------------------------------------------------------------------------


def test_get_quote_hk_stock(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "regularMarketPrice": 372.40,
        "regularMarketChangePercent": -0.80,
        "regularMarketVolume": 18_000_000,
    }
    mock_yf.Ticker.return_value = mock_ticker

    quote = a.get_quote("0700.HK")

    mock_yf.Ticker.assert_called_once_with("0700.HK")
    assert isinstance(quote, Quote)
    assert quote.ticker == "0700.HK"
    assert quote.price == 372.40
    assert quote.change_pct == -0.80
    assert quote.volume == 18_000_000


# ---------------------------------------------------------------------------
# get_quote -- missing optional fields default to zero
# ---------------------------------------------------------------------------


def test_get_quote_missing_optional_fields(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 100.0}
    mock_yf.Ticker.return_value = mock_ticker

    quote = a.get_quote("XYZ")

    assert quote.change_pct == 0.0
    assert quote.volume == 0


# ---------------------------------------------------------------------------
# get_quotes -- multiple tickers
# ---------------------------------------------------------------------------


def test_get_quotes_multiple(adapter):
    a, mock_yf = adapter

    mock_msft = MagicMock()
    mock_msft.info = {
        "regularMarketPrice": 415.50,
        "regularMarketChangePercent": 1.25,
        "regularMarketVolume": 25_000_000,
    }
    mock_tencent = MagicMock()
    mock_tencent.info = {
        "regularMarketPrice": 372.40,
        "regularMarketChangePercent": -0.80,
        "regularMarketVolume": 18_000_000,
    }
    mock_yf.Ticker.side_effect = [mock_msft, mock_tencent]

    quotes = a.get_quotes(["MSFT", "0700.HK"])

    assert len(quotes) == 2
    assert quotes[0].ticker == "MSFT"
    assert quotes[1].ticker == "0700.HK"


def test_get_quotes_empty(adapter):
    a, mock_yf = adapter
    quotes = a.get_quotes([])
    assert quotes == []


# ---------------------------------------------------------------------------
# get_daily_bars
# ---------------------------------------------------------------------------


def _make_history_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame that mimics yf.Ticker.history() output."""
    index = pd.DatetimeIndex([r["date"] for r in rows])
    data = {
        "Open": [r["Open"] for r in rows],
        "High": [r["High"] for r in rows],
        "Low": [r["Low"] for r in rows],
        "Close": [r["Close"] for r in rows],
        "Volume": [r["Volume"] for r in rows],
    }
    return pd.DataFrame(data, index=index)


def test_get_daily_bars_single_bar(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_history_df(
        [{"date": "2026-03-26", "Open": 400.0, "High": 420.0, "Low": 395.0, "Close": 415.0, "Volume": 10_000_000}]
    )
    mock_yf.Ticker.return_value = mock_ticker

    bars = a.get_daily_bars("MSFT", "2026-03-25", "2026-03-27")

    mock_ticker.history.assert_called_once_with(start="2026-03-25", end="2026-03-27")
    assert len(bars) == 1
    bar = bars[0]
    assert isinstance(bar, OHLCBar)
    assert bar.ticker == "MSFT"
    assert bar.date == "2026-03-26"
    assert bar.open == 400.0
    assert bar.high == 420.0
    assert bar.low == 395.0
    assert bar.close == 415.0
    assert bar.volume == 10_000_000


def test_get_daily_bars_hk_stock(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_history_df(
        [
            {"date": "2026-03-25", "Open": 368.0, "High": 375.0, "Low": 365.0, "Close": 372.0, "Volume": 15_000_000},
            {"date": "2026-03-26", "Open": 372.0, "High": 380.0, "Low": 370.0, "Close": 378.0, "Volume": 20_000_000},
        ]
    )
    mock_yf.Ticker.return_value = mock_ticker

    bars = a.get_daily_bars("0700.HK", "2026-03-25", "2026-03-27")

    assert len(bars) == 2
    assert bars[0].ticker == "0700.HK"
    assert bars[0].date == "2026-03-25"
    assert bars[1].date == "2026-03-26"
    assert bars[1].close == 378.0


def test_get_daily_bars_empty(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
        index=pd.DatetimeIndex([]),
    )
    mock_yf.Ticker.return_value = mock_ticker

    bars = a.get_daily_bars("MSFT", "2026-03-25", "2026-03-26")
    assert bars == []


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


def test_health_check_success(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 189.0}
    mock_yf.Ticker.return_value = mock_ticker

    assert a.health_check() is True


def test_health_check_missing_price_key(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Apple Inc."}  # no regularMarketPrice
    mock_yf.Ticker.return_value = mock_ticker

    assert a.health_check() is False


def test_health_check_exception(adapter):
    a, mock_yf = adapter
    mock_yf.Ticker.side_effect = Exception("Network unreachable")

    assert a.health_check() is False
