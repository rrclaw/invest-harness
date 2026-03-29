"""No-op transport for local development and dry runs."""

from __future__ import annotations

from lib.transport.base import MessageTransport, TransportSendResult
from lib.transport.messages import TransportMessage
from lib.transport.router import ResolvedTransportTarget


class NoopTransport(MessageTransport):
    transport_name = "noop"

    def _send_resolved(
        self,
        message: TransportMessage,
        resolved: ResolvedTransportTarget,
        payload_text: str,
    ) -> TransportSendResult:
        return TransportSendResult(
            delivered=False,
            transport=self.transport_name,
            message_kind=message.kind.value,
            channel=resolved.channel,
            target_alias=resolved.target_alias,
            target_id=resolved.target_id,
            payload_text=payload_text,
            reason="noop",
        )
