import pytest
from unittest.mock import MagicMock, patch
from scripts.polling_daemon import (
    PollingDaemon,
    HealthTracker,
    CONSECUTIVE_DEGRADED,
    CONSECUTIVE_FAILING,
)


@pytest.fixture
def health():
    return HealthTracker()


def test_health_tracker_initial_state(health):
    status = health.status()
    assert status["consecutive_failures"] == 0
    assert status["adapter_status"] == "healthy"
    assert status["circuit_broken"] is False


def test_health_tracker_record_success(health):
    health.record_success()
    assert health.status()["consecutive_failures"] == 0
    assert health.status()["adapter_status"] == "healthy"


def test_health_tracker_degraded(health):
    for _ in range(CONSECUTIVE_DEGRADED):
        health.record_failure()
    assert health.status()["adapter_status"] == "degraded"


def test_health_tracker_failing(health):
    for _ in range(CONSECUTIVE_FAILING):
        health.record_failure()
    status = health.status()
    assert status["adapter_status"] == "failing"
    assert status["alert_level"] == "L2"


def test_health_tracker_dead(health):
    for _ in range(10):
        health.record_failure()
    status = health.status()
    assert status["adapter_status"] == "dead"
    assert status["alert_level"] == "L1"


def test_health_tracker_reset_on_success(health):
    for _ in range(5):
        health.record_failure()
    health.record_success()
    assert health.status()["consecutive_failures"] == 0
    assert health.status()["adapter_status"] == "healthy"


def test_check_risk_triggers_no_breach():
    daemon = PollingDaemon.__new__(PollingDaemon)
    triggers = {"stock_rapid_drop": {"window_minutes": 15, "threshold_pct": -5.0, "volume_multiplier": 3.0}}
    events = daemon._check_risk_triggers(
        triggers=triggers,
        ticker="688256.SH",
        current_change_pct=-2.0,
        volume_ratio=1.5,
    )
    assert events == []


def test_check_risk_triggers_stock_rapid_drop():
    daemon = PollingDaemon.__new__(PollingDaemon)
    triggers = {"stock_rapid_drop": {"window_minutes": 15, "threshold_pct": -5.0, "volume_multiplier": 3.0}}
    events = daemon._check_risk_triggers(
        triggers=triggers,
        ticker="688256.SH",
        current_change_pct=-6.0,
        volume_ratio=4.0,
    )
    assert len(events) == 1
    assert events[0]["event_type"] == "stock_rapid_drop"
    assert events[0]["alert_level"] == "L2"


def test_check_risk_triggers_index_rapid_drop():
    daemon = PollingDaemon.__new__(PollingDaemon)
    triggers = {"index_rapid_drop": {"window_minutes": 30, "threshold_pct": -2.0}}
    events = daemon._check_risk_triggers(
        triggers=triggers,
        ticker="000001.SH",
        current_change_pct=-2.5,
        volume_ratio=1.0,
    )
    assert len(events) == 1
    assert events[0]["event_type"] == "index_rapid_drop"


def test_effective_interval_with_tier():
    daemon = PollingDaemon.__new__(PollingDaemon)
    assert daemon._effective_interval(3, 1.0) == 3.0
    assert daemon._effective_interval(3, 2.0) == 6.0
    assert daemon._effective_interval(5, 3.0) == 15.0


def test_handle_health_status_emits_alert_and_notifies():
    notifier = MagicMock()
    alert_mgr = MagicMock()
    alert_mgr.fire.return_value = {"alert_id": "alert_1", "level": "L1", "market": "a_stock", "message": "bad", "source": "polling_daemon"}
    daemon = PollingDaemon(
        market="a_stock",
        config={},
        adapter=MagicMock(),
        alert_mgr=alert_mgr,
        state_machine=MagicMock(),
        notifier=notifier,
    )

    alert = daemon.handle_health_status(
        {
            "adapter_status": "dead",
            "consecutive_failures": 10,
            "alert_level": "L1",
        }
    )

    assert alert["level"] == "L1"
    alert_mgr.fire.assert_called_once()
    notifier.send_alert.assert_called_once()


def test_emit_risk_trigger_alerts_returns_alerts():
    notifier = MagicMock()
    alert_mgr = MagicMock()
    alert_mgr.fire.side_effect = [
        {"alert_id": "alert_1", "level": "L2", "market": "a_stock", "message": "one", "source": "polling_daemon"},
        {"alert_id": "alert_2", "level": "L2", "market": "a_stock", "message": "two", "source": "polling_daemon"},
    ]
    daemon = PollingDaemon(
        market="a_stock",
        config={},
        adapter=MagicMock(),
        alert_mgr=alert_mgr,
        state_machine=MagicMock(),
        notifier=notifier,
    )

    alerts = daemon.emit_risk_trigger_alerts(
        [
            {"event_type": "index_rapid_drop", "ticker": "000001.SH", "observed_value": "drop", "alert_level": "L2"},
            {"event_type": "stock_rapid_drop", "ticker": "688256.SH", "observed_value": "drop", "alert_level": "L2"},
        ]
    )

    assert len(alerts) == 2
    assert alert_mgr.fire.call_count == 2
    assert notifier.send_alert.call_count == 2
