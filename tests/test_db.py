import sqlite3
import pytest
from lib.db import get_connection, init_db, DB_SCHEMA_VERSION


def test_connection_uses_wal_mode(tmp_harness):
    conn = get_connection(tmp_harness)
    cursor = conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode == "wal", f"Expected WAL mode, got {mode}"
    conn.close()


def test_init_db_creates_tables(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    assert "task_log" in tables
    assert "task_results" in tables
    assert "state_machine" in tables
    assert "feishu_dedupe" in tables
    assert "alert_log" in tables
    conn.close()


def test_task_log_idempotency_key_unique(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    conn.execute(
        "INSERT INTO task_log (idempotency_key, task_type, market, exchange_date, status) "
        "VALUES ('key1', 'hypothesis_draft', 'a_stock', '2026-03-26', 'pending')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO task_log (idempotency_key, task_type, market, exchange_date, status) "
            "VALUES ('key1', 'hypothesis_draft', 'a_stock', '2026-03-26', 'pending')"
        )
    conn.close()


def test_task_results_table_structure(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    conn.execute(
        "INSERT INTO task_results (result_id, idempotency_key, worker_id, result_payload, created_at) "
        "VALUES ('r1', 'key1', 'worker1', '{\"data\": 1}', '2026-03-26T10:00:00')"
    )
    row = conn.execute("SELECT consumed FROM task_results WHERE result_id='r1'").fetchone()
    assert row[0] == 0, "Default consumed should be 0"
    conn.close()


def test_state_machine_table_structure(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    conn.execute(
        "INSERT INTO state_machine (market, current_state, exchange_date, updated_at) "
        "VALUES ('a_stock', 'IDLE', '2026-03-26', '2026-03-26T07:00:00')"
    )
    row = conn.execute("SELECT current_state FROM state_machine WHERE market='a_stock'").fetchone()
    assert row[0] == "IDLE"
    conn.close()


def test_schema_version_recorded(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == DB_SCHEMA_VERSION
    conn.close()
