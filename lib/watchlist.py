"""Watchlist management utilities for invest_harness."""

import json
from datetime import date
from pathlib import Path

__all__ = ["detect_market", "add_ticker", "remove_ticker", "list_tickers"]

_MARKETS = ["a_stock", "hk_stock", "us_stock", "polymarket"]

_EMPTY_WATCHLIST: dict = {m: [] for m in _MARKETS}


def detect_market(ticker: str) -> str:
    """Auto-detect market from ticker suffix.

    .SZ/.SH -> a_stock, .HK -> hk_stock, pure alpha -> us_stock
    """
    upper = ticker.upper()
    if upper.endswith(".SZ") or upper.endswith(".SH"):
        return "a_stock"
    if upper.endswith(".HK"):
        return "hk_stock"
    return "us_stock"


def _load(watchlist_path: Path) -> dict:
    if watchlist_path.exists():
        with open(watchlist_path, encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all expected market keys are present
        for m in _MARKETS:
            data.setdefault(m, [])
        return data
    return {m: [] for m in _MARKETS}


def _save(watchlist_path: Path, data: dict) -> None:
    watchlist_path.parent.mkdir(parents=True, exist_ok=True)
    with open(watchlist_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_ticker(
    watchlist_path: Path,
    *,
    ticker: str,
    market: str,
    added_by: str = "user",
    name: str | None = None,
) -> dict:
    """Add ticker to watchlist. Returns {"added": True/False, ...}. Noop if exists."""
    data = _load(watchlist_path)
    entries = data.setdefault(market, [])

    for entry in entries:
        if entry["ticker"] == ticker:
            return {"added": False, "ticker": ticker, "market": market, "reason": "already_exists"}

    entry: dict = {
        "ticker": ticker,
        "added_at": date.today().isoformat(),
        "added_by": added_by,
    }
    if name is not None:
        entry["name"] = name

    entries.append(entry)
    _save(watchlist_path, data)
    return {"added": True, "ticker": ticker, "market": market}


def remove_ticker(watchlist_path: Path, *, ticker: str, market: str) -> dict:
    """Remove ticker. Returns {"removed": True/False, ...}."""
    data = _load(watchlist_path)
    entries = data.get(market, [])

    new_entries = [e for e in entries if e["ticker"] != ticker]
    if len(new_entries) == len(entries):
        return {"removed": False, "ticker": ticker, "market": market, "reason": "not_found"}

    data[market] = new_entries
    _save(watchlist_path, data)
    return {"removed": True, "ticker": ticker, "market": market}


def list_tickers(watchlist_path: Path, *, market: str | None = None) -> list | dict:
    """List tickers. If market given, returns list. If None, returns full dict."""
    data = _load(watchlist_path)
    if market is not None:
        return data.get(market, [])
    return data
