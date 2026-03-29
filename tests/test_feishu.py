import pytest
import hashlib
from unittest.mock import patch, MagicMock
from lib.db import get_connection, init_db
from lib.feishu import FeishuClient, FEISHU_GROUPS

TEST_GROUP_MAP = {
    "tailmon": "oc_test_tailmon",
    "agumon": "oc_test_agumon",
    "gabumon": "oc_test_gabumon",
    "gomamon": "oc_test_gomamon",
    "kabuterimon": "oc_test_kabuterimon",
    "patamon": "oc_test_patamon",
}


def test_group_ids_defined():
    assert "tailmon" in FEISHU_GROUPS
    assert "agumon" in FEISHU_GROUPS
    assert "gabumon" in FEISHU_GROUPS
    assert "gomamon" in FEISHU_GROUPS
    assert "kabuterimon" in FEISHU_GROUPS
    assert "patamon" in FEISHU_GROUPS


@pytest.fixture
def client(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    return FeishuClient(
        app_id="test_app",
        app_secret="test_secret",
        conn=conn,
        group_map=TEST_GROUP_MAP,
    )


def test_send_unconfigured_group_returns_reason(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    client = FeishuClient(
        app_id="test_app",
        app_secret="test_secret",
        conn=conn,
    )
    result = client.send_to_group("gomamon", "Test message")
    assert result["sent"] is False
    assert result["reason"] == "unconfigured_group"


def test_send_message(client):
    with patch("lib.feishu.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
        result = client.send_to_group("gomamon", "Test message")
    assert result["sent"] is True
    assert mock_post.call_count == 2  # token + message


def test_send_dedup_blocks_duplicate(client):
    with patch("lib.feishu.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
        client.send_to_group("gomamon", "Same message")
        result = client.send_to_group("gomamon", "Same message")
    assert result["sent"] is False
    assert result["reason"] == "dedup"


def test_send_different_groups_not_deduped(client):
    with patch("lib.feishu.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
        r1 = client.send_to_group("gomamon", "Same message")
        r2 = client.send_to_group("kabuterimon", "Same message")
    assert r1["sent"] is True
    assert r2["sent"] is True


def test_send_to_unknown_group_raises(client):
    with pytest.raises(ValueError, match="Unknown group"):
        client.send_to_group("unknown_group", "test")


def test_route_alert_l1_to_kabuterimon(client):
    target = client.route_alert("L1")
    assert target == "kabuterimon"


def test_route_alert_l2_to_gomamon(client):
    target = client.route_alert("L2")
    assert target == "gomamon"


def test_route_alert_l3_to_gomamon(client):
    target = client.route_alert("L3")
    assert target == "gomamon"


def test_route_approval_to_gabumon(client):
    target = client.route_approval()
    assert target == "gabumon"
