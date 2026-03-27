import pytest
from unittest.mock import MagicMock, patch
from adapters.adapter_yahoo import YahooAdapter
from adapters.market_data import Quote, OHLCBar


@pytest.fixture
def adapter():
    with patch("adapters.adapter_yahoo.yf") as mock_yf:
        a = YahooAdapter()
        a._yf = mock_yf
        yield a, mock_yf


def test_get_quote(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "regularMarketPrice": 950.0,
        "regularMarketChangePercent": 3.2,
        "regularMarketVolume": 42000000,
    }
    mock_yf.Ticker.return_value = mock_ticker
    quote = a.get_quote("NVDA")
    assert isinstance(quote, Quote)
    assert quote.ticker == "NVDA"
    assert quote.price == 950.0
    assert quote.change_pct == 3.2


def test_get_quotes_multiple(adapter):
    import pandas as pd

    a, mock_yf = adapter
    mock_t1 = MagicMock()
    mock_t1.info = {"regularMarketPrice": 950.0, "regularMarketChangePercent": 3.2, "regularMarketVolume": 42000000}
    mock_t2 = MagicMock()
    mock_t2.info = {"regularMarketPrice": 180.0, "regularMarketChangePercent": -1.5, "regularMarketVolume": 30000000}
    mock_yf.Ticker.side_effect = [mock_t1, mock_t2]

    quotes = a.get_quotes(["NVDA", "TSLA"])
    assert len(quotes) == 2


def test_get_daily_bars(adapter):
    import pandas as pd
    from datetime import datetime

    a, mock_yf = adapter
    idx = pd.DatetimeIndex([datetime(2026, 3, 26)])
    mock_yf.download.return_value = pd.DataFrame(
        {
            "Open": [900.0],
            "High": [960.0],
            "Low": [895.0],
            "Close": [950.0],
            "Volume": [42000000],
        },
        index=idx,
    )
    bars = a.get_daily_bars("NVDA", "2026-03-25", "2026-03-26")
    assert len(bars) == 1
    assert isinstance(bars[0], OHLCBar)
    assert bars[0].close == 950.0


def test_health_check_success(adapter):
    a, mock_yf = adapter
    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 100.0}
    mock_yf.Ticker.return_value = mock_ticker
    assert a.health_check() is True


def test_health_check_failure(adapter):
    a, mock_yf = adapter
    mock_yf.Ticker.side_effect = Exception("Network error")
    assert a.health_check() is False
