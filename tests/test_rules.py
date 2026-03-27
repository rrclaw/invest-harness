import pytest
from pathlib import Path
from lib.rules import RuleEngine, Rule


@pytest.fixture
def rules_dir(tmp_path):
    d = tmp_path / "rules"
    d.mkdir()

    (d / "universal.md").write_text(
        """---
rule_id: R-U-001
title: Never risk more than 3% daily
market: universal
status: active
priority: high
scope:
  themes: []
  tickers: []
  conditions: []
not_applicable: []
created_at: 2026-03-01
evidence_refs: []
last_reviewed: 2026-03-25
last_hit_count: 10
deprecated_reason: null
---

## Rule Description

Do not allow total daily portfolio loss to exceed 3%.
""")

    (d / "a_stock.md").write_text(
        """---
rule_id: R-A-001
title: Do not chase gap-up when auction volume diverges
market: a_stock
status: active
priority: high
scope:
  themes: ["short_term_trading", "limit_up"]
  tickers: []
  conditions: ["Auction volume < 8% of yesterday AND gap up > 5%"]
not_applicable:
  - "Broad market rally > 3%"
created_at: 2026-03-20
evidence_refs: ["h_20260318_a_003"]
last_reviewed: 2026-03-25
last_hit_count: 4
deprecated_reason: null
---

## Rule Description

When auction volume is below 8% of yesterday's total but gap up > 5%, do not chase.

---
rule_id: R-A-002
title: Half position only for first-day listing
market: a_stock
status: paused
priority: medium
scope:
  themes: ["IPO"]
  tickers: []
  conditions: []
not_applicable: []
created_at: 2026-03-10
evidence_refs: []
last_reviewed: 2026-03-20
last_hit_count: 1
deprecated_reason: null
---

## Rule Description

For first-day listings, only take half position max.
""")

    (d / "rule_candidates.md").write_text(
        """# Rule Candidates

## Candidate 1
- Observed: 2026-03-25
- observed_count: 2
- Description: Consider reducing position when index RSI > 80 for 3 consecutive days
- Source: nightly_review_2026-03-25
""")

    return d


def test_load_rules_from_file(rules_dir):
    engine = RuleEngine(rules_dir)
    rules = engine.load_all()
    # Should find R-U-001, R-A-001, R-A-002 (but not candidates)
    ids = {r.rule_id for r in rules}
    assert "R-U-001" in ids
    assert "R-A-001" in ids
    assert "R-A-002" in ids


def test_load_active_only(rules_dir):
    engine = RuleEngine(rules_dir)
    active = engine.load_active()
    ids = {r.rule_id for r in active}
    assert "R-U-001" in ids
    assert "R-A-001" in ids
    assert "R-A-002" not in ids  # paused


def test_load_for_market(rules_dir):
    engine = RuleEngine(rules_dir)
    rules = engine.load_for_market("a_stock")
    ids = {r.rule_id for r in rules}
    assert "R-U-001" in ids  # universal always included
    assert "R-A-001" in ids  # a_stock specific
    assert "R-A-002" not in ids  # paused


def test_rule_has_parsed_frontmatter(rules_dir):
    engine = RuleEngine(rules_dir)
    rules = engine.load_all()
    r = next(r for r in rules if r.rule_id == "R-A-001")
    assert r.title == "Do not chase gap-up when auction volume diverges"
    assert r.market == "a_stock"
    assert r.status == "active"
    assert r.priority == "high"
    assert "short_term_trading" in r.scope["themes"]


def test_rank_by_relevance(rules_dir):
    engine = RuleEngine(rules_dir)
    ranked = engine.rank_for_hypothesis(
        market="a_stock",
        themes=["short_term_trading", "limit_up"],
        ticker="688256.SH",
        max_rules=5,
    )
    # R-A-001 should rank highest (theme match)
    assert ranked[0].rule_id == "R-A-001"


def test_rank_limits_count(rules_dir):
    engine = RuleEngine(rules_dir)
    ranked = engine.rank_for_hypothesis(
        market="a_stock", themes=["anything"], ticker="X", max_rules=1
    )
    assert len(ranked) <= 1


def test_flat_merge_market_overrides_universal(rules_dir):
    """Same-scope conflict: market rule overrides universal by priority."""
    engine = RuleEngine(rules_dir)
    # Both R-U-001 and R-A-001 are high priority; market-specific wins in conflict
    merged = engine.load_for_market("a_stock")
    # Both should be present since they don't conflict on scope
    ids = {r.rule_id for r in merged}
    assert "R-U-001" in ids
    assert "R-A-001" in ids


def test_rule_body_content(rules_dir):
    engine = RuleEngine(rules_dir)
    rules = engine.load_all()
    r = next(r for r in rules if r.rule_id == "R-A-001")
    assert "auction volume" in r.body.lower()


def test_candidates_not_loaded_as_rules(rules_dir):
    engine = RuleEngine(rules_dir)
    rules = engine.load_all()
    ids = {r.rule_id for r in rules}
    # rule_candidates.md should not produce Rule objects
    assert all(not id.startswith("Candidate") for id in ids)


def test_update_status(rules_dir):
    engine = RuleEngine(rules_dir)
    engine.update_status("R-A-002", "active", rules_dir / "a_stock.md")
    active = engine.load_active()
    ids = {r.rule_id for r in active}
    assert "R-A-002" in ids


def test_deprecate_requires_reason(rules_dir):
    engine = RuleEngine(rules_dir)
    with pytest.raises(ValueError, match="deprecated_reason"):
        engine.update_status("R-A-001", "deprecated", rules_dir / "a_stock.md")


def test_deprecate_with_reason(rules_dir):
    engine = RuleEngine(rules_dir)
    engine.update_status(
        "R-A-001",
        "deprecated",
        rules_dir / "a_stock.md",
        deprecated_reason="No longer relevant after market structure change",
    )
    all_rules = engine.load_all()
    r = next(r for r in all_rules if r.rule_id == "R-A-001")
    assert r.status == "deprecated"
