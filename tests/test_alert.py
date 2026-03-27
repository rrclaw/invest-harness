import pytest
from lib.db import get_connection, init_db
from lib.alert import AlertManager


@pytest.fixture
def alert_mgr(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    return AlertManager(conn)


def test_fire_l3_alert(alert_mgr):
    alert = alert_mgr.fire(
        level="L3",
        market="a_stock",
        message="Snapshot completed for 688256.SH",
        source="polling_daemon",
    )
    assert alert["alert_id"].startswith("alert_")
    assert alert["level"] == "L3"


def test_fire_l2_alert(alert_mgr):
    alert = alert_mgr.fire(
        level="L2",
        market="a_stock",
        message="Data feed degraded for a_stock",
        source="polling_daemon",
        hypothesis_ref="h_20260326_a_001",
    )
    assert alert["level"] == "L2"
    assert alert["hypothesis_ref"] == "h_20260326_a_001"


def test_fire_l1_alert(alert_mgr):
    alert = alert_mgr.fire(
        level="L1",
        market="a_stock",
        message="API blocked, retry exhausted",
        source="adapter_tushare",
    )
    assert alert["level"] == "L1"


def test_get_unacknowledged_alerts(alert_mgr):
    alert_mgr.fire("L2", "a_stock", "msg1", "src1")
    alert_mgr.fire("L3", "a_stock", "msg2", "src2")
    alerts = alert_mgr.get_unacknowledged()
    assert len(alerts) == 2


def test_acknowledge_alert(alert_mgr):
    alert = alert_mgr.fire("L2", "a_stock", "msg", "src")
    alert_mgr.acknowledge(alert["alert_id"])
    unacked = alert_mgr.get_unacknowledged()
    assert len(unacked) == 0


def test_get_alerts_by_level(alert_mgr):
    alert_mgr.fire("L1", "a_stock", "critical", "src")
    alert_mgr.fire("L2", "a_stock", "warning", "src")
    alert_mgr.fire("L3", "a_stock", "info", "src")
    l1_alerts = alert_mgr.get_by_level("L1")
    assert len(l1_alerts) == 1
    assert l1_alerts[0]["message"] == "critical"


def test_get_alerts_by_market(alert_mgr):
    alert_mgr.fire("L2", "a_stock", "msg1", "src")
    alert_mgr.fire("L2", "hk_stock", "msg2", "src")
    a_alerts = alert_mgr.get_by_market("a_stock")
    assert len(a_alerts) == 1


def test_alert_id_uniqueness(alert_mgr):
    a1 = alert_mgr.fire("L3", "a_stock", "msg1", "src")
    a2 = alert_mgr.fire("L3", "a_stock", "msg2", "src")
    assert a1["alert_id"] != a2["alert_id"]
