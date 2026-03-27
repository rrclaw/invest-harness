import json
import pytest
from lib.db import get_connection, init_db
from lib.state_machine import StateMachine
from lib.conductor import Conductor


@pytest.fixture
def env(tmp_path):
    db_path = tmp_path / "harness.db"
    conn = get_connection(db_path)
    init_db(conn)
    sm = StateMachine(conn)
    return conn, sm


def test_consume_task_results(env):
    conn, sm = env
    # Insert a task result
    conn.execute(
        "INSERT INTO task_results (result_id, idempotency_key, worker_id, result_payload, created_at) "
        "VALUES ('r1', 'key1', 'hypothesis_worker', '{\"status\": \"draft_ready\"}', '2026-03-26T08:00:00')"
    )
    conn.commit()

    conductor = Conductor(conn, sm)
    results = conductor.consume_pending_results()
    assert len(results) == 1
    assert results[0]["result_id"] == "r1"

    # Verify consumed flag is set
    row = conn.execute("SELECT consumed FROM task_results WHERE result_id='r1'").fetchone()
    assert row["consumed"] == 1


def test_consume_skips_already_consumed(env):
    conn, sm = env
    conn.execute(
        "INSERT INTO task_results (result_id, idempotency_key, worker_id, result_payload, consumed, created_at) "
        "VALUES ('r2', 'key2', 'worker', '{}', 1, '2026-03-26T08:00:00')"
    )
    conn.commit()
    conductor = Conductor(conn, sm)
    results = conductor.consume_pending_results()
    assert len(results) == 0


def test_register_task_idempotent(env):
    conn, sm = env
    conductor = Conductor(conn, sm)
    conductor.register_task("hypothesis_draft", "a_stock", "2026-03-26")
    # Second call should not raise (idempotent)
    conductor.register_task("hypothesis_draft", "a_stock", "2026-03-26")
    rows = conn.execute("SELECT * FROM task_log WHERE market='a_stock'").fetchall()
    assert len(rows) == 1


def test_update_task_status(env):
    conn, sm = env
    conductor = Conductor(conn, sm)
    conductor.register_task("hypothesis_draft", "a_stock", "2026-03-26")
    key = "hypothesis_draft_2026-03-26_a_stock"
    conductor.update_task_status(key, "running")
    row = conn.execute("SELECT status FROM task_log WHERE idempotency_key=?", (key,)).fetchone()
    assert row["status"] == "running"


def test_should_skip_non_trading_day(env):
    conn, sm = env
    conductor = Conductor(conn, sm)
    # Polymarket: calendar_bypass = True, always runs
    assert conductor.should_skip("polymarket", calendar_bypass=True) is False


def test_is_market_suspended(env):
    conn, sm = env
    sm.initialize("a_stock", "2026-03-26")
    sm._force_state("a_stock", "SUSPENDED")
    conductor = Conductor(conn, sm)
    assert conductor.is_market_suspended("a_stock") is True


def test_is_market_not_suspended(env):
    conn, sm = env
    sm.initialize("a_stock", "2026-03-26")
    conductor = Conductor(conn, sm)
    assert conductor.is_market_suspended("a_stock") is False
