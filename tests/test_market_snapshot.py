import pytest
from unittest.mock import MagicMock
from scripts.market_snapshot import build_snapshot
from adapters.market_data import Quote
from datetime import datetime, timezone


def _make_quote(ticker, price, change_pct, volume):
    return Quote(
        ticker=ticker,
        price=price,
        change_pct=change_pct,
        volume=volume,
        timestamp=datetime.now(timezone.utc),
    )


def test_build_snapshot_basic():
    quotes = [_make_quote("688256.SH", 312.5, 6.8, 15000000)]
    hypotheses = [
        {
            "hypothesis_id": "h_20260326_a_001",
            "ticker": "688256.SH",
            "invalidation_conditions": ["Auction volume < 5% of yesterday"],
        }
    ]
    snapshot = build_snapshot(
        market="a_stock",
        data_source="tushare",
        quotes=quotes,
        hypotheses=hypotheses,
        health_status={"consecutive_failures": 0, "last_heartbeat": "now", "circuit_broken": False, "adapter_status": "healthy"},
    )
    assert snapshot["market"] == "a_stock"
    assert snapshot["data_source"] == "tushare"
    assert len(snapshot["hypothesis_checks"]) == 1
    assert snapshot["hypothesis_checks"][0]["hypothesis_ref"] == "h_20260326_a_001"


def test_build_snapshot_no_hypotheses():
    quotes = [_make_quote("688256.SH", 312.5, 6.8, 15000000)]
    snapshot = build_snapshot(
        market="a_stock",
        data_source="tushare",
        quotes=quotes,
        hypotheses=[],
        health_status={"consecutive_failures": 0, "last_heartbeat": "now", "circuit_broken": False, "adapter_status": "healthy"},
    )
    assert snapshot["hypothesis_checks"] == []


def test_build_snapshot_has_health_check():
    quotes = []
    health = {"consecutive_failures": 3, "last_heartbeat": "now", "circuit_broken": False, "adapter_status": "degraded"}
    snapshot = build_snapshot(
        market="a_stock",
        data_source="tushare",
        quotes=quotes,
        hypotheses=[],
        health_status=health,
    )
    assert snapshot["health_check"]["adapter_status"] == "degraded"
    assert snapshot["health_check"]["consecutive_failures"] == 3


def test_build_snapshot_validates_schema():
    from lib.schema_validator import validate
    quotes = [_make_quote("688256.SH", 312.5, 6.8, 15000000)]
    snapshot = build_snapshot(
        market="a_stock",
        data_source="tushare",
        quotes=quotes,
        hypotheses=[],
        health_status={"consecutive_failures": 0, "last_heartbeat": "2026-03-26T09:45:00+08:00", "circuit_broken": False, "adapter_status": "healthy"},
    )
    validate(snapshot, "monitor_snapshot")  # Should not raise
