"""Run Store — execution tracking, idempotency, and artifact management."""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _uuid() -> str:
    return str(uuid.uuid4())


class RunStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ── Runs ──

    def create_run(
        self,
        *,
        phase: str,
        market: str,
        trigger_source: str,
        watchlist_hash: str,
        knowledge_fingerprint: str,
        date: str | None = None,
    ) -> dict:
        date = date or datetime.now(timezone.utc).strftime("%Y%m%d")
        batch_id = f"{date}-{phase}-{market}"
        idempotency_key = hashlib.sha256(
            f"{batch_id}:{watchlist_hash}:{knowledge_fingerprint}".encode()
        ).hexdigest()

        # Check existing run with same idempotency_key
        existing = self._conn.execute(
            "SELECT run_id, status, artifacts FROM runs WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
            (idempotency_key,),
        ).fetchone()

        if existing:
            if existing["status"] == "completed":
                return {
                    "run_id": existing["run_id"],
                    "batch_id": batch_id,
                    "idempotency_key": idempotency_key,
                    "status": "skipped",
                    "artifacts": json.loads(existing["artifacts"]),
                }
            elif existing["status"] == "failed":
                # Delete old failed run so new one can use fresh idempotency_key
                self._conn.execute("DELETE FROM runs WHERE run_id = ?", (existing["run_id"],))
                self._conn.commit()
            elif existing["status"] in ("pending", "running"):
                return {
                    "run_id": existing["run_id"],
                    "batch_id": batch_id,
                    "idempotency_key": idempotency_key,
                    "status": existing["status"],
                }

        run_id = _uuid()
        now = _now()
        self._conn.execute(
            "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', '[]', '{}', ?, ?)",
            (run_id, batch_id, idempotency_key, phase, market, trigger_source, now, now),
        )
        self._conn.commit()
        return {
            "run_id": run_id,
            "batch_id": batch_id,
            "idempotency_key": idempotency_key,
            "status": "pending",
        }

    def get_run(self, run_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def update_status(self, run_id: str, status: str, *, error: str | None = None, artifacts: dict | None = None) -> None:
        now = _now()
        sets = ["status = ?", "updated_at = ?"]
        vals: list = [status, now]
        if error is not None:
            sets.append("error = ?")
            vals.append(error)
        if artifacts is not None:
            sets.append("artifacts = ?")
            vals.append(json.dumps(artifacts))
        if status == "completed":
            sets.append("completed_at = ?")
            vals.append(now)
        vals.append(run_id)
        self._conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", vals)
        self._conn.commit()

    def append_agent_trace(self, run_id: str, *, agent: str, status: str) -> None:
        row = self._conn.execute("SELECT agent_trace FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        trace = json.loads(row["agent_trace"]) if row else []
        trace.append({"agent": agent, "status": status, "at": _now()})
        self._conn.execute(
            "UPDATE runs SET agent_trace = ?, updated_at = ? WHERE run_id = ?",
            (json.dumps(trace), _now(), run_id),
        )
        self._conn.commit()

    def get_runs_by_phase_and_window(self, *, phase: str, start: str, end: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE phase = ? AND created_at >= ? AND created_at <= ? ORDER BY created_at",
            (phase, start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Candidates ──

    def save_candidate(self, *, run_id: str, market: str, primary_ticker: str,
                       direction: str, confidence: str, thesis: str,
                       evidence: list, auto_action: str,
                       related_tickers: list | None = None,
                       suggested_entry: float | None = None,
                       suggested_exit: float | None = None,
                       stop_loss: float | None = None,
                       time_horizon: str | None = None,
                       risk_factors: list | None = None) -> dict:
        candidate_id = _uuid()
        self._conn.execute(
            "INSERT INTO candidates (candidate_id, run_id, market, primary_ticker, related_tickers, "
            "direction, confidence, thesis, evidence, suggested_entry, suggested_exit, stop_loss, "
            "time_horizon, risk_factors, auto_action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, run_id, market, primary_ticker,
             json.dumps(related_tickers or []), direction, confidence, thesis,
             json.dumps(evidence), suggested_entry, suggested_exit, stop_loss,
             time_horizon, json.dumps(risk_factors or []), auto_action, _now()),
        )
        self._conn.commit()
        return {"candidate_id": candidate_id}

    def list_candidates(self, run_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM candidates WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_candidates_by_ticker(self, ticker: str, *, days: int = 30) -> list[dict]:
        cutoff_str = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self._conn.execute(
            "SELECT * FROM candidates WHERE primary_ticker = ? AND created_at >= ? ORDER BY created_at DESC",
            (ticker, cutoff_str),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Deliveries ──

    def save_delivery(self, run_id: str, target: str, message_kind: str,
                      requires_action: bool, *, card_template: str | None = None) -> dict:
        delivery_id = _uuid()
        idem_key = hashlib.sha256(f"{run_id}:{target}:{message_kind}".encode()).hexdigest()
        # Skip if already exists
        existing = self._conn.execute(
            "SELECT delivery_id, status FROM deliveries WHERE idempotency_key = ?", (idem_key,)
        ).fetchone()
        if existing:
            return dict(existing)
        self._conn.execute(
            "INSERT INTO deliveries (delivery_id, run_id, target, message_kind, card_template, "
            "requires_action, status, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (delivery_id, run_id, target, message_kind, card_template, int(requires_action), idem_key),
        )
        self._conn.commit()
        return {"delivery_id": delivery_id, "status": "pending"}

    def mark_delivered(self, delivery_id: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET status = 'sent', sent_at = ? WHERE delivery_id = ?",
            (_now(), delivery_id),
        )
        self._conn.commit()

    def mark_delivery_failed(self, delivery_id: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET status = 'failed' WHERE delivery_id = ?", (delivery_id,)
        )
        self._conn.commit()

    def update_action_status(self, delivery_id: str, action_status: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET action_status = ?, action_at = ? WHERE delivery_id = ?",
            (action_status, _now(), delivery_id),
        )
        self._conn.commit()

    def get_pending_deliveries(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM deliveries WHERE status = 'pending' ORDER BY rowid"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Feedbacks ──

    def save_feedback(self, *, run_id: str, source_hypothesis_id: str | None = None,
                      verdict: str | None = None, weight_adjustments: list | None = None,
                      rule_proposals: list | None = None, lessons: list | None = None) -> dict:
        feedback_id = _uuid()
        self._conn.execute(
            "INSERT INTO feedbacks (feedback_id, run_id, source_hypothesis_id, verdict, "
            "weight_adjustments, rule_proposals, lessons, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (feedback_id, run_id, source_hypothesis_id, verdict,
             json.dumps(weight_adjustments or []), json.dumps(rule_proposals or []),
             json.dumps(lessons or []), _now()),
        )
        self._conn.commit()
        return {"feedback_id": feedback_id}

    def get_feedbacks_for_run(self, run_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM feedbacks WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(r) for r in rows]
