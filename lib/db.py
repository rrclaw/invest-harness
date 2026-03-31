"""SQLite database module for invest_harness.

CRITICAL: Every connection MUST use WAL mode. This is the foundational
guarantee for concurrent multi-worker read/write on a single Mac Mini.
"""

import sqlite3
from pathlib import Path

DB_SCHEMA_VERSION = 1


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode enforced."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist. Idempotent."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS state_machine (
            market          TEXT PRIMARY KEY,
            current_state   TEXT NOT NULL,
            previous_state  TEXT,
            exchange_date   TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            error_detail    TEXT,
            retry_count     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS task_log (
            idempotency_key TEXT PRIMARY KEY,
            task_type       TEXT NOT NULL,
            market          TEXT NOT NULL,
            exchange_date   TEXT NOT NULL,
            status          TEXT NOT NULL,
            started_at      TEXT,
            finished_at     TEXT,
            retry_count     INTEGER DEFAULT 0,
            error_detail    TEXT
        );

        CREATE TABLE IF NOT EXISTS task_results (
            result_id       TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL,
            worker_id       TEXT NOT NULL,
            result_payload  TEXT NOT NULL,
            consumed        INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feishu_dedupe (
            content_hash    TEXT NOT NULL,
            group_id        TEXT NOT NULL,
            sent_at         TEXT NOT NULL,
            PRIMARY KEY (content_hash, group_id)
        );

        CREATE TABLE IF NOT EXISTS alert_log (
            alert_id        TEXT PRIMARY KEY,
            level           TEXT NOT NULL,
            market          TEXT NOT NULL,
            message         TEXT NOT NULL,
            source          TEXT,
            hypothesis_ref  TEXT,
            created_at      TEXT NOT NULL,
            acknowledged    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            phase TEXT NOT NULL CHECK(phase IN ('scan','verify','review','feedback','watchlist_change')),
            market TEXT NOT NULL,
            trigger_source TEXT NOT NULL CHECK(trigger_source IN ('cron','manual','event')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','completed','failed','skipped')),
            agent_trace TEXT NOT NULL DEFAULT '[]',
            artifacts TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id);
        CREATE INDEX IF NOT EXISTS idx_runs_phase_market ON runs(phase, market);
        CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

        CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            target TEXT NOT NULL,
            message_kind TEXT NOT NULL,
            card_template TEXT,
            requires_action INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
            action_status TEXT CHECK(action_status IN (NULL,'approved','rejected')),
            idempotency_key TEXT NOT NULL UNIQUE,
            sent_at TEXT,
            action_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_deliveries_run ON deliveries(run_id);

        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            market TEXT NOT NULL,
            primary_ticker TEXT NOT NULL,
            related_tickers TEXT NOT NULL DEFAULT '[]',
            direction TEXT NOT NULL CHECK(direction IN ('long','short','neutral')),
            confidence TEXT NOT NULL CHECK(confidence IN ('high','medium','low')),
            thesis TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '[]',
            suggested_entry REAL,
            suggested_exit REAL,
            stop_loss REAL,
            time_horizon TEXT,
            risk_factors TEXT NOT NULL DEFAULT '[]',
            auto_action TEXT NOT NULL CHECK(auto_action IN ('auto_lock','await_approval','log_only')),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
        CREATE INDEX IF NOT EXISTS idx_candidates_ticker ON candidates(primary_ticker);

        CREATE TABLE IF NOT EXISTS feedbacks (
            feedback_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            source_hypothesis_id TEXT,
            verdict TEXT,
            weight_adjustments TEXT NOT NULL DEFAULT '[]',
            rule_proposals TEXT NOT NULL DEFAULT '[]',
            lessons TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_feedbacks_run ON feedbacks(run_id);
        """
    )
    conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
    conn.commit()
