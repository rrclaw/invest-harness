import json
from pathlib import Path

import pytest

from scripts.init_local_config import _resolve_config_root, initialize_local_config


def _write_examples(config_root: Path) -> None:
    examples = config_root / "examples"
    examples.mkdir(parents=True)
    (examples / ".env.example").write_text(
        "LLM_API_KEY=your_key\n"
        "LLM_BASE_URL=https://api.example.com/v1\n"
        "LLM_MODEL=your_model\n"
    )
    (examples / "local.runtime.example.json").write_text(
        json.dumps(
            {
                "llm": {"provider": "openai-compatible", "model": "your_model"},
                "persona": {"name": "Example", "goal": "Example goal"},
                "knowledge": {
                    "canonical_pipeline_root": "knowledge",
                    "bridge_sources": [],
                    "historical_inputs": [],
                    "read_only_inputs": [],
                },
                "markets": {
                    "enabled": ["a_stock"],
                    "adapters": {"a_stock": "tushare"},
                },
                "rules": {"default_rule_files": ["rules/universal.md"]},
                "feedback": {
                    "feedback_system": "human_in_loop",
                    "review_timezone": "Asia/Shanghai",
                    "retrospective_time": "22:30",
                    "milestone_mode": "manual",
                },
                "transport": {
                    "type": "noop",
                    "channel": "none",
                    "routing": {
                        "approval": {"target": "gabumon"},
                        "broadcast": {"target": "gomamon"},
                        "review": {"target": "gomamon"},
                        "alert": {
                            "default_target": "gomamon",
                            "level_targets": {"L1": "kabuterimon", "L2": "gomamon", "L3": "gomamon"},
                        },
                    },
                    "direct_feishu": {"app_id_env": "FEISHU_APP_ID", "app_secret_env": "FEISHU_APP_SECRET"},
                    "openclaw": {"command": "openclaw", "target_prefix": "chat", "timeout_seconds": 15},
                },
                "openclaw": {"plugin_path": None, "workspace_root": None},
                "feishu": {"group_map": {}},
            }
        )
    )
    (examples / "local.watchlist.example.json").write_text(
        json.dumps(
            {
                "a_stock": [],
                "hk_stock": [],
                "us_stock": [],
                "polymarket": [],
            }
        )
    )
    (examples / "local.portfolio_snapshot.example.json").write_text(
        json.dumps(
            {
                "snapshot_time": "2026-01-01T00:00:00+08:00",
                "total_aum": 0,
                "currency": "USD",
                "cash_available": 0,
                "per_market_exposure": {
                    "a_stock": {"used": 0, "ceiling": 0},
                    "hk_stock": {"used": 0, "ceiling": 0},
                    "us_stock": {"used": 0, "ceiling": 0},
                    "polymarket": {"used": 0, "ceiling": 0},
                },
                "max_single_position_pct": 0,
                "max_daily_loss_pct": 0,
            }
        )
    )


def test_initialize_local_config_writes_templates(tmp_path):
    config_root = tmp_path / "config"
    _write_examples(config_root)

    result = initialize_local_config(
        config_root,
        provider="anthropic",
        model="claude-sonnet-4-6",
        persona_name="Tailmon",
        persona_goal="Bridge Feishu to Harness",
        bridge_sources=["/tmp/upstream"],
        historical_inputs=["/tmp/history"],
        enabled_markets=["a_stock", "polymarket"],
        adapters={"a_stock": "tushare"},
        rule_files=["rules/universal.md", "rules/a_stock.md"],
        feedback_system="feishu_group",
        review_timezone="Asia/Shanghai",
        retrospective_time="23:00",
        milestone_mode="weekly",
        transport_type="openclaw",
        channel="feishu",
        openclaw_plugin_path="/tmp/plugin",
        openclaw_workspace_root="/tmp/workspace",
        feishu_groups={"tailmon": "oc_123"},
        env_overrides={"LLM_API_KEY": "placeholder", "LLM_MODEL": "claude-sonnet-4-6"},
    )

    assert result["runtime.json"] == "written"
    runtime = json.loads((config_root / "local" / "runtime.json").read_text())
    assert runtime["llm"]["provider"] == "anthropic"
    assert runtime["persona"]["name"] == "Tailmon"
    assert runtime["transport"]["type"] == "openclaw"
    assert runtime["feishu"]["group_map"]["tailmon"] == "oc_123"
    env_text = (config_root / "local" / ".env").read_text()
    assert "LLM_API_KEY=placeholder" in env_text


def test_initialize_local_config_preserves_existing_files_without_force(tmp_path):
    config_root = tmp_path / "config"
    _write_examples(config_root)
    local_dir = config_root / "local"
    local_dir.mkdir()
    (local_dir / "runtime.json").write_text('{"persona": {"name": "keep"}}')

    result = initialize_local_config(config_root)

    assert result["runtime.json"] == "skipped"
    assert json.loads((local_dir / "runtime.json").read_text())["persona"]["name"] == "keep"


def test_resolve_config_root_accepts_project_root(tmp_path):
    project_root = tmp_path / "repo"
    assert _resolve_config_root(project_root=project_root) == project_root / "config"


def test_resolve_config_root_rejects_both_project_and_config_root(tmp_path):
    with pytest.raises(ValueError, match="either project_root or config_root"):
        _resolve_config_root(
            project_root=tmp_path / "repo",
            config_root=tmp_path / "repo" / "config",
        )
