"""Per-market state machine for invest_harness.

8 states: IDLE, HYPOTHESIS_DRAFT, LOCKED, MONITORING, VERIFYING, REVIEWED, ERROR, SUSPENDED.
Polymarket uses a stripped subset without MONITORING/VERIFYING.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

VALID_STATES = {
    "IDLE",
    "HYPOTHESIS_DRAFT",
    "LOCKED",
    "MONITORING",
    "VERIFYING",
    "REVIEWED",
    "ERROR",
    "SUSPENDED",
}

POLYMARKET_STATES = {
    "IDLE",
    "HYPOTHESIS_DRAFT",
    "LOCKED",
    "REVIEWED",
    "ERROR",
    "SUSPENDED",
}

# Allowed transitions: from_state -> {to_states}
# ERROR and SUSPENDED can be reached from any state (handled separately)
_TRANSITIONS: dict[str, set[str]] = {
    "IDLE": {"HYPOTHESIS_DRAFT"},
    "HYPOTHESIS_DRAFT": {"LOCKED"},
    "LOCKED": {"MONITORING"},
    "MONITORING": {"VERIFYING"},
    "VERIFYING": {"REVIEWED"},
    "REVIEWED": {"IDLE"},
}

_POLYMARKET_TRANSITIONS: dict[str, set[str]] = {
    "IDLE": {"HYPOTHESIS_DRAFT"},
    "HYPOTHESIS_DRAFT": {"LOCKED"},
    "LOCKED": {"REVIEWED"},
    "REVIEWED": {"IDLE"},
}


class InvalidTransition(Exception):
    pass


class StateMachine:
    """Manages per-market state machine persisted in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_polymarket(self, market: str) -> bool:
        return market == "polymarket"

    def _get_transitions(self, market: str) -> dict[str, set[str]]:
        if self._is_polymarket(market):
            return _POLYMARKET_TRANSITIONS
        return _TRANSITIONS

    def _get_valid_states(self, market: str) -> set[str]:
        if self._is_polymarket(market):
            return POLYMARKET_STATES
        return VALID_STATES

    def initialize(self, market: str, exchange_date: str) -> None:
        """Initialize a market to IDLE state. Idempotent."""
        self._conn.execute(
            "INSERT OR REPLACE INTO state_machine "
            "(market, current_state, previous_state, exchange_date, updated_at, error_detail, retry_count) "
            "VALUES (?, 'IDLE', NULL, ?, ?, NULL, 0)",
            (market, exchange_date, self._now()),
        )
        self._conn.commit()

    def get_state(self, market: str) -> dict:
        """Get current state for a market. Raises KeyError if not initialized."""
        row = self._conn.execute(
            "SELECT * FROM state_machine WHERE market=?", (market,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Market {market!r} not initialized")
        return dict(row)

    def transition(
        self, market: str, to_state: str, error_detail: str | None = None
    ) -> None:
        """Transition market to new state. Validates transition legality."""
        current = self.get_state(market)
        from_state = current["current_state"]
        valid_states = self._get_valid_states(market)

        if to_state not in valid_states:
            raise InvalidTransition(
                f"{market}: state {to_state!r} not valid for this market"
            )

        # ERROR can be reached from any state
        if to_state == "ERROR":
            retry = current["retry_count"] + 1
            self._conn.execute(
                "UPDATE state_machine SET current_state=?, previous_state=?, "
                "updated_at=?, error_detail=?, retry_count=? WHERE market=?",
                (to_state, from_state, self._now(), error_detail, retry, market),
            )
            self._conn.commit()
            return

        # SUSPENDED can be reached from any state
        if to_state == "SUSPENDED":
            self._conn.execute(
                "UPDATE state_machine SET current_state=?, previous_state=?, "
                "updated_at=? WHERE market=?",
                (to_state, from_state, self._now(), market),
            )
            self._conn.commit()
            return

        # Normal transition validation
        transitions = self._get_transitions(market)
        allowed = transitions.get(from_state, set())
        if to_state not in allowed:
            raise InvalidTransition(
                f"{market}: {from_state!r} -> {to_state!r} not allowed. "
                f"Valid targets: {allowed}"
            )

        self._conn.execute(
            "UPDATE state_machine SET current_state=?, previous_state=?, "
            "updated_at=?, error_detail=NULL, retry_count=0 WHERE market=?",
            (to_state, from_state, self._now(), market),
        )
        self._conn.commit()

    def lift_suspension(self, market: str) -> None:
        """Human lifts SUSPENDED state, returning to previous state."""
        current = self.get_state(market)
        if current["current_state"] != "SUSPENDED":
            raise InvalidTransition(
                f"{market}: not in SUSPENDED state, currently {current['current_state']!r}"
            )
        prev = current["previous_state"] or "IDLE"
        self._conn.execute(
            "UPDATE state_machine SET current_state=?, previous_state='SUSPENDED', "
            "updated_at=? WHERE market=?",
            (prev, self._now(), market),
        )
        self._conn.commit()

    def reset_to_idle(self, market: str, new_exchange_date: str) -> None:
        """Reset market to IDLE for a new trading day."""
        current = self.get_state(market)
        self._conn.execute(
            "UPDATE state_machine SET current_state='IDLE', previous_state=?, "
            "exchange_date=?, updated_at=?, error_detail=NULL, retry_count=0 "
            "WHERE market=?",
            (current["current_state"], new_exchange_date, self._now(), market),
        )
        self._conn.commit()

    def _force_state(self, market: str, state: str) -> None:
        """Force-set state (for testing only). Bypasses transition validation."""
        current = self.get_state(market)
        self._conn.execute(
            "UPDATE state_machine SET current_state=?, previous_state=?, updated_at=? "
            "WHERE market=?",
            (state, current["current_state"], self._now(), market),
        )
        self._conn.commit()
