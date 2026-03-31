import sqlite3
import json
import pytest
from lib.db import get_connection, init_db
from lib.run_store import RunStore


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "harness.db"
    conn = get_connection(str(db_path))
    init_db(conn)
    return conn


@pytest.fixture
def store(db):
    return RunStore(db)


# ── Schema tests ──


def test_runs_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
    )
    assert cursor.fetchone() is not None


def test_deliveries_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='deliveries'"
    )
    assert cursor.fetchone() is not None


def test_candidates_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidates'"
    )
    assert cursor.fetchone() is not None


def test_feedbacks_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='feedbacks'"
    )
    assert cursor.fetchone() is not None


def test_runs_idempotency_key_unique(db):
    db.execute(
        "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
        "VALUES ('r1', 'b1', 'key1', 'scan', 'a_stock', 'cron', 'pending', '[]', '{}', '2026-03-30T08:30:00', '2026-03-30T08:30:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
            "VALUES ('r2', 'b1', 'key1', 'scan', 'a_stock', 'cron', 'pending', '[]', '{}', '2026-03-30T08:31:00', '2026-03-30T08:31:00')"
        )


# ── RunStore CRUD tests ──


def test_create_run(store):
    run = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run["run_id"]
    assert run["batch_id"].endswith("-scan-a_stock")
    assert run["status"] == "pending"
    assert run["idempotency_key"]


def test_idempotent_run_skips(store):
    run1 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    store.update_status(run1["run_id"], "completed")

    run2 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run2["status"] == "skipped"
    assert run2["run_id"] == run1["run_id"]


def test_failed_run_allows_retry(store):
    run1 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    store.update_status(run1["run_id"], "failed", error="timeout")

    run2 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run2["status"] == "pending"
    assert run2["run_id"] != run1["run_id"]


def test_update_agent_trace(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.append_agent_trace(run["run_id"], agent="codex", status="started")
    store.append_agent_trace(run["run_id"], agent="codex", status="completed")
    result = store.get_run(run["run_id"])
    trace = json.loads(result["agent_trace"])
    assert len(trace) == 2
    assert trace[0]["agent"] == "codex"


def test_save_candidate(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    cand = store.save_candidate(
        run_id=run["run_id"],
        market="a_stock",
        primary_ticker="600519.SH",
        direction="long",
        confidence="high",
        thesis="Strong Q1 earnings",
        evidence=[{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
        auto_action="auto_lock",
    )
    assert cand["candidate_id"]
    candidates = store.list_candidates(run["run_id"])
    assert len(candidates) == 1


def test_save_delivery(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    dlv = store.save_delivery(
        run_id=run["run_id"],
        target="gomamon",
        message_kind="scan_result",
        requires_action=False,
    )
    assert dlv["delivery_id"]
    assert dlv["status"] == "pending"


def test_save_feedback(store):
    run = store.create_run(
        phase="review", market="global", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    fb = store.save_feedback(
        run_id=run["run_id"],
        source_hypothesis_id="H1",
        verdict="hit",
        weight_adjustments=[{"fact_id": "f1", "old_weight": 0.7, "new_weight": 0.735}],
        rule_proposals=[],
        lessons=[{"insight_text": "lesson1", "category": "timing"}],
    )
    assert fb["feedback_id"]


def test_get_pending_deliveries(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.save_delivery(run["run_id"], "gomamon", "scan_result", False)
    store.save_delivery(run["run_id"], "gabumon", "approval", True)
    pending = store.get_pending_deliveries()
    assert len(pending) == 2


def test_get_verify_history(store):
    # Create a completed verify run
    run = store.create_run(
        phase="verify", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.update_status(run["run_id"], "completed")
    history = store.get_runs_by_phase_and_window(
        phase="verify", start="2026-03-01T00:00:00", end="2026-04-01T00:00:00"
    )
    assert len(history) == 1
