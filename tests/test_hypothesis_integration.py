"""Integration test: full hypothesis lifecycle from draft to verification."""

import pytest
from lib.db import get_connection, init_db
from lib.state_machine import StateMachine
from lib.hypothesis import HypothesisManager
from lib.alert import AlertManager
from lib.verification import VerificationEngine, Verdict
from lib.stat_eligibility import check_eligibility
from scripts.lock_hypothesis import check_and_lock
from scripts.post_verify import run_post_verify


def _make_full_draft():
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
            "direction": {"metric": "Close direction", "bull": "up"},
            "magnitude": {"metric": "Close change %", "threshold": 2.0},
            "time_window": {"metric": "Key move timing", "expected": "09:30-10:30"},
            "invalidation_triggered": {"metric": "Boolean"},
        },
        "action_plan": {"gap_up": {"position_size": "50%"}},
        "status": "draft",
        "amend_log": [],
        "_audit": {
            "model_version": "claude-opus-4-6",
            "prompt_hash": "sha256:abc123",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "generated_at": "2026-03-26T07:35:00+08:00",
            "idempotency_key": "hypothesis_draft_2026-03-26_a_stock_001",
        },
    }


def test_full_lifecycle_hit(tmp_path):
    """Draft -> Lock -> Monitor -> Verify -> Eligibility check."""
    conn = get_connection(tmp_path / "harness.db")
    init_db(conn)
    sm = StateMachine(conn)
    hypo_mgr = HypothesisManager(tmp_path / "hypotheses")
    alert_mgr = AlertManager(conn)

    # 1. IDLE -> HYPOTHESIS_DRAFT
    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    draft = _make_full_draft()
    hypo_mgr.save_draft(draft, "2026-03-26")

    # 2. Human approves -> LOCKED
    hypo_mgr.lock("2026-03-26", "a_stock", approved_by="human")
    sm.transition("a_stock", "LOCKED")
    assert hypo_mgr.is_locked("2026-03-26", "a_stock")

    # 3. Market open -> MONITORING
    sm.transition("a_stock", "MONITORING")

    # 4. Market close -> VERIFYING
    sm.transition("a_stock", "VERIFYING")

    # 5. Post-market verification
    actuals = {
        "close_change_pct": 6.8,
        "direction": "up",
        "peak_time": "09:35-10:15",
        "invalidation_triggered": False,
        "market_cause": "Policy catalyst",
        "market_cause_evidence": ["f_20260326_018"],
    }
    result = run_post_verify(
        hypothesis=hypo_mgr.load_for_date("2026-03-26", "a_stock"),
        actuals=actuals,
        date="2026-03-26",
        reviews_dir=str(tmp_path / "reviews"),
    )
    assert result["verdict"] == Verdict.HIT

    # 6. Check statistical eligibility
    locked_hypo = hypo_mgr.load_for_date("2026-03-26", "a_stock")
    elig = check_eligibility(
        status=locked_hypo["status"],
        audit=locked_hypo["_audit"],
        amend_log=locked_hypo["amend_log"],
        fallback_used=locked_hypo["_audit"]["fallback_used"],
        invalidation_type=None,
    )
    assert elig["stat_eligible"] is True
    assert elig["win_rate_pool"] is True

    # 7. REVIEWED
    sm.transition("a_stock", "REVIEWED")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "REVIEWED"

    conn.close()


def test_unconfirmed_lifecycle(tmp_path):
    """Draft -> timeout -> unconfirmed -> verify -> excluded from stats."""
    conn = get_connection(tmp_path / "harness.db")
    init_db(conn)
    sm = StateMachine(conn)
    hypo_mgr = HypothesisManager(tmp_path / "hypotheses")

    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    hypo_mgr.save_draft(_make_full_draft(), "2026-03-26")

    # Timeout: no approval
    lock_result = check_and_lock(hypo_mgr, "2026-03-26", "a_stock")
    assert lock_result["action"] == "unconfirmed"

    # Verify: should be UNCONFIRMED verdict
    engine = VerificationEngine()
    hypo = hypo_mgr.load_for_date("2026-03-26", "a_stock")
    actuals = {"close_change_pct": 6.8, "direction": "up", "peak_time": "09:35",
               "invalidation_triggered": False, "market_cause": "", "market_cause_evidence": []}
    result = engine.verify(hypo, actuals)
    assert result["verdict"] == Verdict.UNCONFIRMED
    assert result["stat_eligible"] is False

    conn.close()
