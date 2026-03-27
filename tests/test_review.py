import pytest
from lib.review import ReviewGenerator


def _make_verify_result(hypothesis_id, verdict, cause_match, score_earned, stat_eligible=True):
    return {
        "hypothesis_ref": hypothesis_id,
        "market": "a_stock",
        "ticker": "688256.SH",
        "stat_eligible": stat_eligible,
        "verdict": verdict,
        "scenario_matched": "bull",
        "dimensions": {
            "direction": {"predicted": "up", "actual": "up", "score": 1},
            "magnitude": {"predicted_range": [5.0, 100.0], "actual": 6.8, "score": 1},
            "time_window": {"expected": "09:30-10:30", "actual": "09:35-10:15", "score": 1},
            "cause": {
                "thesis_cause_match": cause_match,
                "market_cause": "test cause",
            },
        },
        "invalidation_review": {"any_triggered": False},
        "action_review": {
            "execution_ref": None,
            "plan_followed": True,
            "deviation": None,
            "execution_alpha": "+1.0%",
            "thesis_vs_execution": "thesis_correct_execution_good",
        },
        "score": {"earned": score_earned, "possible": 4, "direction": 1, "magnitude": 1, "time_window": 1, "cause": 1},
        "rule_violations": [],
        "regime_shift_alerts": [],
    }


def test_categorize_true_hit():
    gen = ReviewGenerator()
    results = [_make_verify_result("h1", "hit", "aligned", 4)]
    report = gen.categorize(results)
    assert len(report["true_hits"]) == 1
    assert len(report["lucky_hits"]) == 0


def test_categorize_lucky_hit():
    gen = ReviewGenerator()
    results = [_make_verify_result("h1", "hit", "lucky", 4)]
    report = gen.categorize(results)
    assert len(report["lucky_hits"]) == 1
    assert len(report["true_hits"]) == 0


def test_categorize_true_miss():
    gen = ReviewGenerator()
    results = [_make_verify_result("h1", "miss", "unknown", 0)]
    report = gen.categorize(results)
    assert len(report["true_misses"]) == 1


def test_categorize_partial_hit():
    gen = ReviewGenerator()
    results = [_make_verify_result("h1", "partial_hit", "aligned", 2)]
    report = gen.categorize(results)
    assert len(report["true_hits"]) == 1  # partial with aligned cause = true hit category


def test_categorize_unconfirmed():
    gen = ReviewGenerator()
    results = [_make_verify_result("h1", "unconfirmed", "unknown", 0, stat_eligible=False)]
    report = gen.categorize(results)
    assert len(report["unconfirmed"]) == 1


def test_execution_gaps():
    gen = ReviewGenerator()
    r = _make_verify_result("h1", "hit", "aligned", 4)
    r["action_review"]["thesis_vs_execution"] = "thesis_correct_execution_bad"
    r["action_review"]["execution_alpha"] = "-2.0%"
    results = [r]
    report = gen.categorize(results)
    assert len(report["execution_gaps"]) == 1


def test_generate_markdown():
    gen = ReviewGenerator()
    results = [
        _make_verify_result("h1", "hit", "aligned", 4),
        _make_verify_result("h2", "miss", "unknown", 0),
    ]
    md = gen.generate_markdown(results, "2026-03-26")
    assert "# Cross-Market Unified Review" in md
    assert "2026-03-26" in md
    assert "True Hits" in md
    assert "True Misses" in md
    assert "Human Verdict" in md


def test_mixed_results():
    gen = ReviewGenerator()
    results = [
        _make_verify_result("h1", "hit", "aligned", 4),
        _make_verify_result("h2", "hit", "lucky", 3),
        _make_verify_result("h3", "miss", "unknown", 0),
        _make_verify_result("h4", "unconfirmed", "unknown", 0, stat_eligible=False),
    ]
    report = gen.categorize(results)
    assert len(report["true_hits"]) == 1
    assert len(report["lucky_hits"]) == 1
    assert len(report["true_misses"]) == 1
    assert len(report["unconfirmed"]) == 1
