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
        """
    )
    conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
    conn.commit()
