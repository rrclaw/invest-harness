"""Direct Feishu API transport."""

from __future__ import annotations

from lib.feishu import FeishuClient
from lib.transport.base import MessageTransport, TransportSendResult
from lib.transport.messages import TransportMessage
from lib.transport.router import ResolvedTransportTarget


class DirectFeishuTransport(MessageTransport):
    transport_name = "direct_feishu"

    def __init__(self, router, client: FeishuClient):
        super().__init__(router)
        self._client = client

    def _send_resolved(
        self,
        message: TransportMessage,
        resolved: ResolvedTransportTarget,
        payload_text: str,
    ) -> TransportSendResult:
        result = self._client.send_to_group(resolved.target_alias, payload_text)
        return TransportSendResult(
            delivered=bool(result.get("sent")),
            transport=self.transport_name,
            message_kind=message.kind.value,
            channel=resolved.channel,
            target_alias=resolved.target_alias,
            target_id=resolved.target_id,
            payload_text=payload_text,
            reason=result.get("reason"),
            external_id=str(result.get("status_code")) if result.get("status_code") else None,
        )
