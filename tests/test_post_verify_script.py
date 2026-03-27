import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from scripts.post_verify import run_post_verify


def test_run_post_verify_writes_result(tmp_path):
    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()

    hypothesis = {
        "hypothesis_id": "h_20260326_a_001",
        "market": "a_stock",
        "ticker": "688256.SH",
        "company": "Cambricon",
        "status": "locked",
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
        "invalidation_conditions": ["Volume < 5%"],
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

    actuals = {
        "close_change_pct": 6.8,
        "direction": "up",
        "peak_time": "09:35-10:15",
        "invalidation_triggered": False,
        "market_cause": "Policy catalyst",
        "market_cause_evidence": ["f_20260326_018"],
    }

    result = run_post_verify(
        hypothesis=hypothesis,
        actuals=actuals,
        date="2026-03-26",
        reviews_dir=str(reviews_dir),
    )
    assert result["verdict"] == "hit"

    # Check file was written
    review_path = reviews_dir / "2026-03-26" / "post_market_a_stock.json"
    assert review_path.exists()
    saved = json.loads(review_path.read_text())
    assert saved["verdict"] == "hit"
