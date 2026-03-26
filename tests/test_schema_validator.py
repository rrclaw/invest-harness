import pytest
from lib.schema_validator import validate, ValidationError


def test_validate_valid_fact():
    fact = {
        "fact_id": "f_20260326_001",
        "fact": "Cambricon Q4 revenue 2.54B",
        "company": ["Cambricon"],
        "tickers": ["688256.SH"],
        "topic": "quarterly_revenue",
        "as_of": "2025-12-31",
        "date": "2026-03-26",
        "source_ref": "raw/2026-03-26/test.pdf",
        "source_type": "company_research",
        "confidence": 0.95,
        "decay_class": "financial",
        "tags": ["earnings"],
        "status": "active",
        "supersedes": None,
        "supersede_type": None,
    }
    # Should not raise
    validate(fact, "fact")


def test_validate_invalid_fact_missing_field():
    fact = {"fact_id": "f_20260326_001"}
    with pytest.raises(ValidationError):
        validate(fact, "fact")


def test_validate_invalid_source_type():
    fact = {
        "fact_id": "f_20260326_001",
        "fact": "Test",
        "company": ["X"],
        "tickers": ["X"],
        "topic": "t",
        "as_of": "2025-12-31",
        "date": "2026-03-26",
        "source_ref": "raw/test",
        "source_type": "INVALID_TYPE",
        "confidence": 0.5,
        "decay_class": "ephemeral",
        "tags": [],
        "status": "active",
        "supersedes": None,
        "supersede_type": None,
    }
    with pytest.raises(ValidationError):
        validate(fact, "fact")


def test_validate_hypothesis_valid():
    hypo = {
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
    validate(hypo, "hypothesis")


def test_validate_unknown_schema_raises():
    with pytest.raises(FileNotFoundError):
        validate({}, "nonexistent_schema")
