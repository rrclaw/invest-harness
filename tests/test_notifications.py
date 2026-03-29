from lib.notifications import NotificationService
from types import SimpleNamespace


class DummyTransport:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return SimpleNamespace(
            delivered=True,
            transport="dummy",
            message_kind=message.kind.value,
            channel="feishu",
            target_alias=message.target,
            target_id=None,
            payload_text=message.render_text(),
            reason=None,
            external_id=None,
        )


def test_send_approval_request_uses_approval_message():
    transport = DummyTransport()
    service = NotificationService(transport)
    result = service.send_approval_request(
        {
            "hypothesis_id": "h_001",
            "market": "a_stock",
            "ticker": "688256.SH",
            "trigger_event": "Earnings beat",
            "probability": 0.7,
            "status": "draft",
        },
        date="2026-03-27",
        target="gabumon",
    )
    assert result["message_kind"] == "approval"
    assert transport.sent[0].target == "gabumon"


def test_send_alert_uses_alert_message():
    transport = DummyTransport()
    service = NotificationService(transport)
    result = service.send_alert(
        {
            "alert_id": "alert_001",
            "level": "L2",
            "market": "a_stock",
            "message": "Rapid drop detected",
            "source": "polling_daemon",
            "hypothesis_ref": "h_001",
        }
    )
    assert result["message_kind"] == "alert"
    assert "Rapid drop detected" in result["payload_text"]


def test_send_review_uses_review_message():
    transport = DummyTransport()
    service = NotificationService(transport)
    result = service.send_review(
        review_date="2026-03-27",
        markdown="# Review\nAll good.",
    )
    assert result["message_kind"] == "review"


def test_send_broadcast_uses_broadcast_message():
    transport = DummyTransport()
    service = NotificationService(transport)
    result = service.send_broadcast(
        title="Backup Complete",
        body="All backup targets succeeded.",
        market="global",
    )
    assert result["message_kind"] == "broadcast"
