import pytest

from lib.transport.messages import TransportMessage
from lib.transport.router import TransportRouter


def test_router_resolves_approval_target_from_config():
    router = TransportRouter(
        channel="feishu",
        routing={"approval": {"target": "gabumon"}},
        group_map={"gabumon": "oc_123"},
    )
    message = TransportMessage.approval(
        title="Approve",
        body="Please review.",
        market="a_stock",
        hypothesis_ref="h_001",
    )

    resolved = router.resolve(message)
    assert resolved.channel == "feishu"
    assert resolved.target_alias == "gabumon"
    assert resolved.target_id == "oc_123"


def test_router_resolves_alert_targets_by_level():
    router = TransportRouter(
        channel="feishu",
        routing={
            "alert": {
                "default_target": "gomamon",
                "level_targets": {"L1": "kabuterimon"},
            }
        },
        group_map={"kabuterimon": "oc_l1", "gomamon": "oc_default"},
    )

    l1 = router.resolve(
        TransportMessage.alert(
            title="Critical",
            body="API blocked",
            market="a_stock",
            level="L1",
            source="adapter",
        )
    )
    l2 = router.resolve(
        TransportMessage.alert(
            title="Warn",
            body="Degraded feed",
            market="a_stock",
            level="L2",
            source="adapter",
        )
    )

    assert l1.target_alias == "kabuterimon"
    assert l1.target_id == "oc_l1"
    assert l2.target_alias == "gomamon"
    assert l2.target_id == "oc_default"


def test_router_raises_when_route_missing():
    router = TransportRouter(channel="feishu", routing={}, group_map={})
    message = TransportMessage.broadcast(title="Ping", body="Hello")
    with pytest.raises(ValueError, match="missing target"):
        router.resolve(message)
