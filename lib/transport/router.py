"""Config-driven routing for transport messages."""

from __future__ import annotations

from dataclasses import dataclass

from lib.transport.messages import MessageKind, TransportMessage


DEFAULT_ROUTING = {
    "approval": {"target": "gabumon"},
    "broadcast": {"target": "gomamon"},
    "review": {"target": "gomamon"},
    "alert": {
        "default_target": "gomamon",
        "level_targets": {
            "L1": "kabuterimon",
            "L2": "gomamon",
            "L3": "gomamon",
        },
    },
}


@dataclass(frozen=True)
class ResolvedTransportTarget:
    channel: str
    target_alias: str
    target_id: str | None


class TransportRouter:
    """Resolve message kinds into configured channel targets."""

    def __init__(
        self,
        *,
        channel: str,
        routing: dict | None = None,
        group_map: dict[str, str] | None = None,
    ):
        self._channel = channel
        self._routing = DEFAULT_ROUTING if routing is None else routing
        self._group_map = group_map or {}

    def resolve(self, message: TransportMessage) -> ResolvedTransportTarget:
        alias = message.target or self._resolve_alias(message)
        return ResolvedTransportTarget(
            channel=self._channel,
            target_alias=alias,
            target_id=self._group_map.get(alias),
        )

    def _resolve_alias(self, message: TransportMessage) -> str:
        if message.kind == MessageKind.ALERT:
            alert_cfg = self._routing.get("alert", {})
            level_targets = alert_cfg.get("level_targets", {})
            if message.level and message.level in level_targets:
                return level_targets[message.level]
            default_target = alert_cfg.get("default_target")
            if default_target:
                return default_target
            raise ValueError("Alert transport route is missing default_target")

        entry = self._routing.get(message.kind.value, {})
        target = entry.get("target")
        if not target:
            raise ValueError(f"Transport route missing target for {message.kind.value}")
        return target
