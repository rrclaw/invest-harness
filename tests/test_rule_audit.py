import pytest
from pathlib import Path
from lib.rules import RuleEngine, Rule
from scripts.rule_audit import run_audit


@pytest.fixture
def rules_with_issues(tmp_path):
    d = tmp_path / "rules"
    d.mkdir()

    # Two overlapping rules
    (d / "a_stock.md").write_text(
        """---
rule_id: R-A-001
title: Do not chase gap-up when auction volume low
market: a_stock
status: active
priority: high
scope:
  themes: ["short_term_trading", "limit_up"]
  tickers: []
  conditions: ["gap up > 5%"]
not_applicable: []
created_at: 2026-03-01
evidence_refs: []
last_reviewed: 2026-03-25
last_hit_count: 5
deprecated_reason: null
---

Do not chase.

---
rule_id: R-A-002
title: Avoid gap-up chasing with low volume
market: a_stock
status: active
priority: medium
scope:
  themes: ["short_term_trading", "limit_up"]
  tickers: []
  conditions: ["gap up > 4%"]
not_applicable: []
created_at: 2026-03-05
evidence_refs: []
last_reviewed: 2026-03-20
last_hit_count: 0
deprecated_reason: null
---

Avoid chasing.

---
rule_id: R-A-003
title: Dead rule nobody uses
market: a_stock
status: active
priority: low
scope:
  themes: ["crypto"]
  tickers: []
  conditions: []
not_applicable: []
created_at: 2026-01-01
evidence_refs: []
last_reviewed: 2026-01-15
last_hit_count: 0
deprecated_reason: null
---

This rule has never triggered.
""")

    (d / "universal.md").write_text("")
    (d / "rule_candidates.md").write_text("# Candidates\n")
    return d


def test_detect_semantic_overlap(rules_with_issues):
    report = run_audit(str(rules_with_issues))
    overlaps = report["semantic_overlaps"]
    # R-A-001 and R-A-002 have >70% theme overlap
    assert len(overlaps) >= 1
    ids = {(o["rule_a"], o["rule_b"]) for o in overlaps}
    assert ("R-A-001", "R-A-002") in ids or ("R-A-002", "R-A-001") in ids


def test_detect_dead_rules(rules_with_issues):
    report = run_audit(str(rules_with_issues))
    dead = report["dead_rules"]
    ids = {d["rule_id"] for d in dead}
    assert "R-A-003" in ids  # last_hit_count=0


def test_bloat_warning(rules_with_issues):
    report = run_audit(str(rules_with_issues))
    # 3 rules is under 30 threshold
    assert report["bloat_warning"] is False
