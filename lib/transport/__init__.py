"""Transport abstraction layer."""

from lib.transport.base import (
    MessageTransport,
    TransportConfigurationError,
    TransportSendResult,
)
from lib.transport.direct_feishu import DirectFeishuTransport
from lib.transport.factory import (
    build_transport,
    build_transport_from_config,
    normalize_transport_type,
)
from lib.transport.messages import MessageKind, TransportMessage
from lib.transport.noop import NoopTransport
from lib.transport.openclaw import OpenClawTransport
from lib.transport.router import DEFAULT_ROUTING, ResolvedTransportTarget, TransportRouter

__all__ = [
    "DEFAULT_ROUTING",
    "DirectFeishuTransport",
    "MessageKind",
    "MessageTransport",
    "NoopTransport",
    "OpenClawTransport",
    "ResolvedTransportTarget",
    "TransportConfigurationError",
    "TransportMessage",
    "TransportRouter",
    "TransportSendResult",
    "build_transport",
    "build_transport_from_config",
    "normalize_transport_type",
]
