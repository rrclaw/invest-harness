"""Integration test: scan → verify → review → feedback full loop."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def harness_env(tmp_path):
    """Set up a minimal harness environment for integration testing."""
    (tmp_path / "config" / "default").mkdir(parents=True)
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "knowledge" / "raw").mkdir(parents=True)
    (tmp_path / "knowledge" / "normalized").mkdir(parents=True)
    (tmp_path / "knowledge" / "curated").mkdir(parents=True)
    (tmp_path / "hypotheses").mkdir()
    (tmp_path / "reviews").mkdir()
    (tmp_path / "rules").mkdir()
    (tmp_path / "chroma_storage").mkdir()
    (tmp_path / "scans").mkdir()
    (tmp_path / "prompts").mkdir()

    (tmp_path / "prompts" / "scan.md").write_text("Analyze: {context_bundle}\nRules: {rules}")

    runtime = {
        "llm": {"provider": "test"},
        "transport": {"type": "noop"},
        "knowledge": {"canonical_pipeline_root": str(tmp_path / "knowledge")},
        "markets": {"enabled": ["a_stock"]},
    }
    (tmp_path / "config" / "default" / "runtime.json").write_text(json.dumps(runtime))

    watchlist = {
        "a_stock": [{"ticker": "600519.SH", "name": "贵州茅台", "added_at": "2026-03-28", "added_by": "test"}],
        "hk_stock": [], "us_stock": [], "polymarket": [],
    }
    (tmp_path / "config" / "local" / "watchlist.json").write_text(json.dumps(watchlist))

    fact = {"fact_id": "f1", "company": "贵州茅台", "tickers": ["600519.SH"],
            "topic": "earnings", "status": "active", "text": "Q1 revenue up 15%",
            "source_type": "company_research", "source_weight": 0.9,
            "updated_at": "2026-03-29"}
    (tmp_path / "knowledge" / "normalized" / "facts.jsonl").write_text(json.dumps(fact) + "\n")

    from lib.db import get_connection, init_db
    conn = get_connection(str(tmp_path / "harness.db"))
    init_db(conn)

    return tmp_path, conn


def test_scan_creates_candidates(harness_env):
    """Verify scan command produces candidates from knowledge base."""
    tmp_path, conn = harness_env
    from lib.run_store import RunStore
    store = RunStore(conn)

    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="test", knowledge_fingerprint="test",
        date="20260330",
    )
    assert run["status"] == "pending"

    cand = store.save_candidate(
        run_id=run["run_id"], market="a_stock",
        primary_ticker="600519.SH", direction="long",
        confidence="high", thesis="Strong Q1",
        evidence=[{"fact_id": "f1", "relevance_score": 0.9, "snippet": "Q1 up 15%"}],
        auto_action="auto_lock",
    )
    assert cand["candidate_id"]

    candidates = store.list_candidates(run["run_id"])
    assert len(candidates) == 1
    assert candidates[0]["primary_ticker"] == "600519.SH"

    store.update_status(run["run_id"], "completed")

    run2 = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="test", knowledge_fingerprint="test",
        date="20260330",
    )
    assert run2["status"] == "skipped"


def test_feedback_weight_adjustment(harness_env):
    """Verify feedback engine adjusts knowledge weights."""
    tmp_path, conn = harness_env
    from lib.feedback_engine import FeedbackEngine

    mock_knowledge = MagicMock()
    mock_knowledge.update_source_weight.return_value = True

    engine = FeedbackEngine(
        knowledge=mock_knowledge, chroma=MagicMock(),
        llm_call=MagicMock(), rules=[],
    )

    adjustments = engine.adjust_weights([{
        "verdict": "hit",
        "hypothesis_ref": "H1",
        "evidence_fact_ids": ["f1"],
    }])
    assert len(adjustments) == 1
    assert adjustments[0]["new_weight"] > adjustments[0]["old_weight"]

    adjustments = engine.adjust_weights([{
        "verdict": "miss",
        "hypothesis_ref": "H2",
        "evidence_fact_ids": ["f2"],
    }])
    assert len(adjustments) == 1
    assert adjustments[0]["new_weight"] < adjustments[0]["old_weight"]
