import json
from pathlib import Path

from scripts.harness_cli import run_cli


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _bootstrap_project(root: Path) -> None:
    for sub in [
        "config/default",
        "config/local",
        "hypotheses",
        "reviews",
        "rules",
        "knowledge/raw",
        "knowledge/normalized",
        "knowledge/curated",
        "chroma_storage",
    ]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    _write(
        root / "config/local/.env",
        "\n".join(
            [
                "TUSHARE_TOKEN=test_token",
                "POLYMARKET_API_URL=https://gamma-api.polymarket.com",
                "LLM_API_KEY=test_llm_key",
                "LLM_BASE_URL=https://api.example.com/v1",
                "LLM_MODEL=test_model",
                "FEISHU_APP_ID=test_app_id",
                "FEISHU_APP_SECRET=test_secret",
            ]
        )
        + "\n",
    )

    _write_json(
        root / "config/default/markets.json",
        {
            "a_stock": {
                "timezone": "Asia/Shanghai",
                "open": "09:30",
                "close": "15:00",
                "hypothesis_lock": "08:45",
                "pre_market_cron": "07:30",
                "post_market_cron": "15:30",
                "trading_days": "mon-fri",
                "holidays_source": "tushare_trade_cal",
                "dst": False,
                "snapshots": {"initial_check": "09:45", "mid_session": ["11:00"], "close_snapshot": "15:05"},
                "polling_interval_minutes": 3,
                "risk_triggers": {},
            },
            "polymarket": {
                "timezone": "UTC",
                "always_open": True,
                "hypothesis_lock": None,
                "review_cron": "22:00",
                "trading_days": "all",
                "calendar_bypass": True,
                "snapshots": None,
                "polling_interval_minutes": 5,
                "risk_triggers": {},
            },
        },
    )
    _write_json(
        root / "config/default/watchlist.json",
        {"a_stock": [], "hk_stock": [], "us_stock": [], "polymarket": []},
    )
    _write_json(
        root / "config/default/tier_policies.json",
        {
            "core": {"polling_multiplier": 1.0, "hypothesis_mode": "always", "alert_on_anomaly": "L2", "snapshot_priority": "high"},
            "watch": {"polling_multiplier": 2.0, "hypothesis_mode": "catalyst_only", "alert_on_anomaly": "L3", "snapshot_priority": "medium"},
            "peripheral": {"polling_multiplier": 3.0, "hypothesis_mode": "human_request_only", "alert_on_anomaly": "L3_extreme_only", "snapshot_priority": "low"},
        },
    )
    _write_json(
        root / "config/default/exchange_calendar.json",
        {
            "a_stock": {"source": "tushare_trade_cal"},
            "polymarket": {"always_open": True, "calendar_bypass": True},
        },
    )
    _write_json(
        root / "config/default/alert_levels.json",
        {
            "L1": {"semantics": "System-level fault", "machine_action": "SUSPENDED"},
            "L2": {"semantics": "Business logic anomaly", "machine_action": "Block buy orders"},
            "L3": {"semantics": "Information flow", "machine_action": "No blocking action"},
        },
    )
    _write_json(
        root / "config/default/portfolio_snapshot.json",
        {
            "snapshot_time": "2026-01-01T00:00:00+00:00",
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
        },
    )
    _write_json(
        root / "config/default/runtime.json",
        {
            "llm": {"provider": "openai-compatible", "model": "test_model", "api_key_env": "LLM_API_KEY", "base_url_env": "LLM_BASE_URL"},
            "persona": {"name": "Test Harness", "goal": "Test goal"},
            "knowledge": {"canonical_pipeline_root": "knowledge", "bridge_sources": [], "historical_inputs": [], "read_only_inputs": []},
            "markets": {"enabled": ["a_stock", "polymarket"], "adapters": {"a_stock": "tushare", "polymarket": "polymarket"}},
            "rules": {"default_rule_files": ["rules/universal.md", "rules/a_stock.md"]},
            "feedback": {"feedback_system": "human_in_loop", "review_timezone": "Asia/Shanghai", "retrospective_time": "22:30", "milestone_mode": "manual"},
            "transport": {
                "type": "noop",
                "channel": "feishu",
                "routing": {
                    "approval": {"target": "gabumon"},
                    "broadcast": {"target": "gomamon"},
                    "review": {"target": "gomamon"},
                    "alert": {"default_target": "gomamon", "level_targets": {"L1": "kabuterimon", "L2": "gomamon", "L3": "gomamon"}},
                },
                "direct_feishu": {"app_id_env": "FEISHU_APP_ID", "app_secret_env": "FEISHU_APP_SECRET"},
                "openclaw": {"command": "openclaw", "target_prefix": "chat", "timeout_seconds": 15},
            },
            "openclaw": {"plugin_path": None, "workspace_root": None},
            "feishu": {"group_map": {"gabumon": "oc_gabu", "gomamon": "oc_goma", "kabuterimon": "oc_kabu"}},
        },
    )

    _write(root / "rules/universal.md", "")
    _write(
        root / "rules/a_stock.md",
        """---
rule_id: R-A-001
title: Rule title
market: a_stock
status: active
priority: high
scope:
  themes: ["ai"]
  tickers: []
  conditions: []
not_applicable: []
created_at: 2026-03-01
evidence_refs: []
last_reviewed: 2026-03-25
last_hit_count: 1
deprecated_reason: null
---

Body
""",
    )


