import pytest
from lib.verification import VerificationEngine, Verdict


def test_verdict_enum():
    assert Verdict.HIT == "hit"
    assert Verdict.PARTIAL_HIT == "partial_hit"
    assert Verdict.MISS == "miss"
    assert Verdict.INVALIDATED == "invalidated"
    assert Verdict.UNCONFIRMED == "unconfirmed"


def _make_hypothesis():
    return {
        "hypothesis_id": "h_20260326_a_001",
        "market": "a_stock",
        "ticker": "688256.SH",
        "company": "Cambricon",
        "status": "locked",
        "scenario": {
            "bull": {"description": "Gap up 5%+", "target": "+8% to limit-up"},
            "base": {"description": "Gap up 2-5%", "target": "+3% to +6%"},
            "bear": {"description": "Flat or gap down", "target": "0% to -3%"},
        },
        "review_rubric": {
            "direction": {"metric": "Close direction", "bull": "up", "base": "up", "bear": "down/flat"},
            "magnitude": {"metric": "Close change %", "threshold": 2.0},
            "time_window": {"metric": "Key move timing", "expected": "09:30-10:30"},
            "invalidation_triggered": {"metric": "Boolean", "type": "boolean"},
        },
        "invalidation_conditions": ["Auction volume < 5% of yesterday"],
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


def _make_actuals(close_change=6.8, direction="up", peak_time="09:35-10:15"):
    return {
        "close_change_pct": close_change,
        "direction": direction,
        "peak_time": peak_time,
        "invalidation_triggered": False,
        "market_cause": "Compute policy capital inflow",
        "market_cause_evidence": ["f_20260326_018"],
    }


def test_full_hit():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals())
    assert result["verdict"] == Verdict.HIT
    assert result["score"]["earned"] == 4
    assert result["score"]["possible"] == 4


def test_partial_hit_direction_correct_magnitude_off():
    actuals = _make_actuals(close_change=1.5)
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), actuals)
    assert result["verdict"] == Verdict.PARTIAL_HIT
    assert result["dimensions"]["direction"]["match"] is True
    assert result["dimensions"]["magnitude"]["within_tolerance"] is False


def test_miss_wrong_direction():
    actuals = _make_actuals(close_change=-2.0, direction="down")
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), actuals)
    assert result["verdict"] == Verdict.MISS
    assert result["dimensions"]["direction"]["match"] is False


def test_invalidated():
    actuals = _make_actuals()
    actuals["invalidation_triggered"] = True
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), actuals)
    assert result["verdict"] == Verdict.INVALIDATED


def test_unconfirmed_hypothesis():
    hypo = _make_hypothesis()
    hypo["status"] = "unconfirmed"
    engine = VerificationEngine()
    result = engine.verify(hypo, _make_actuals())
    assert result["verdict"] == Verdict.UNCONFIRMED
    assert result["stat_eligible"] is False


def test_cause_match_aligned():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals())
    assert result["dimensions"]["cause"]["thesis_cause_match"] in ("aligned", "unknown")


def test_score_structure():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals())
    score = result["score"]
    assert "direction" in score
    assert "magnitude" in score
    assert "time_window" in score
    assert "cause" in score
    assert score["earned"] == score["direction"] + score["magnitude"] + score["time_window"] + score["cause"]
    assert score["possible"] == 4


def test_scenario_matched():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals(close_change=6.8))
    assert result["scenario_matched"] == "bull"


def test_scenario_matched_base():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals(close_change=4.0))
    assert result["scenario_matched"] == "base"


def test_scenario_matched_bear():
    engine = VerificationEngine()
    result = engine.verify(_make_hypothesis(), _make_actuals(close_change=-1.0, direction="down"))
    assert result["scenario_matched"] == "bear"
