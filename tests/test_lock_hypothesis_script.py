import json
import pytest
from pathlib import Path
from lib.hypothesis import HypothesisManager
from scripts.lock_hypothesis import check_and_lock


def _make_draft():
    return {
        "hypothesis_id": "h_20260326_a_001",
        "market": "a_stock",
        "ticker": "688256.SH",
        "company": "Cambricon",
        "theme": ["AI_compute"],
        "created_at": "2026-03-26T07:45:00+08:00",
        "locked_at": None,
        "approved_by": None,
        "trigger_event": "Q4 earnings beat",
        "core_evidence": [{"fact_ref": "f_20260326_001", "summary": "Revenue up"}],
        "invalidation_conditions": ["Volume < 5%"],
        "observation_window": {"start": "2026-03-26T09:30:00+08:00", "end": "2026-03-26T15:00:00+08:00"},
        "probability": 0.7,
        "odds": "2:1",
        "win_rate_estimate": 0.65,
        "scenario": {
            "bull": {"description": "Gap up 5%+", "target": "+8%"},
            "base": {"description": "Gap up 2-5%", "target": "+3%"},
            "bear": {"description": "Flat", "target": "0%"},
        },
        "review_rubric": {
            "direction": {"metric": "Close direction"},
            "magnitude": {"metric": "Close change %"},
            "time_window": {"metric": "Key move timing"},
            "invalidation_triggered": {"metric": "Boolean"},
        },
        "action_plan": {"gap_up": {"position_size": "50%"}},
        "status": "draft",
        "amend_log": [],
        "_audit": {
            "model_version": "claude-opus-4-6",
            "prompt_hash": "sha256:abc",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "generated_at": "2026-03-26T07:35:00+08:00",
            "idempotency_key": "key1",
        },
    }


def test_check_and_lock_already_locked(tmp_path):
    mgr = HypothesisManager(tmp_path / "hypotheses")
    mgr.save_draft(_make_draft(), "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", "human")
    result = check_and_lock(mgr, "2026-03-26", "a_stock")
    assert result["action"] == "already_locked"


def test_check_and_lock_marks_unconfirmed(tmp_path):
    mgr = HypothesisManager(tmp_path / "hypotheses")
    mgr.save_draft(_make_draft(), "2026-03-26")
    result = check_and_lock(mgr, "2026-03-26", "a_stock")
    assert result["action"] == "unconfirmed"
    loaded = mgr.load_for_date("2026-03-26", "a_stock")
    assert loaded["status"] == "unconfirmed"


def test_check_and_lock_no_hypothesis(tmp_path):
    mgr = HypothesisManager(tmp_path / "hypotheses")
    result = check_and_lock(mgr, "2026-03-26", "a_stock")
    assert result["action"] == "no_hypothesis"
