"""Factory for config-driven transport selection."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from lib.feishu import FeishuClient
from lib.transport.base import MessageTransport, TransportConfigurationError
from lib.transport.direct_feishu import DirectFeishuTransport
from lib.transport.noop import NoopTransport
from lib.transport.openclaw import OpenClawTransport
from lib.transport.router import DEFAULT_ROUTING, TransportRouter

TRANSPORT_TYPE_ALIASES = {
    "noop": "noop",
    "direct_feishu": "direct_feishu",
    "direct_feishu_api": "direct_feishu",
    "openclaw": "openclaw",
    "openclaw_feishu_plugin": "openclaw",
}


def normalize_transport_type(name: str | None) -> str:
    if not name:
        return "noop"
    try:
        return TRANSPORT_TYPE_ALIASES[name]
    except KeyError as e:
        raise TransportConfigurationError(f"Unknown transport type: {name!r}") from e


def build_transport(
    runtime_config: dict,
    env_getter: Callable[[str], str],
    *,
    conn: sqlite3.Connection | None = None,
) -> MessageTransport:
    transport_cfg = runtime_config.get("transport", {})
    feishu_cfg = runtime_config.get("feishu", {})
    openclaw_cfg = runtime_config.get("openclaw", {})

    transport_type = normalize_transport_type(transport_cfg.get("type"))
    router = TransportRouter(
        channel=transport_cfg.get("channel", "none"),
        routing=transport_cfg.get("routing") or DEFAULT_ROUTING,
        group_map=feishu_cfg.get("group_map") or {},
    )

    if transport_type == "noop":
        return NoopTransport(router)

    if transport_type == "direct_feishu":
        if conn is None:
            raise TransportConfigurationError(
                "DirectFeishuTransport requires a sqlite connection"
            )
        direct_cfg = transport_cfg.get("direct_feishu", {})
        client = FeishuClient(
            app_id=env_getter(direct_cfg.get("app_id_env", "FEISHU_APP_ID")),
            app_secret=env_getter(direct_cfg.get("app_secret_env", "FEISHU_APP_SECRET")),
            conn=conn,
            group_map=feishu_cfg.get("group_map"),
        )
        return DirectFeishuTransport(router, client)

    openclaw_transport_cfg = transport_cfg.get("openclaw", {})
    return OpenClawTransport(
        router,
        executable=openclaw_transport_cfg.get("command", "openclaw"),
        target_prefix=openclaw_transport_cfg.get("target_prefix", "chat"),
        timeout_seconds=int(openclaw_transport_cfg.get("timeout_seconds", 15)),
        workspace_root=openclaw_cfg.get("workspace_root"),
    )


def build_transport_from_config(
    config,
    *,
    conn: sqlite3.Connection | None = None,
) -> MessageTransport:
    return build_transport(config.runtime, config.env, conn=conn)
