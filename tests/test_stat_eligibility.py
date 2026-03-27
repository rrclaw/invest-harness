import pytest
from lib.stat_eligibility import check_eligibility


def test_locked_with_full_audit():
    result = check_eligibility(
        status="locked",
        audit={
            "model_version": "claude-opus-4-6",
            "prompt_hash": "sha256:abc",
            "generated_at": "2026-03-26T07:35:00",
            "prompt_ref": "prompts/hypothesis_gen.md@v1",
            "fallback_used": False,
            "fallback_from": None,
            "idempotency_key": "key1",
        },
        amend_log=[],
        fallback_used=False,
        invalidation_type=None,
    )
    assert result["stat_eligible"] is True
    assert result["win_rate_pool"] is True
    assert result["rule_iteration_pool"] is True
    assert result["backtest_pool"] is True


def test_unconfirmed_excluded():
    result = check_eligibility(
        status="unconfirmed",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": False, "fallback_from": None,
               "idempotency_key": "x"},
        amend_log=[],
        fallback_used=False,
        invalidation_type=None,
    )
    assert result["stat_eligible"] is False
    assert result["win_rate_pool"] is False
    assert result["rule_iteration_pool"] is False
    assert result["backtest_pool"] is False


def test_amended_with_complete_log():
    result = check_eligibility(
        status="amended",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": False, "fallback_from": None,
               "idempotency_key": "x"},
        amend_log=[{"reason": "shareholder reduction", "amended_by": "human"}],
        fallback_used=False,
        invalidation_type=None,
    )
    assert result["stat_eligible"] is True
    assert result["win_rate_pool"] is True
    assert result["backtest_pool"] is False


def test_amended_with_empty_log():
    result = check_eligibility(
        status="amended",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": False, "fallback_from": None,
               "idempotency_key": "x"},
        amend_log=[],
        fallback_used=False,
        invalidation_type=None,
    )
    assert result["stat_eligible"] is False
    assert result["reason"] == "amended but amend_log is empty"


def test_fallback_used():
    result = check_eligibility(
        status="locked",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": True, "fallback_from": "claude",
               "idempotency_key": "x"},
        amend_log=[],
        fallback_used=True,
        invalidation_type=None,
    )
    assert result["win_rate_pool"] is True
    assert result["rule_iteration_pool"] is False
    assert result["backtest_pool"] is False


def test_pre_trigger_invalidated():
    result = check_eligibility(
        status="locked",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": False, "fallback_from": None,
               "idempotency_key": "x"},
        amend_log=[],
        fallback_used=False,
        invalidation_type="pre_trigger",
    )
    assert result["win_rate_pool"] is False
    assert result["rule_iteration_pool"] is True
    assert result["backtest_pool"] is False


def test_post_trigger_invalidated():
    result = check_eligibility(
        status="locked",
        audit={"model_version": "x", "prompt_hash": "x", "generated_at": "x",
               "prompt_ref": "x", "fallback_used": False, "fallback_from": None,
               "idempotency_key": "x"},
        amend_log=[],
        fallback_used=False,
        invalidation_type="post_trigger",
    )
    assert result["win_rate_pool"] is True
    assert result["rule_iteration_pool"] is True
    assert result["backtest_pool"] is True


def test_incomplete_audit():
    result = check_eligibility(
        status="locked",
        audit={"model_version": "x"},
        amend_log=[],
        fallback_used=False,
        invalidation_type=None,
    )
    assert result["stat_eligible"] is False
    assert "incomplete" in result["reason"].lower()