def _sample_hypothesis() -> dict:
    return {
        "hypothesis_id": "h_20260327_a_001",
        "market": "a_stock",
        "ticker": "688256.SH",
        "company": "Cambricon",
        "theme": ["AI_compute"],
        "created_at": "2026-03-27T07:45:00+08:00",
        "locked_at": None,
        "approved_by": None,
        "trigger_event": "Q4 earnings beat",
        "core_evidence": [{"fact_ref": "f_001", "summary": "Revenue up"}],
        "invalidation_conditions": ["Volume < 5%"],
        "observation_window": {"start": "2026-03-27T09:30:00+08:00", "end": "2026-03-27T15:00:00+08:00"},
        "probability": 0.7,
        "odds": "2:1",
        "win_rate_estimate": 0.65,
        "scenario": {
            "bull": {"description": "Gap up 5%+", "target": "+8%"},
            "base": {"description": "Gap up 2-5%", "target": "+3%"},
            "bear": {"description": "Flat", "target": "0%"},
        },
        "review_rubric": {
            "direction": {"metric": "Close direction", "bull": "up"},
            "magnitude": {"metric": "Close change %", "threshold": 2.0},
            "time_window": {"metric": "Key move timing", "expected": "09:30-10:30"},
            "invalidation_triggered": {"metric": "Boolean"},
        },
        "action_plan": {"gap_up": {"position_size": "50%"}},
        "status": "draft",
        "amend_log": [],
        "_audit": {
            "model_version": "claude-sonnet-4-6",
            "prompt_hash": "sha256:abc",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "generated_at": "2026-03-27T07:35:00+08:00",
            "idempotency_key": "key1",
        },
    }


def test_hypothesis_command_saves_and_notifies(tmp_path):
    _bootstrap_project(tmp_path)
    hypothesis_path = tmp_path / "input_hypothesis.json"
    _write_json(hypothesis_path, _sample_hypothesis())

    result = run_cli(
        ["hypothesis", "--file", str(hypothesis_path), "--date", "2026-03-27"],
        project_root=tmp_path,
    )

    assert result["saved"] is True
    assert result["transport"]["message_kind"] == "approval"
    assert (tmp_path / "hypotheses/2026-03-27/a_stock.json").exists()


def test_lock_deadline_check_emits_alert(tmp_path):
    _bootstrap_project(tmp_path)
    hypothesis_path = tmp_path / "input_hypothesis.json"
    _write_json(hypothesis_path, _sample_hypothesis())
    run_cli(
        ["hypothesis", "--file", str(hypothesis_path), "--date", "2026-03-27", "--no-notify"],
        project_root=tmp_path,
    )

    result = run_cli(
        ["lock", "--date", "2026-03-27", "--market", "a_stock", "--deadline-check"],
        project_root=tmp_path,
    )

    assert result["action"] == "unconfirmed"
    assert result["transport"]["message_kind"] == "alert"


def test_review_command_writes_markdown_and_notifies(tmp_path):
    _bootstrap_project(tmp_path)
    review_dir = tmp_path / "reviews/2026-03-27"
    review_dir.mkdir(parents=True)
    _write_json(
        review_dir / "post_market_a_stock.json",
        {
            "hypothesis_ref": "h_001",
            "market": "a_stock",
            "ticker": "688256.SH",
            "stat_eligible": True,
            "scenario_matched": "bull",
            "dimensions": {"cause": {"thesis_cause_match": "aligned", "market_cause": "Policy"}},
            "invalidation_review": {"any_triggered": False, "invalidation_type": None, "details": []},
            "verdict": "hit",
            "score": {"earned": 4, "possible": 4},
        },
    )

    result = run_cli(["review", "--date", "2026-03-27"], project_root=tmp_path)

    assert result["transport"]["message_kind"] == "review"
    assert (tmp_path / "reviews/2026-03-27/nightly_review.md").exists()


def test_rule_audit_and_backup_commands_broadcast(tmp_path):
    _bootstrap_project(tmp_path)

    audit = run_cli(["rule_audit", "--date", "2026-03-27"], project_root=tmp_path)
    backup = run_cli(["backup", "--date-override", "20260327"], project_root=tmp_path)

    assert audit["transport"]["message_kind"] == "broadcast"
    assert backup["transport"]["message_kind"] == "broadcast"
