"""Tests for FeedbackEngine."""

import json
import pytest
from unittest.mock import MagicMock
from lib.feedback_engine import FeedbackEngine


@pytest.fixture
def mock_knowledge():
    kp = MagicMock()
    kp.update_source_weight.return_value = True
    kp.add_curated_insight.return_value = {"insight_id": "i1"}
    kp._dir = MagicMock()
    return kp


@pytest.fixture
def engine(mock_knowledge):
    return FeedbackEngine(
        knowledge=mock_knowledge,
        chroma=MagicMock(),
        llm_call=MagicMock(),
        rules=[],
    )


def test_adjust_weights_hit(engine, mock_knowledge):
    result = engine.adjust_weights([{
        "verdict": "hit",
        "hypothesis_ref": "H1",
        "evidence_fact_ids": ["f1", "f2"],
    }])
    assert len(result) == 2
    for adj in result:
        assert adj["new_weight"] > adj["old_weight"]
    assert mock_knowledge.update_source_weight.call_count == 2


def test_adjust_weights_miss(engine, mock_knowledge):
    result = engine.adjust_weights([{
        "verdict": "miss",
        "hypothesis_ref": "H2",
        "evidence_fact_ids": ["f3"],
    }])
    assert len(result) == 1
    assert result[0]["new_weight"] < result[0]["old_weight"]


def test_adjust_weights_partial_hit_no_change(engine, mock_knowledge):
    result = engine.adjust_weights([{
        "verdict": "partial_hit",
        "hypothesis_ref": "H3",
        "evidence_fact_ids": ["f4"],
    }])
    assert len(result) == 0
    mock_knowledge.update_source_weight.assert_not_called()


def test_adjust_weights_invalidated_no_change(engine, mock_knowledge):
    result = engine.adjust_weights([{
        "verdict": "invalidated",
        "hypothesis_ref": "H4",
        "evidence_fact_ids": ["f5"],
    }])
    assert len(result) == 0


def test_generate_rule_proposals(engine):
    engine._llm_call.return_value = json.dumps([{
        "action": "add",
        "rule_id": None,
        "title": "Sentiment divergence downgrade",
        "diff": "New rule",
        "rationale": "2 misses caused by sentiment",
    }])
    proposals = engine.generate_rule_proposals([{"verdict": "miss"}])
    assert len(proposals) == 1
    assert proposals[0]["status"] == "pending_approval"
    assert proposals[0]["proposal_id"]


def test_generate_rule_proposals_empty_misses(engine):
    proposals = engine.generate_rule_proposals([])
    assert proposals == []


def test_extract_lessons(engine):
    engine._llm_call.return_value = json.dumps([{
        "insight_text": "Single catalyst needs sentiment cross-check",
        "category": "sentiment",
        "tickers": ["300750.SZ"],
    }])
    lessons = engine.extract_lessons(
        review_summary={"hits": 3, "misses": 1},
        trend_summary={"7d_hit_rate": 0.65},
    )
    assert len(lessons) == 1
    assert lessons[0]["category"] == "sentiment"


def test_apply_rule_proposal_approve(engine):
    proposal = {"proposal_id": "P1", "action": "add", "status": "pending_approval"}
    result = engine.apply_rule_proposal(proposal, approved=True)
    assert result["status"] == "approved"


def test_apply_rule_proposal_reject(engine):
    proposal = {"proposal_id": "P1", "action": "add", "status": "pending_approval"}
    result = engine.apply_rule_proposal(proposal, approved=False, reason="Not needed")
    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "Not needed"
