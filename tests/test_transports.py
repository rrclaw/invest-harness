import subprocess
from unittest.mock import MagicMock

from lib.transport import (
    DirectFeishuTransport,
    NoopTransport,
    OpenClawTransport,
    TransportMessage,
    TransportRouter,
)


GROUP_MAP = {
    "gabumon": "oc_gabu",
    "gomamon": "oc_goma",
    "kabuterimon": "oc_kabu",
}

ROUTING = {
    "approval": {"target": "gabumon"},
    "broadcast": {"target": "gomamon"},
    "review": {"target": "gomamon"},
    "alert": {
        "default_target": "gomamon",
        "level_targets": {"L1": "kabuterimon", "L2": "gomamon", "L3": "gomamon"},
    },
}


def _router() -> TransportRouter:
    return TransportRouter(channel="feishu", routing=ROUTING, group_map=GROUP_MAP)


def test_noop_transport_returns_noop_reason():
    transport = NoopTransport(_router())
    result = transport.send(
        TransportMessage.broadcast(title="Heartbeat", body="All systems nominal.")
    )
    assert result.delivered is False
    assert result.reason == "noop"
    assert result.target_alias == "gomamon"


def test_direct_feishu_transport_delegates_to_client():
    client = MagicMock()
    client.send_to_group.return_value = {"sent": True, "status_code": 200}
    transport = DirectFeishuTransport(_router(), client)

    result = transport.send(
        TransportMessage.approval(
            title="Approve",
            body="Please approve.",
            market="a_stock",
            hypothesis_ref="h_001",
        )
    )

    assert result.delivered is True
    client.send_to_group.assert_called_once()
    sent_group, sent_payload = client.send_to_group.call_args.args
    assert sent_group == "gabumon"
    assert "[APPROVAL] Approve" in sent_payload


def test_openclaw_transport_builds_cli_command(mocker):
    mock_run = mocker.patch("lib.transport.openclaw.subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
    transport = OpenClawTransport(
        _router(),
        executable="openclaw",
        target_prefix="chat",
        timeout_seconds=20,
        workspace_root="/tmp/workspace",
    )

    result = transport.send(
        TransportMessage.alert(
            title="Critical",
            body="API blocked",
            market="a_stock",
            level="L1",
            source="adapter_tushare",
        )
    )

    assert result.delivered is True
    command = mock_run.call_args.args[0]
    assert command[:4] == ["openclaw", "message", "send", "--channel"]
    assert "chat:oc_kabu" in command
    assert mock_run.call_args.kwargs["cwd"] == "/tmp/workspace"


def test_openclaw_transport_handles_missing_binary(mocker):
    mocker.patch(
        "lib.transport.openclaw.subprocess.run",
        side_effect=FileNotFoundError("openclaw not found"),
    )
    transport = OpenClawTransport(_router())

    result = transport.send(
        TransportMessage.review(
            title="Nightly Review",
            body="Summary",
            review_date="2026-03-27",
        )
    )

    assert result.delivered is False
    assert "openclaw not found" in result.reason
