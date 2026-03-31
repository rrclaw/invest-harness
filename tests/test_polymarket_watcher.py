"""Tests for PolymarketWatcher."""

import pytest
from unittest.mock import MagicMock
from scripts.polymarket_watcher import PolymarketWatcher


@pytest.fixture
def mock_adapter():
    return MagicMock()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_runs_by_phase_and_window.return_value = []
    return store


@pytest.fixture
def watcher(mock_adapter, mock_store):
    return PolymarketWatcher(
        adapter=mock_adapter,
        run_store=mock_store,
        watchlist=["cid_1", "cid_2"],
    )


def test_detect_resolved(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_1",
        "resolved": True,
        "outcome": "yes",
        "final_price": 1.0,
    }
    events = watcher.check_market("cid_1")
    assert any(e["type"] == "resolved" for e in events)


def test_detect_price_spike(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.85,
        "price_change_24h": 0.15,
        "hours_to_expiry": 72,
    }
    events = watcher.check_market("cid_2")
    assert any(e["type"] == "price_spike" for e in events)


def test_detect_expiring_soon(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.60,
        "price_change_24h": 0.02,
        "hours_to_expiry": 12,
    }
    events = watcher.check_market("cid_2")
    assert any(e["type"] == "expiring_soon" for e in events)


def test_no_events(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.50,
        "price_change_24h": 0.01,
        "hours_to_expiry": 168,
    }
    events = watcher.check_market("cid_2")
    assert len(events) == 0
