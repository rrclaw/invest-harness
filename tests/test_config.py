"""Tests for lib/config.py -- layered HarnessConfig loader.

Validates:
- Explicit file-name-based JSON loading (no magic scanning)
- Schema validation on load for watchlist + portfolio_snapshot
- config/default + config/local layering
- python-dotenv loading from config/local/.env
- Module-level singleton caching (one load per process)
- Computed helpers: effective_polling_interval, tickers_for_market, etc.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from lib.config import HarnessConfig, ConfigValidationError, load_json_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary layered config directory with valid config files."""
    d = tmp_path / "config"
    default_dir = d / "default"
    local_dir = d / "local"
    examples_dir = d / "examples"
    default_dir.mkdir(parents=True)
    local_dir.mkdir()
    examples_dir.mkdir()

    # markets.json
    (default_dir / "markets.json").write_text(json.dumps({
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
            "snapshots": {
                "initial_check": "09:45",
                "mid_session": ["11:00", "13:30"],
                "close_snapshot": "15:05"
            },
            "polling_interval_minutes": 3,
            "risk_triggers": {}
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
            "risk_triggers": {}
        }
    }))

    # watchlist.json (must pass watchlist schema)
    (default_dir / "watchlist.json").write_text(json.dumps({
        "a_stock": [
            {"ticker": "688256.SH", "company": "Cambricon", "tier": "core", "themes": ["AI_compute"]},
            {"ticker": "300750.SZ", "company": "CATL", "tier": "watch", "themes": ["EV_battery"]}
        ],
        "polymarket": [
            {"ticker": "us-election", "company": None, "tier": "watch", "themes": ["politics"]}
        ]
    }))

    # tier_policies.json
    (default_dir / "tier_policies.json").write_text(json.dumps({
        "core": {"polling_multiplier": 1.0, "hypothesis_mode": "always", "alert_on_anomaly": "L2", "snapshot_priority": "high"},
        "watch": {"polling_multiplier": 2.0, "hypothesis_mode": "catalyst_only", "alert_on_anomaly": "L3", "snapshot_priority": "medium"},
        "peripheral": {"polling_multiplier": 3.0, "hypothesis_mode": "human_request_only", "alert_on_anomaly": "L3_extreme_only", "snapshot_priority": "low"}
    }))

    # exchange_calendar.json
    (default_dir / "exchange_calendar.json").write_text(json.dumps({
        "a_stock": {"source": "tushare_trade_cal", "half_day_close": "11:30", "refresh_interval_days": 7},
        "polymarket": {"always_open": True, "calendar_bypass": True}
    }))

    # alert_levels.json
    (default_dir / "alert_levels.json").write_text(json.dumps({
        "L1": {"semantics": "System-level fault", "machine_action": "SUSPENDED"},
        "L2": {"semantics": "Business logic anomaly", "machine_action": "Block buy orders"},
        "L3": {"semantics": "Information flow", "machine_action": "No blocking action"}
    }))

    # portfolio_snapshot.json (must pass portfolio_snapshot schema)
    (default_dir / "portfolio_snapshot.json").write_text(json.dumps({
        "snapshot_time": "2026-03-26T07:00:00+08:00",
        "total_aum": 500000,
        "currency": "CNY",
        "cash_available": 200000,
        "per_market_exposure": {
            "a_stock": {"used": 180000, "ceiling": 250000},
            "polymarket": {"used": 0, "ceiling": 20000}
        },
        "max_single_position_pct": 10,
        "max_daily_loss_pct": 3
    }))

    # runtime.json
    (default_dir / "runtime.json").write_text(json.dumps({
        "llm": {"provider": "openai-compatible", "model": "default-model"},
        "persona": {"name": "Harness", "goal": "Default goal"},
        "knowledge": {"canonical_pipeline_root": "knowledge", "bridge_sources": [], "historical_inputs": [], "read_only_inputs": []},
        "markets": {"enabled": ["a_stock", "polymarket"], "adapters": {"a_stock": "tushare", "polymarket": "polymarket"}},
        "rules": {"default_rule_files": ["rules/universal.md"]},
        "feedback": {"feedback_system": "human_in_loop", "review_timezone": "Asia/Shanghai", "retrospective_time": "22:30", "milestone_mode": "manual"},
        "transport": {
            "type": "noop",
            "channel": "none",
            "routing": {
                "approval": {"target": "gabumon"},
                "broadcast": {"target": "gomamon"},
                "review": {"target": "gomamon"},
                "alert": {
                    "default_target": "gomamon",
                    "level_targets": {"L1": "kabuterimon", "L2": "gomamon", "L3": "gomamon"}
                }
            },
            "direct_feishu": {"app_id_env": "FEISHU_APP_ID", "app_secret_env": "FEISHU_APP_SECRET"},
            "openclaw": {"command": "openclaw", "target_prefix": "chat", "timeout_seconds": 15}
        },
        "openclaw": {"plugin_path": None, "workspace_root": None},
        "feishu": {"group_map": {}}
    }))

    # local .env file
    (local_dir / ".env").write_text(
        "TUSHARE_TOKEN=test_token_123\n"
        "POLYMARKET_API_URL=https://gamma-api.polymarket.com\n"
        "LLM_API_KEY=test_llm_key\n"
        "LLM_BASE_URL=https://api.example.com/v1\n"
        "LLM_MODEL=claude-opus-4-6\n"
        "FEISHU_APP_ID=test_app_id\n"
        "FEISHU_APP_SECRET=test_app_secret\n"
    )

    # examples/.env.example for error message parity
    (examples_dir / ".env.example").write_text("LLM_API_KEY=example\n")

    return d


