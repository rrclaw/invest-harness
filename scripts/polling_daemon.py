"""Lightweight intraday polling daemon.

ABSOLUTELY FORBIDS LLM participation. Pure Python script:
every N minutes, adapter fetches data -> compare against thresholds ->
only generates snapshot and wakes downstream when threshold breached.

Tier-aware: effective_interval = base_interval * tier.polling_multiplier
"""

import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

CONSECUTIVE_DEGRADED = 3
CONSECUTIVE_FAILING = 6
CONSECUTIVE_DEAD = 10

logger = logging.getLogger("polling_daemon")


class HealthTracker:
    """Tracks consecutive failures for soft-failure escalation."""

    def __init__(self):
        self._consecutive_failures = 0
        self._last_heartbeat = datetime.now(timezone.utc).isoformat()

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._last_heartbeat = datetime.now(timezone.utc).isoformat()

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def status(self) -> dict:
        if self._consecutive_failures >= CONSECUTIVE_DEAD:
            adapter_status = "dead"
            alert_level = "L1"
        elif self._consecutive_failures >= CONSECUTIVE_FAILING:
            adapter_status = "failing"
            alert_level = "L2"
        elif self._consecutive_failures >= CONSECUTIVE_DEGRADED:
            adapter_status = "degraded"
            alert_level = None
        else:
            adapter_status = "healthy"
            alert_level = None

        result = {
            "consecutive_failures": self._consecutive_failures,
            "last_heartbeat": self._last_heartbeat,
            "circuit_broken": adapter_status == "dead",
            "adapter_status": adapter_status,
        }
        if alert_level:
            result["alert_level"] = alert_level
        return result


class PollingDaemon:
    """Main polling loop. Instantiated per market."""

    def __init__(self, market, config, adapter, alert_mgr, state_machine, notifier=None):
        self._market = market
        self._config = config
        self._adapter = adapter
        self._alert_mgr = alert_mgr
        self._sm = state_machine
        self._health = HealthTracker()
        self._running = False
        self._notifier = notifier

    def _effective_interval(self, base_minutes: float, multiplier: float) -> float:
        return base_minutes * multiplier

    def _check_risk_triggers(self, triggers, ticker, current_change_pct, volume_ratio):
        events = []
        if "index_rapid_drop" in triggers:
            t = triggers["index_rapid_drop"]
            if current_change_pct <= t["threshold_pct"]:
                events.append({
                    "event_type": "index_rapid_drop",
                    "ticker": ticker,
                    "observed_value": f"Change {current_change_pct}% <= {t['threshold_pct']}%",
                    "alert_level": "L2",
                })
        if "stock_rapid_drop" in triggers:
            t = triggers["stock_rapid_drop"]
            if current_change_pct <= t["threshold_pct"] and volume_ratio >= t.get("volume_multiplier", 1.0):
                events.append({
                    "event_type": "stock_rapid_drop",
                    "ticker": ticker,
                    "observed_value": f"Change {current_change_pct}% with volume {volume_ratio}x",
                    "alert_level": "L2",
                })
        if "odds_slope" in triggers:
            t = triggers["odds_slope"]
            if abs(current_change_pct) >= t["threshold_pct"]:
                events.append({
                    "event_type": "odds_slope",
                    "ticker": ticker,
                    "observed_value": f"Slope {current_change_pct}% >= {t['threshold_pct']}%",
                    "alert_level": "L2",
                })
        return events

    def _emit_alert(
        self,
        *,
        level: str,
        message: str,
        source: str,
        hypothesis_ref: str | None = None,
    ) -> dict:
        alert = self._alert_mgr.fire(
            level=level,
            market=self._market,
            message=message,
            source=source,
            hypothesis_ref=hypothesis_ref,
        )
        if self._notifier is not None:
            self._notifier.send_alert(alert)
        return alert

    def handle_health_status(self, status: dict) -> dict | None:
        """Persist and notify health-derived alerts when escalation is reached."""
        level = status.get("alert_level")
        if not level:
            return None
        message = (
            f"{self._market} adapter status={status['adapter_status']} "
            f"failures={status['consecutive_failures']}"
        )
        return self._emit_alert(level=level, message=message, source="polling_daemon")

    def emit_risk_trigger_alerts(self, events: list[dict]) -> list[dict]:
        """Persist and notify risk-trigger events."""
        alerts = []
        for event in events:
            message = (
                f"{event['event_type']} detected for {event['ticker']}: "
                f"{event['observed_value']}"
            )
            alerts.append(
                self._emit_alert(
                    level=event["alert_level"],
                    message=message,
                    source="polling_daemon",
                )
            )
        return alerts

    def stop(self) -> None:
        self._running = False
