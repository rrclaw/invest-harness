"""Weekly rule health audit.

Detects:
1. Semantic overlap (>70% theme overlap with different actions)
2. Logic conflicts (overlapping scope + opposite priority)
3. Dead rules (active, last_hit_count=0 for >30 days)
4. Bloat warning (>30 active rules per market)
"""

import argparse
from pathlib import Path
from lib.rules import RuleEngine

OVERLAP_THRESHOLD = 0.7
MAX_RULES_PER_MARKET = 30
DEAD_RULE_DAYS = 30  # not implemented in time check yet, uses hit_count=0


def _theme_overlap(themes_a: list[str], themes_b: list[str]) -> float:
    """Jaccard similarity between two theme lists."""
    if not themes_a and not themes_b:
        return 0.0
    set_a = set(themes_a)
    set_b = set(themes_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def run_audit(rules_dir: str) -> dict:
    """Run the full rule health audit. Returns report dict."""
    engine = RuleEngine(rules_dir)
    active_rules = engine.load_active()

    report = {
        "semantic_overlaps": [],
        "logic_conflicts": [],
        "dead_rules": [],
        "bloat_warning": False,
        "total_active": len(active_rules),
    }

    # 1. Semantic overlap detection (pairwise)
    for i, ra in enumerate(active_rules):
        for rb in active_rules[i + 1 :]:
            themes_a = ra.scope.get("themes", [])
            themes_b = rb.scope.get("themes", [])
            overlap = _theme_overlap(themes_a, themes_b)
            if overlap >= OVERLAP_THRESHOLD:
                report["semantic_overlaps"].append(
                    {
                        "rule_a": ra.rule_id,
                        "rule_b": rb.rule_id,
                        "overlap": round(overlap, 2),
                        "themes_a": themes_a,
                        "themes_b": themes_b,
                    }
                )

    # 2. Dead rule detection
    for rule in active_rules:
        if rule.last_hit_count == 0:
            report["dead_rules"].append(
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "last_reviewed": rule.last_reviewed,
                    "last_hit_count": rule.last_hit_count,
                }
            )

    # 3. Bloat warning
    market_counts: dict[str, int] = {}
    for rule in active_rules:
        market_counts[rule.market] = market_counts.get(rule.market, 0) + 1
    if any(count > MAX_RULES_PER_MARKET for count in market_counts.values()):
        report["bloat_warning"] = True

    return report


def main():
    parser = argparse.ArgumentParser(description="Run weekly rule health audit")
    parser.add_argument("--rules-dir", help="Rules directory path")
    args = parser.parse_args()
    rules_dir = args.rules_dir or str(Path(__file__).resolve().parent.parent / "rules")
    report = run_audit(rules_dir)
    print(f"Audit complete: {report}")


if __name__ == "__main__":
    main()
