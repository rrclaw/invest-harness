import pytest
from unittest.mock import MagicMock, patch
from adapters.adapter_tushare import TushareAdapter
from adapters.market_data import Quote, OHLCBar


@pytest.fixture
def mock_ts_api():
    """Mock tushare pro_api."""
    with patch("adapters.adapter_tushare.ts") as mock_ts:
        mock_api = MagicMock()
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


@pytest.fixture
def adapter(mock_ts_api):
    return TushareAdapter(token="test_token")


def test_get_quote(adapter, mock_ts_api):
    import pandas as pd

    mock_ts_api.realtime_quote.return_value = pd.DataFrame(
        [
            {
                "TS_CODE": "688256.SH",
                "PRICE": 312.5,
                "CHANGE": 6.8,
                "VOL": 15000000,
                "DATETIME": "2026-03-26 14:30:00",
            }
        ]
    )
    quote = adapter.get_quote("688256.SH")
    assert isinstance(quote, Quote)
    assert quote.ticker == "688256.SH"
    assert quote.price == 312.5
    assert quote.change_pct == 6.8


def test_get_quotes_multiple(adapter, mock_ts_api):
    import pandas as pd

    mock_ts_api.realtime_quote.return_value = pd.DataFrame(
        [
            {"TS_CODE": "688256.SH", "PRICE": 312.5, "CHANGE": 6.8, "VOL": 15000000, "DATETIME": "2026-03-26 14:30:00"},
            {"TS_CODE": "300750.SZ", "PRICE": 220.0, "CHANGE": -1.2, "VOL": 8000000, "DATETIME": "2026-03-26 14:30:00"},
        ]
    )
    quotes = adapter.get_quotes(["688256.SH", "300750.SZ"])
    assert len(quotes) == 2
    assert quotes[0].ticker == "688256.SH"
    assert quotes[1].ticker == "300750.SZ"


def test_get_daily_bars(adapter, mock_ts_api):
    import pandas as pd

    mock_ts_api.daily.return_value = pd.DataFrame(
        [
            {
                "ts_code": "688256.SH",
                "open": 300.0,
                "high": 315.0,
                "low": 298.0,
                "close": 312.5,
                "vol": 15000000,
                "trade_date": "20260326",
            }
        ]
    )
    bars = adapter.get_daily_bars("688256.SH", "2026-03-25", "2026-03-26")
    assert len(bars) == 1
    assert isinstance(bars[0], OHLCBar)
    assert bars[0].close == 312.5
    assert bars[0].date == "2026-03-26"


def test_health_check_success(adapter, mock_ts_api):
    import pandas as pd

    mock_ts_api.trade_cal.return_value = pd.DataFrame([{"exchange": "SSE"}])
    assert adapter.health_check() is True


def test_health_check_failure(adapter, mock_ts_api):
    mock_ts_api.trade_cal.side_effect = Exception("API down")
    assert adapter.health_check() is False