# ---------------------------------------------------------------------------
# 1. Explicit file-name-based loading
# ---------------------------------------------------------------------------

class TestExplicitLoading:
    def test_load_markets(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert "a_stock" in cfg.markets
        assert "polymarket" in cfg.markets
        assert cfg.markets["a_stock"]["timezone"] == "Asia/Shanghai"

    def test_load_watchlist(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert "a_stock" in cfg.watchlist
        assert any(t["ticker"] == "688256.SH" for t in cfg.watchlist["a_stock"])

    def test_load_tier_policies(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.tier_policies["core"]["polling_multiplier"] == 1.0
        assert cfg.tier_policies["peripheral"]["polling_multiplier"] == 3.0

    def test_load_exchange_calendar(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.exchange_calendar["a_stock"]["source"] == "tushare_trade_cal"

    def test_load_alert_levels(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert "L1" in cfg.alert_levels
        assert "L2" in cfg.alert_levels
        assert "L3" in cfg.alert_levels

    def test_load_portfolio_snapshot(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.portfolio_snapshot["total_aum"] == 500000
        assert cfg.portfolio_snapshot["per_market_exposure"]["a_stock"]["ceiling"] == 250000

    def test_load_runtime(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.runtime["knowledge"]["canonical_pipeline_root"] == "knowledge"

    def test_missing_config_file_raises(self, config_dir):
        (config_dir / "default" / "markets.json").unlink()
        with pytest.raises(FileNotFoundError):
            HarnessConfig(config_dir)


# ---------------------------------------------------------------------------
# 2. Schema validation on load
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_invalid_watchlist_rejected(self, config_dir):
        """Watchlist with invalid tier should fail schema validation."""
        (config_dir / "default" / "watchlist.json").write_text(json.dumps({
            "a_stock": [
                {"ticker": "X", "tier": "INVALID_TIER", "themes": ["t"]}
            ]
        }))
        with pytest.raises(ConfigValidationError, match="watchlist"):
            HarnessConfig(config_dir)

    def test_invalid_portfolio_snapshot_rejected(self, config_dir):
        """Portfolio snapshot missing required field should fail."""
        (config_dir / "default" / "portfolio_snapshot.json").write_text(json.dumps({
            "total_aum": 500000
            # missing: snapshot_time, currency, cash_available, etc.
        }))
        with pytest.raises(ConfigValidationError, match="portfolio_snapshot"):
            HarnessConfig(config_dir)

    def test_valid_configs_pass_silently(self, config_dir):
        """Valid configs should load without errors."""
        cfg = HarnessConfig(config_dir)
        assert cfg.watchlist is not None
        assert cfg.portfolio_snapshot is not None


# ---------------------------------------------------------------------------
# 3. .env loading and missing-var errors
# ---------------------------------------------------------------------------

class TestEnvLoading:
    def test_env_vars_loaded(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.env("TUSHARE_TOKEN") == "test_token_123"
        assert cfg.env("LLM_API_KEY") == "test_llm_key"

    def test_missing_env_var_raises(self, config_dir):
        cfg = HarnessConfig(config_dir)
        with pytest.raises(KeyError, match="NONEXISTENT_VAR"):
            cfg.env("NONEXISTENT_VAR")

    def test_no_silent_fallback(self, config_dir):
        """env() must NOT accept a default parameter -- force explicit handling."""
        cfg = HarnessConfig(config_dir)
        # env() should raise, not return None or empty string
        with pytest.raises(KeyError):
            cfg.env("MISSING_KEY")

    def test_missing_env_file_raises(self, config_dir):
        (config_dir / "local" / ".env").unlink()
        with pytest.raises(FileNotFoundError, match=".env"):
            HarnessConfig(config_dir)


# ---------------------------------------------------------------------------
# 4. Caching / singleton within single instance
# ---------------------------------------------------------------------------

class TestCaching:
    def test_same_property_returns_cached_object(self, config_dir):
        cfg = HarnessConfig(config_dir)
        m1 = cfg.markets
        m2 = cfg.markets
        assert m1 is m2, "Second access should return exact same dict object"

    def test_all_properties_cached(self, config_dir):
        cfg = HarnessConfig(config_dir)
        # Access each property twice
        for prop in ["markets", "watchlist", "tier_policies", "exchange_calendar", "alert_levels", "portfolio_snapshot", "runtime"]:
            v1 = getattr(cfg, prop)
            v2 = getattr(cfg, prop)
            assert v1 is v2, f"{prop} should be cached"


class TestLayeredOverrides:
    def test_local_watchlist_overrides_default(self, config_dir):
        (config_dir / "local" / "watchlist.json").write_text(json.dumps({
            "a_stock": [
                {"ticker": "000001.SZ", "company": "Ping An", "tier": "watch", "themes": ["finance"]}
            ]
        }))
        cfg = HarnessConfig(config_dir)
        assert cfg.watchlist["a_stock"][0]["ticker"] == "000001.SZ"
        assert cfg.watchlist["polymarket"][0]["ticker"] == "us-election"

    def test_local_runtime_merges_nested_dicts(self, config_dir):
        (config_dir / "local" / "runtime.json").write_text(json.dumps({
            "transport": {"type": "direct_feishu", "channel": "feishu"},
            "openclaw": {"plugin_path": "/tmp/feishu"},
            "feishu": {"group_map": {"tailmon": "oc_123"}}
        }))
        cfg = HarnessConfig(config_dir)
        assert cfg.runtime["transport"]["type"] == "direct_feishu"
        assert cfg.runtime["feedback"]["review_timezone"] == "Asia/Shanghai"
        assert cfg.runtime["feishu"]["group_map"]["tailmon"] == "oc_123"

    def test_examples_are_not_loaded_at_runtime(self, config_dir):
        (config_dir / "examples" / "watchlist.json").write_text(json.dumps({
            "a_stock": [{"ticker": "SHOULD_NOT_LOAD", "tier": "watch", "themes": ["x"]}]
        }))
        cfg = HarnessConfig(config_dir)
        assert cfg.watchlist["a_stock"][0]["ticker"] == "688256.SH"

    def test_load_json_config_without_env_dependency(self, config_dir):
        (config_dir / "local" / ".env").unlink()
        exchange = load_json_config(config_dir, "exchange_calendar")
        assert exchange["a_stock"]["source"] == "tushare_trade_cal"


# ---------------------------------------------------------------------------
# 5. Computed helpers
# ---------------------------------------------------------------------------

class TestComputedHelpers:
    def test_effective_polling_interval_core(self, config_dir):
        cfg = HarnessConfig(config_dir)
        # a_stock base=3, core multiplier=1.0
        assert cfg.effective_polling_interval("a_stock", "core") == 3.0

    def test_effective_polling_interval_watch(self, config_dir):
        cfg = HarnessConfig(config_dir)
        # a_stock base=3, watch multiplier=2.0
        assert cfg.effective_polling_interval("a_stock", "watch") == 6.0

    def test_effective_polling_interval_peripheral(self, config_dir):
        cfg = HarnessConfig(config_dir)
        # a_stock base=3, peripheral multiplier=3.0
        assert cfg.effective_polling_interval("a_stock", "peripheral") == 9.0

    def test_is_calendar_bypass_polymarket(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.is_calendar_bypass("polymarket") is True

    def test_is_calendar_bypass_a_stock(self, config_dir):
        cfg = HarnessConfig(config_dir)
        assert cfg.is_calendar_bypass("a_stock") is False

    def test_max_position_amount(self, config_dir):
        cfg = HarnessConfig(config_dir)
        # max_single_position_pct=10, total_aum=500000 -> 50000
        assert cfg.max_position_amount() == 50000.0

    def test_tickers_for_market(self, config_dir):
        cfg = HarnessConfig(config_dir)
        tickers = cfg.tickers_for_market("a_stock")
        assert "688256.SH" in tickers
        assert "300750.SZ" in tickers

    def test_tickers_for_market_empty(self, config_dir):
        cfg = HarnessConfig(config_dir)
        tickers = cfg.tickers_for_market("hk_stock")
        assert tickers == []

    def test_unknown_market_raises(self, config_dir):
        cfg = HarnessConfig(config_dir)
        with pytest.raises(KeyError):
            cfg.effective_polling_interval("crypto", "core")


# ---------------------------------------------------------------------------
# 6. Real project config validation (integration test)
# ---------------------------------------------------------------------------

class TestRealProjectConfig:
    """Load the actual project config files to verify they pass validation."""

    @pytest.fixture(autouse=True)
    def _ensure_env(self, project_root):
        """Create config/local/.env from config/examples/.env.example if missing."""
        local_dir = project_root / "config" / "local"
        env_path = local_dir / ".env"
        example_path = project_root / "config" / "examples" / ".env.example"
        created = False
        if not env_path.exists() and example_path.exists():
            import shutil
            local_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(example_path, env_path)
            created = True
        yield
        if created:
            env_path.unlink(missing_ok=True)

    def test_real_config_loads(self, project_root):
        cfg = HarnessConfig(project_root / "config")
        assert cfg.markets is not None
        assert cfg.watchlist is not None
        assert cfg.tier_policies is not None
        assert cfg.portfolio_snapshot is not None

    def test_real_watchlist_passes_schema(self, project_root):
        cfg = HarnessConfig(project_root / "config")
        assert "a_stock" in cfg.watchlist
        assert isinstance(cfg.tickers_for_market("a_stock"), list)

    def test_real_portfolio_passes_schema(self, project_root):
        cfg = HarnessConfig(project_root / "config")
        assert cfg.portfolio_snapshot["total_aum"] >= 0

    def test_real_runtime_default_is_portable(self, project_root):
        cfg = HarnessConfig(project_root / "config")
        assert cfg.runtime["knowledge"]["canonical_pipeline_root"] == "knowledge"
