"""OpenClaw CLI transport.

This transport only shells out to `openclaw message send`. It does not manage
plugin installation, gateway repair, or local Feishu wiring.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.transport.base import MessageTransport, TransportSendResult
from lib.transport.messages import TransportMessage
from lib.transport.router import ResolvedTransportTarget


class OpenClawTransport(MessageTransport):
    transport_name = "openclaw"

    def __init__(
        self,
        router,
        *,
        executable: str = "openclaw",
        target_prefix: str = "chat",
        timeout_seconds: int = 15,
        workspace_root: str | None = None,
    ):
        super().__init__(router)
        self._executable = executable
        self._target_prefix = target_prefix
        self._timeout_seconds = timeout_seconds
        self._workspace_root = workspace_root

    def _send_resolved(
        self,
        message: TransportMessage,
        resolved: ResolvedTransportTarget,
        payload_text: str,
    ) -> TransportSendResult:
        if not resolved.target_id:
            return TransportSendResult(
                delivered=False,
                transport=self.transport_name,
                message_kind=message.kind.value,
                channel=resolved.channel,
                target_alias=resolved.target_alias,
                target_id=resolved.target_id,
                payload_text=payload_text,
                reason="unconfigured_group",
            )

        command = [
            self._executable,
            "message",
            "send",
            "--channel",
            resolved.channel,
            "--target",
            f"{self._target_prefix}:{resolved.target_id}",
            "--message",
            payload_text,
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                cwd=str(Path(self._workspace_root)) if self._workspace_root else None,
                check=False,
            )
        except FileNotFoundError as e:
            return TransportSendResult(
                delivered=False,
                transport=self.transport_name,
                message_kind=message.kind.value,
                channel=resolved.channel,
                target_alias=resolved.target_alias,
                target_id=resolved.target_id,
                payload_text=payload_text,
                reason=str(e),
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return TransportSendResult(
            delivered=completed.returncode == 0,
            transport=self.transport_name,
            message_kind=message.kind.value,
            channel=resolved.channel,
            target_alias=resolved.target_alias,
            target_id=resolved.target_id,
            payload_text=payload_text,
            reason=None if completed.returncode == 0 else (stderr or stdout or "openclaw_send_failed"),
            external_id=stdout or None,
        )
