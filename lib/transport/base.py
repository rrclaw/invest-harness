"""Base classes for message transports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from lib.transport.messages import TransportMessage
from lib.transport.router import ResolvedTransportTarget, TransportRouter


class TransportConfigurationError(Exception):
    """Raised when runtime transport configuration is invalid."""


@dataclass(frozen=True)
class TransportSendResult:
    delivered: bool
    transport: str
    message_kind: str
    channel: str
    target_alias: str | None
    target_id: str | None
    payload_text: str
    reason: str | None = None
    external_id: str | None = None


class MessageTransport(ABC):
    """Abstract message transport."""

    transport_name = "base"

    def __init__(self, router: TransportRouter):
        self._router = router

    def send(self, message: TransportMessage) -> TransportSendResult:
        resolved = self._router.resolve(message)
        payload_text = message.render_text()
        return self._send_resolved(message, resolved, payload_text)

    @abstractmethod
    def _send_resolved(
        self,
        message: TransportMessage,
        resolved: ResolvedTransportTarget,
        payload_text: str,
    ) -> TransportSendResult:
        """Send an already-resolved payload."""
        ...
