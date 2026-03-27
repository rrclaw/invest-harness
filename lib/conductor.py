"""Conductor: single state-machine driver.

Single-Writer Principle: Only Conductor writes to state_machine and task_log.
Workers deposit results in task_results; Conductor consumes and reconciles.

Conductor's Git commit permission is strictly limited to executing instructions
that have passed through the approval flow (FC-1).
"""

import json
import sqlite3
from datetime import datetime, timezone

from lib.state_machine import StateMachine


class Conductor:
    """Main orchestration brain. Drives state machine transitions."""

    def __init__(self, conn: sqlite3.Connection, state_machine: StateMachine):
        self._conn = conn
        self._sm = state_machine

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def consume_pending_results(self) -> list[dict]:
        """Read and consume all pending task results.

        Returns list of result dicts. Marks each as consumed.
        """
        rows = self._conn.execute(
            "SELECT * FROM task_results WHERE consumed=0 ORDER BY created_at"
        ).fetchall()

        results = []
        for row in rows:
            result = dict(row)
            result["result_payload"] = json.loads(result["result_payload"])
            results.append(result)
            self._conn.execute(
                "UPDATE task_results SET consumed=1 WHERE result_id=?",
                (result["result_id"],),
            )
        self._conn.commit()
        return results

    def register_task(
        self, task_type: str, market: str, exchange_date: str
    ) -> str:
        """Register a task in task_log. Idempotent via UNIQUE key."""
        key = f"{task_type}_{exchange_date}_{market}"
        try:
            self._conn.execute(
                "INSERT INTO task_log (idempotency_key, task_type, market, exchange_date, status, started_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?)",
                (key, task_type, market, exchange_date, self._now()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already registered, idempotent
        return key

    def update_task_status(
        self,
        idempotency_key: str,
        status: str,
        error_detail: str | None = None,
    ) -> None:
        """Update task status."""
        if status in ("done", "error"):
            self._conn.execute(
                "UPDATE task_log SET status=?, finished_at=?, error_detail=? "
                "WHERE idempotency_key=?",
                (status, self._now(), error_detail, idempotency_key),
            )
        else:
            self._conn.execute(
                "UPDATE task_log SET status=? WHERE idempotency_key=?",
                (status, idempotency_key),
            )
        self._conn.commit()

    def should_skip(self, market: str, calendar_bypass: bool = False) -> bool:
        """Check if market should be skipped (non-trading day, etc.)."""
        if calendar_bypass:
            return False
        # Full calendar checking delegated to cron_dispatch.sh
        # Conductor just checks if market is in a runnable state
        return False

    def is_market_suspended(self, market: str) -> bool:
        """Check if market is in SUSPENDED state."""
        try:
            state = self._sm.get_state(market)
            return state["current_state"] == "SUSPENDED"
        except KeyError:
            return False
