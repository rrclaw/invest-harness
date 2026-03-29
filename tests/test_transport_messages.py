from lib.transport.messages import MessageKind, TransportMessage


def test_approval_message_renders_required_fields():
    message = TransportMessage.approval(
        title="Approval Needed",
        body="Please approve the locked hypothesis.",
        market="a_stock",
        hypothesis_ref="h_001",
        metadata={"priority": "high"},
    )

    text = message.render_text()
    assert message.kind == MessageKind.APPROVAL
    assert "Approval Needed" in text
    assert "Market: a_stock" in text
    assert "Hypothesis: h_001" in text
    assert "priority: high" in text


def test_alert_message_renders_level_and_source():
    message = TransportMessage.alert(
        title="Feed Degraded",
        body="Polling has degraded for 30 minutes.",
        market="hk_stock",
        level="L2",
        source="polling_daemon",
    )

    text = message.render_text()
    assert message.kind == MessageKind.ALERT
    assert "Level: L2" in text
    assert "Source: polling_daemon" in text


def test_review_message_renders_review_date():
    message = TransportMessage.review(
        title="Nightly Review",
        body="Three hits, one miss.",
        review_date="2026-03-27",
        market="global",
    )

    text = message.render_text()
    assert message.kind == MessageKind.REVIEW
    assert "Review Date: 2026-03-27" in text
