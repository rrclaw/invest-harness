"""Business-facing notification wiring on top of transports."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

from lib.transport import TransportMessage


class NotificationService:
    """Translate business events into transport messages."""

    def __init__(self, transport):
        self._transport = transport

    def _serialize_result(self, result) -> dict:
        if is_dataclass(result):
            return asdict(result)
        if hasattr(result, "__dict__"):
            return dict(result.__dict__)
        raise TypeError(f"Unsupported transport result type: {type(result)!r}")

    def send_alert(self, alert: dict, *, target: str | None = None) -> dict:
        message = TransportMessage.alert(
            title=f"{alert['level']} Alert",
            body=alert["message"],
            market=alert["market"],
            level=alert["level"],
            source=alert.get("source", "unknown"),
            target=target,
            hypothesis_ref=alert.get("hypothesis_ref"),
            metadata={"alert_id": alert.get("alert_id")},
        )
        return self._serialize_result(self._transport.send(message))

    def send_approval_request(
        self,
        hypothesis: dict,
        *,
        date: str | None = None,
        target: str | None = None,
    ) -> dict:
        title = f"Approval Needed: {hypothesis['market']} {hypothesis['ticker']}"
        body_lines = [
            f"Hypothesis ID: {hypothesis['hypothesis_id']}",
            f"Ticker: {hypothesis['ticker']}",
            f"Trigger: {hypothesis.get('trigger_event', '')}",
            f"Probability: {hypothesis.get('probability', '')}",
            f"Status: {hypothesis.get('status', '')}",
        ]
        if date:
            body_lines.append(f"Exchange Date: {date}")

        message = TransportMessage.approval(
            title=title,
            body="\n".join(body_lines),
            market=hypothesis["market"],
            hypothesis_ref=hypothesis["hypothesis_id"],
            target=target,
            metadata={"ticker": hypothesis["ticker"]},
        )
        return self._serialize_result(self._transport.send(message))

    def send_review(
        self,
        *,
        review_date: str,
        markdown: str,
        market: str | None = "global",
        target: str | None = None,
    ) -> dict:
        message = TransportMessage.review(
            title=f"Nightly Review {review_date}",
            body=markdown,
            review_date=review_date,
            market=market,
            target=target,
        )
        return self._serialize_result(self._transport.send(message))

    def send_broadcast(
        self,
        *,
        title: str,
        body: str,
        market: str | None = None,
        target: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> dict:
        message = TransportMessage.broadcast(
            title=title,
            body=body,
            market=market,
            target=target,
            metadata=metadata,
        )
        return self._serialize_result(self._transport.send(message))
