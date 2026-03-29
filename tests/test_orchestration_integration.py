"""Integration test: conductor dispatches tasks, consumes results, drives state machine."""

import json
import pytest
from lib.db import get_connection, init_db
from lib.state_machine import StateMachine
from lib.conductor import Conductor
from lib.alert import AlertManager
from lib.hypothesis import HypothesisManager
from lib.review import ReviewGenerator
from lib.rules import RuleEngine
from lib.feishu import FeishuClient, FEISHU_GROUPS
from unittest.mock import patch, MagicMock

TEST_GROUP_MAP = {
    "tailmon": "oc_test_tailmon",
    "agumon": "oc_test_agumon",
    "gabumon": "oc_test_gabumon",
    "gomamon": "oc_test_gomamon",
    "kabuterimon": "oc_test_kabuterimon",
    "patamon": "oc_test_patamon",
}


def _make_full_hypothesis():
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
            "prompt_hash": "sha256:abc",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "generated_at": "2026-03-26T07:35:00+08:00",
            "idempotency_key": "hypothesis_draft_2026-03-26_a_stock_001",
        },
    }


def test_full_day_orchestration(tmp_path):
    """Simulate a full trading day: IDLE -> HYPO -> LOCK -> MONITOR -> VERIFY -> REVIEW."""
    db_path = tmp_path / "harness.db"
    conn = get_connection(db_path)
    init_db(conn)
    sm = StateMachine(conn)
    conductor = Conductor(conn, sm)
    alert_mgr = AlertManager(conn)
    hypo_mgr = HypothesisManager(tmp_path / "hypotheses")

    # Day start: initialize
    sm.initialize("a_stock", "2026-03-26")
    assert sm.get_state("a_stock")["current_state"] == "IDLE"

    # Pre-market: generate hypothesis
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    task_key = conductor.register_task("hypothesis_draft", "a_stock", "2026-03-26")
    conductor.update_task_status(task_key, "running")

    # Worker deposits result
    hypo = _make_full_hypothesis()
    hypo_mgr.save_draft(hypo, "2026-03-26")
    conn.execute(
        "INSERT INTO task_results (result_id, idempotency_key, worker_id, result_payload, created_at) "
        "VALUES ('r1', ?, 'hypothesis_worker', ?, '2026-03-26T07:40:00')",
        (task_key, json.dumps({"status": "draft_ready", "hypothesis_id": hypo["hypothesis_id"]})),
    )
    conn.commit()

    # Conductor consumes
    results = conductor.consume_pending_results()
    assert len(results) == 1
    conductor.update_task_status(task_key, "done")

    # Human approves -> lock
    hypo_mgr.lock("2026-03-26", "a_stock", approved_by="human")
    sm.transition("a_stock", "LOCKED")

    # Market open -> monitoring
    sm.transition("a_stock", "MONITORING")
    assert not conductor.is_market_suspended("a_stock")

    # L2 alert during monitoring
    alert = alert_mgr.fire("L2", "a_stock", "Rapid drop detected", "polling_daemon")
    assert alert["level"] == "L2"

    # Market close -> verification
    sm.transition("a_stock", "VERIFYING")

    # Post-verify (simplified)
    from lib.verification import VerificationEngine
    engine = VerificationEngine()
    locked_hypo = hypo_mgr.load_for_date("2026-03-26", "a_stock")
    verify_result = engine.verify(
        locked_hypo,
        {"close_change_pct": 6.8, "direction": "up", "peak_time": "09:35-10:15",
         "invalidation_triggered": False, "market_cause": "Policy catalyst",
         "market_cause_evidence": ["f_20260326_018"]},
    )
    assert verify_result["verdict"] == "hit"

    # Review
    sm.transition("a_stock", "REVIEWED")
    gen = ReviewGenerator()
    md = gen.generate_markdown([verify_result], "2026-03-26")
    assert "True Hits" in md

    # Reset for next day
    sm.reset_to_idle("a_stock", "2026-03-27")
    assert sm.get_state("a_stock")["current_state"] == "IDLE"

    conn.close()


def test_l1_alert_suspends_market(tmp_path):
    """L1 alert triggers SUSPENDED state."""
    db_path = tmp_path / "harness.db"
    conn = get_connection(db_path)
    init_db(conn)
    sm = StateMachine(conn)
    alert_mgr = AlertManager(conn)

    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    sm.transition("a_stock", "LOCKED")
    sm.transition("a_stock", "MONITORING")

    # L1 alert -> SUSPENDED
    alert_mgr.fire("L1", "a_stock", "API blocked, retry exhausted", "adapter_tushare")
    sm.transition("a_stock", "SUSPENDED")
    assert sm.get_state("a_stock")["current_state"] == "SUSPENDED"

    # Human lifts suspension
    sm.lift_suspension("a_stock")
    assert sm.get_state("a_stock")["current_state"] == "MONITORING"

    conn.close()


def test_feishu_routing_integration(tmp_path):
    """Verify Feishu routing for different message types."""
    db_path = tmp_path / "harness.db"
    conn = get_connection(db_path)
    init_db(conn)

    with patch("lib.feishu.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
        client = FeishuClient("test", "test", conn, group_map=TEST_GROUP_MAP)

        # Approval -> Gabumon
        target = client.route_approval()
        assert target == "gabumon"
        client.send_to_group(target, "Please approve hypothesis h_20260326_a_001")

        # L1 alert -> Kabuterimon
        target = client.route_alert("L1")
        assert target == "kabuterimon"
        client.send_to_group(target, "CRITICAL: API blocked")

        # L2 alert -> Gomamon
        target = client.route_alert("L2")
        assert target == "gomamon"
        client.send_to_group(target, "WARNING: Data feed degraded")

    assert mock_post.call_count == 6  # 3 token calls + 3 message calls
    conn.close()
