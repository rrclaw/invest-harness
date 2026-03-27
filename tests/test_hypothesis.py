import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from lib.hypothesis import HypothesisManager


@pytest.fixture
def hypo_dir(tmp_path):
    d = tmp_path / "hypotheses"
    d.mkdir()
    return d


@pytest.fixture
def mgr(hypo_dir):
    return HypothesisManager(hypotheses_dir=hypo_dir)


def _make_draft(market="a_stock", ticker="688256.SH"):
    return {
        "hypothesis_id": f"h_20260326_{market[:1]}_001",
        "market": market,
        "ticker": ticker,
        "company": "Cambricon",
        "theme": ["AI_compute"],
        "created_at": "2026-03-26T07:45:00+08:00",
        "locked_at": None,
        "approved_by": None,
        "trigger_event": "Q4 earnings beat",
        "core_evidence": [{"fact_ref": "f_20260326_001", "summary": "Revenue up"}],
        "invalidation_conditions": ["Volume < 5%"],
        "observation_window": {
            "start": "2026-03-26T09:30:00+08:00",
            "end": "2026-03-26T15:00:00+08:00",
        },
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
            "prompt_hash": "sha256:abc123",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "generated_at": "2026-03-26T07:35:00+08:00",
            "idempotency_key": "hypothesis_draft_2026-03-26_a_stock_001",
        },
    }


def test_save_draft(mgr, hypo_dir):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    path = hypo_dir / "2026-03-26" / "a_stock.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["status"] == "draft"


def test_load_for_date(mgr, hypo_dir):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    loaded = mgr.load_for_date("2026-03-26", "a_stock")
    assert loaded["hypothesis_id"] == "h_20260326_a_001"


def test_load_nonexistent_returns_none(mgr):
    result = mgr.load_for_date("2026-03-26", "a_stock")
    assert result is None


def test_lock_hypothesis(mgr):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    loaded = mgr.load_for_date("2026-03-26", "a_stock")
    assert loaded["status"] == "locked"
    assert loaded["approved_by"] == "human"
    assert loaded["locked_at"] is not None


def test_lock_creates_lock_file(mgr, hypo_dir):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    lock_file = hypo_dir / "2026-03-26" / "_lock.a_stock"
    assert lock_file.exists()


def test_is_locked(mgr):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    assert mgr.is_locked("2026-03-26", "a_stock") is False
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    assert mgr.is_locked("2026-03-26", "a_stock") is True


def test_cannot_modify_locked_hypothesis(mgr):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    with pytest.raises(PermissionError, match="locked"):
        mgr.save_draft(draft, "2026-03-26")


def test_mark_unconfirmed(mgr):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.mark_unconfirmed("2026-03-26", "a_stock")
    loaded = mgr.load_for_date("2026-03-26", "a_stock")
    assert loaded["status"] == "unconfirmed"


def test_amend_hypothesis(mgr, hypo_dir):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    # Simulate human deleting lock file
    lock_file = hypo_dir / "2026-03-26" / "_lock.a_stock"
    lock_file.unlink()
    # Amend
    mgr.amend(
        "2026-03-26",
        "a_stock",
        reason="Major shareholder announced reduction",
        original_action="gap_up: 50% position",
        revised_action="Immediate full liquidation",
        amended_by="human",
    )
    loaded = mgr.load_for_date("2026-03-26", "a_stock")
    assert loaded["status"] == "amended"
    assert len(loaded["amend_log"]) == 1
    assert loaded["amend_log"][0]["reason"] == "Major shareholder announced reduction"


def test_amend_without_lock_removal_raises(mgr):
    draft = _make_draft()
    mgr.save_draft(draft, "2026-03-26")
    mgr.lock("2026-03-26", "a_stock", approved_by="human")
    with pytest.raises(PermissionError, match="lock file"):
        mgr.amend("2026-03-26", "a_stock", "reason", "old", "new", "human")


def test_list_all_for_date(mgr):
    mgr.save_draft(_make_draft("a_stock"), "2026-03-26")
    draft_hk = _make_draft("hk_stock", "0700.HK")
    draft_hk["hypothesis_id"] = "h_20260326_h_001"
    mgr.save_draft(draft_hk, "2026-03-26")
    all_hypos = mgr.list_for_date("2026-03-26")
    assert len(all_hypos) == 2
    markets = {h["market"] for h in all_hypos}
    assert markets == {"a_stock", "hk_stock"}
