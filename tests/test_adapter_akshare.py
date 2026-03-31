"""Tests for adapters/adapter_akshare.py.

Validates:
- Ticker suffix stripping (000001.SZ -> 000001)
- get_quote() parses akshare spot DataFrame correctly
- get_quotes() handles multiple tickers, skips missing codes
- get_daily_bars() maps Chinese column names to OHLCBar fields
- health_check() returns True/False based on API availability
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, MagicMock

from adapters.adapter_akshare import AkshareAdapter, _strip_suffix
from adapters.market_data import Quote, OHLCBar


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

SPOT_DF = pd.DataFrame(
    [
        {
            "代码": "000001",
            "名称": "平安银行",
            "最新价": 12.34,
            "涨跌幅": 1.5,
            "成交量": 5000000,
        },
        {
            "代码": "300750",
            "名称": "宁德时代",
            "最新价": 220.0,
            "涨跌幅": -0.8,
            "成交量": 3000000,
        },
    ]
)

HIST_DF = pd.DataFrame(
    [
        {
            "日期": "2026-03-25",
            "开盘": 12.10,
            "收盘": 12.30,
            "最高": 12.50,
            "最低": 12.00,
            "成交量": 4500000,
        },
        {
            "日期": "2026-03-26",
            "开盘": 12.30,
            "收盘": 12.34,
            "最高": 12.60,
            "最低": 12.20,
            "成交量": 5000000,
        },
    ]
)


@pytest.fixture
def adapter():
    return AkshareAdapter()


# ---------------------------------------------------------------------------
# Ticker normalisation
# ---------------------------------------------------------------------------

class TestStripSuffix:
    def test_sz_suffix_stripped(self):
        assert _strip_suffix("000001.SZ") == "000001"

    def test_sh_suffix_stripped(self):
        assert _strip_suffix("688256.SH") == "688256"

    def test_bare_code_unchanged(self):
        assert _strip_suffix("000001") == "000001"

    def test_unknown_suffix_stripped(self):
        assert _strip_suffix("600519.SS") == "600519"


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------

class TestGetQuote:
    def test_returns_quote_instance(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert isinstance(q, Quote)

    def test_ticker_preserved_with_suffix(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert q.ticker == "000001.SZ"

    def test_price_parsed(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert q.price == 12.34

    def test_change_pct_parsed(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert q.change_pct == 1.5

    def test_volume_parsed(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert q.volume == 5000000

    def test_timestamp_is_datetime(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("000001.SZ")
        assert isinstance(q.timestamp, datetime)

    def test_second_ticker(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            q = adapter.get_quote("300750.SZ")
        assert q.price == 220.0
        assert q.change_pct == -0.8


# ---------------------------------------------------------------------------
# get_quotes
# ---------------------------------------------------------------------------

class TestGetQuotes:
    def test_returns_list(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["000001.SZ", "300750.SZ"])
        assert isinstance(results, list)

    def test_returns_correct_count(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["000001.SZ", "300750.SZ"])
        assert len(results) == 2

    def test_tickers_preserved(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["000001.SZ", "300750.SZ"])
        tickers = {q.ticker for q in results}
        assert "000001.SZ" in tickers
        assert "300750.SZ" in tickers

    def test_missing_code_skipped(self, adapter):
        """A ticker not present in the spot DataFrame is silently skipped."""
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["000001.SZ", "999999.SZ"])
        assert len(results) == 1
        assert results[0].ticker == "000001.SZ"

    def test_all_missing_returns_empty(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["999998.SZ", "999999.SZ"])
        assert results == []

    def test_single_ticker_list(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            results = adapter.get_quotes(["300750.SZ"])
        assert len(results) == 1
        assert results[0].price == 220.0


# ---------------------------------------------------------------------------
# get_daily_bars
# ---------------------------------------------------------------------------

class TestGetDailyBars:
    def test_returns_list_of_ohlcbars(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF):
            bars = adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        assert len(bars) == 2
        assert all(isinstance(b, OHLCBar) for b in bars)

    def test_ticker_preserved(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF):
            bars = adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        assert all(b.ticker == "000001.SZ" for b in bars)

    def test_ohlcv_values(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF):
            bars = adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        b = bars[0]
        assert b.open == 12.10
        assert b.close == 12.30
        assert b.high == 12.50
        assert b.low == 12.00
        assert b.volume == 4500000

    def test_date_format(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF):
            bars = adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        assert bars[0].date == "2026-03-25"
        assert bars[1].date == "2026-03-26"

    def test_akshare_called_with_stripped_code(self, adapter):
        """Verify akshare receives bare code, not the suffixed ticker."""
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF) as mock_hist:
            adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        call_kwargs = mock_hist.call_args
        assert call_kwargs.kwargs.get("symbol") == "000001" or call_kwargs.args[0] == "000001"

    def test_date_hyphens_stripped_for_akshare(self, adapter):
        """start_date/end_date with hyphens must be converted to YYYYMMDD."""
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=HIST_DF) as mock_hist:
            adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        call_kwargs = mock_hist.call_args
        assert call_kwargs.kwargs.get("start_date") == "20260325"
        assert call_kwargs.kwargs.get("end_date") == "20260326"

    def test_empty_dataframe_returns_empty_list(self, adapter):
        empty_df = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        with patch("adapters.adapter_akshare.ak.stock_zh_a_hist", return_value=empty_df):
            bars = adapter.get_daily_bars("000001.SZ", "2026-03-25", "2026-03-26")
        assert bars == []


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_true_when_api_ok(self, adapter):
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=SPOT_DF):
            assert adapter.health_check() is True

    def test_returns_false_when_api_raises(self, adapter):
        with patch(
            "adapters.adapter_akshare.ak.stock_zh_a_spot_em",
            side_effect=Exception("network error"),
        ):
            assert adapter.health_check() is False

    def test_returns_false_when_empty_dataframe(self, adapter):
        empty_df = pd.DataFrame()
        with patch("adapters.adapter_akshare.ak.stock_zh_a_spot_em", return_value=empty_df):
            assert adapter.health_check() is False
