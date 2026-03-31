"""Tests for lib/watchlist.py"""

import json
import pytest
from pathlib import Path

from lib.watchlist import detect_market, add_ticker, remove_ticker, list_tickers


# ---------------------------------------------------------------------------
# detect_market
# ---------------------------------------------------------------------------

def test_detect_market_sz():
    assert detect_market("000001.SZ") == "a_stock"


def test_detect_market_sh():
    assert detect_market("600519.SH") == "a_stock"


def test_detect_market_hk():
    assert detect_market("0700.HK") == "hk_stock"


def test_detect_market_us_pure_alpha():
    assert detect_market("AAPL") == "us_stock"


def test_detect_market_us_mixed():
    assert detect_market("BRK.B") == "us_stock"


# ---------------------------------------------------------------------------
# add_ticker
# ---------------------------------------------------------------------------

def test_add_new_ticker(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = add_ticker(wl, ticker="600519.SH", market="a_stock", name="贵州茅台")
    assert result["added"] is True
    assert result["ticker"] == "600519.SH"
    assert result["market"] == "a_stock"

    data = json.loads(wl.read_text())
    assert len(data["a_stock"]) == 1
    entry = data["a_stock"][0]
    assert entry["ticker"] == "600519.SH"
    assert entry["name"] == "贵州茅台"
    assert entry["added_by"] == "user"
    assert "added_at" in entry


def test_add_ticker_without_name(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = add_ticker(wl, ticker="AAPL", market="us_stock")
    assert result["added"] is True
    data = json.loads(wl.read_text())
    entry = data["us_stock"][0]
    assert "name" not in entry


def test_add_duplicate_is_noop(tmp_path):
    wl = tmp_path / "watchlist.json"
    add_ticker(wl, ticker="600519.SH", market="a_stock")
    result = add_ticker(wl, ticker="600519.SH", market="a_stock")
    assert result["added"] is False
    assert result["reason"] == "already_exists"

    data = json.loads(wl.read_text())
    assert len(data["a_stock"]) == 1


def test_add_ticker_custom_added_by(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = add_ticker(wl, ticker="TSLA", market="us_stock", added_by="system")
    assert result["added"] is True
    data = json.loads(wl.read_text())
    assert data["us_stock"][0]["added_by"] == "system"


# ---------------------------------------------------------------------------
# remove_ticker
# ---------------------------------------------------------------------------

def test_remove_existing_ticker(tmp_path):
    wl = tmp_path / "watchlist.json"
    add_ticker(wl, ticker="0700.HK", market="hk_stock")
    result = remove_ticker(wl, ticker="0700.HK", market="hk_stock")
    assert result["removed"] is True

    data = json.loads(wl.read_text())
    assert data["hk_stock"] == []


def test_remove_nonexistent_ticker(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = remove_ticker(wl, ticker="NONEXISTENT", market="us_stock")
    assert result["removed"] is False
    assert result["reason"] == "not_found"


def test_remove_only_removes_target(tmp_path):
    wl = tmp_path / "watchlist.json"
    add_ticker(wl, ticker="AAPL", market="us_stock")
    add_ticker(wl, ticker="TSLA", market="us_stock")
    remove_ticker(wl, ticker="AAPL", market="us_stock")

    data = json.loads(wl.read_text())
    tickers = [e["ticker"] for e in data["us_stock"]]
    assert tickers == ["TSLA"]


# ---------------------------------------------------------------------------
# list_tickers
# ---------------------------------------------------------------------------

def test_list_by_market(tmp_path):
    wl = tmp_path / "watchlist.json"
    add_ticker(wl, ticker="600519.SH", market="a_stock")
    add_ticker(wl, ticker="AAPL", market="us_stock")

    result = list_tickers(wl, market="a_stock")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["ticker"] == "600519.SH"


def test_list_by_market_empty(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = list_tickers(wl, market="hk_stock")
    assert result == []


def test_list_all_returns_dict(tmp_path):
    wl = tmp_path / "watchlist.json"
    add_ticker(wl, ticker="600519.SH", market="a_stock")
    add_ticker(wl, ticker="0700.HK", market="hk_stock")

    result = list_tickers(wl)
    assert isinstance(result, dict)
    assert "a_stock" in result
    assert "hk_stock" in result
    assert "us_stock" in result
    assert "polymarket" in result
    assert len(result["a_stock"]) == 1
    assert len(result["hk_stock"]) == 1


def test_list_all_on_empty_file(tmp_path):
    wl = tmp_path / "watchlist.json"
    result = list_tickers(wl)
    assert isinstance(result, dict)
    assert result == {"a_stock": [], "hk_stock": [], "us_stock": [], "polymarket": []}
