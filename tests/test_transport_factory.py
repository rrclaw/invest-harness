from unittest.mock import patch

import pytest

from lib.db import get_connection, init_db
from lib.transport import (
    DirectFeishuTransport,
    NoopTransport,
    OpenClawTransport,
    TransportConfigurationError,
    build_transport,
    normalize_transport_type,
)


def _runtime(transport_type: str) -> dict:
    return {
        "transport": {
            "type": transport_type,
            "channel": "feishu",
            "routing": {
                "approval": {"target": "gabumon"},
                "broadcast": {"target": "gomamon"},
                "review": {"target": "gomamon"},
                "alert": {
                    "default_target": "gomamon",
                    "level_targets": {"L1": "kabuterimon", "L2": "gomamon", "L3": "gomamon"},
                },
            },
            "direct_feishu": {
                "app_id_env": "FEISHU_APP_ID",
                "app_secret_env": "FEISHU_APP_SECRET",
            },
            "openclaw": {"command": "openclaw", "target_prefix": "chat", "timeout_seconds": 15},
        },
        "feishu": {
            "group_map": {
                "gabumon": "oc_gabu",
                "gomamon": "oc_goma",
                "kabuterimon": "oc_kabu",
            }
        },
        "openclaw": {"workspace_root": "/tmp/workspace"},
    }


def test_normalize_transport_type_supports_legacy_aliases():
    assert normalize_transport_type("direct_feishu_api") == "direct_feishu"
    assert normalize_transport_type("openclaw_feishu_plugin") == "openclaw"


def test_build_noop_transport():
    transport = build_transport(_runtime("noop"), lambda key: f"env:{key}")
    assert isinstance(transport, NoopTransport)


def test_build_direct_feishu_requires_conn():
    with pytest.raises(TransportConfigurationError, match="sqlite connection"):
        build_transport(_runtime("direct_feishu"), lambda key: f"env:{key}")


def test_build_direct_feishu_transport(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    transport = build_transport(_runtime("direct_feishu"), lambda key: f"env:{key}", conn=conn)
    assert isinstance(transport, DirectFeishuTransport)


def test_build_openclaw_transport():
    transport = build_transport(_runtime("openclaw"), lambda key: f"env:{key}")
    assert isinstance(transport, OpenClawTransport)


def test_build_transport_rejects_unknown_type():
    with pytest.raises(TransportConfigurationError, match="Unknown transport type"):
        build_transport(_runtime("mystery"), lambda key: f"env:{key}")
