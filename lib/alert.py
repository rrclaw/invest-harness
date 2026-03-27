"""Three-tier alert system: L1 (system fault), L2 (business anomaly), L3 (info).

L1 -> state machine SUSPENDED, human must restore.
L2 -> block buy orders, observe/liquidate mode.
L3 -> no blocking action.
"""

import sqlite3
import uuid
from datetime import datetime, timezone


class AlertManager:
    """Manages alert creation, logging, and querying."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def fire(
        self,
        level: str,
        market: str,
        message: str,
        source: str,
        hypothesis_ref: str | None = None,
    ) -> dict:
        """Create and persist a new alert. Returns alert dict."""
        if level not in ("L1", "L2", "L3"):
            raise ValueError(f"Invalid alert level: {level!r}")

        alert_id = f"alert_{uuid.uuid4().hex[:12]}"
        created_at = self._now()

        self._conn.execute(
            "INSERT INTO alert_log (alert_id, level, market, message, source, hypothesis_ref, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (alert_id, level, market, message, source, hypothesis_ref, created_at),
        )
        self._conn.commit()

        return {
            "alert_id": alert_id,
            "level": level,
            "market": market,
            "message": message,
            "source": source,
            "hypothesis_ref": hypothesis_ref,
            "created_at": created_at,
        }

    def acknowledge(self, alert_id: str) -> None:
        self._conn.execute(
            "UPDATE alert_log SET acknowledged=1 WHERE alert_id=?", (alert_id,)
        )
        self._conn.commit()

    def get_unacknowledged(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM alert_log WHERE acknowledged=0 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_level(self, level: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM alert_log WHERE level=? ORDER BY created_at DESC",
            (level,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_market(self, market: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM alert_log WHERE market=? ORDER BY created_at DESC",
            (market,),
        ).fetchall()
        return [dict(r) for r in rows]
