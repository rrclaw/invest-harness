"""Config loader for invest_harness.

Design principles:
1. All JSON configs validated via schema on load -- fail fast, no dirty config.
2. python-dotenv loads .env; missing required vars raise explicit KeyError.
3. Module-level cache -- configs loaded once per HarnessConfig instance lifetime.
4. Explicit file-name-based loading -- no directory scanning or magic discovery.
5. Load order: markets -> tier_policies -> exchange_calendar -> alert_levels
               -> portfolio_snapshot -> watchlist  (independent, but explicit).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

from lib.schema_validator import validate, ValidationError


class ConfigValidationError(Exception):
    """Raised when a config file fails schema validation."""

    def __init__(self, config_name: str, original: ValidationError):
        self.config_name = config_name
        self.original = original
        super().__init__(
            f"Config '{config_name}' failed schema validation: {original.message}"
        )


# Map of config file names to their schema names (only those with schemas).
_SCHEMA_MAP: dict[str, str] = {
    "watchlist": "watchlist",
    "portfolio_snapshot": "portfolio_snapshot",
}

# The 6 config files, in explicit load order.
_CONFIG_FILES = [
    "markets",
    "tier_policies",
    "exchange_calendar",
    "alert_levels",
    "portfolio_snapshot",
    "watchlist",
]


class HarnessConfig:
    """Loads and validates all config files. One instance per process lifecycle.

    Usage:
        cfg = HarnessConfig(Path("config"))
        cfg.markets["a_stock"]["timezone"]
        cfg.env("TUSHARE_TOKEN")
    """

    def __init__(self, config_dir: str | Path):
        self._dir = Path(config_dir)
        self._cache: dict[str, dict] = {}
        self._env: dict[str, str] = {}

        # Load .env first -- fail if missing
        self._load_env()

        # Load and validate all config files eagerly at init time.
        # This ensures dirty config never enters memory.
        for name in _CONFIG_FILES:
            self._load_and_validate(name)

    # ------------------------------------------------------------------
    # .env loading
    # ------------------------------------------------------------------

    def _load_env(self) -> None:
        env_path = self._dir / ".env"
        if not env_path.exists():
            raise FileNotFoundError(
                f".env file not found at {env_path}. "
                f"Copy config/.env.example to config/.env and fill in values."
            )
        self._env = {
            k: v for k, v in dotenv_values(env_path).items() if v is not None
        }

    def env(self, key: str) -> str:
        """Get environment variable from .env. Raises KeyError if missing.

        No default parameter by design -- callers must handle missing vars
        explicitly. Silent fallbacks are forbidden.
        """
        if key not in self._env:
            raise KeyError(
                f"Required environment variable {key!r} not found in .env. "
                f"Add it to config/.env."
            )
        return self._env[key]

    # ------------------------------------------------------------------
    # JSON config loading with schema validation
    # ------------------------------------------------------------------

    def _load_and_validate(self, name: str) -> dict:
        """Load a JSON config by explicit name. Validate against schema if one exists."""
        if name in self._cache:
            return self._cache[name]

        path = self._dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = json.load(f)

        # Schema validation for configs that have a corresponding schema
        schema_name = _SCHEMA_MAP.get(name)
        if schema_name is not None:
            try:
                validate(data, schema_name)
            except ValidationError as e:
                raise ConfigValidationError(name, e) from e

        self._cache[name] = data
        return data

    # ------------------------------------------------------------------
    # Config properties (cached, explicit)
    # ------------------------------------------------------------------

    @property
    def markets(self) -> dict:
        return self._cache["markets"]

    @property
    def watchlist(self) -> dict:
        return self._cache["watchlist"]

    @property
    def tier_policies(self) -> dict:
        return self._cache["tier_policies"]

    @property
    def exchange_calendar(self) -> dict:
        return self._cache["exchange_calendar"]

    @property
    def alert_levels(self) -> dict:
        return self._cache["alert_levels"]

    @property
    def portfolio_snapshot(self) -> dict:
        return self._cache["portfolio_snapshot"]

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    def effective_polling_interval(self, market: str, tier: str) -> float:
        """Calculate effective polling interval in minutes for a market+tier."""
        base = self.markets[market]["polling_interval_minutes"]
        multiplier = self.tier_policies[tier]["polling_multiplier"]
        return base * multiplier

    def is_calendar_bypass(self, market: str) -> bool:
        """Check if a market bypasses exchange calendar checks."""
        return self.markets[market].get("calendar_bypass", False)

    def max_position_amount(self) -> float:
        """Max single position amount based on AUM and position limit."""
        ps = self.portfolio_snapshot
        return ps["total_aum"] * ps["max_single_position_pct"] / 100

    def tickers_for_market(self, market: str) -> list[str]:
        """Return list of ticker strings for a given market."""
        return [item["ticker"] for item in self.watchlist.get(market, [])]
