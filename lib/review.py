"""Nightly review generator.

Produces the mandatory review structure:
1. True Hits, 2. Lucky Hits, 3. True Misses, 4. Execution Gaps,
5. Unconfirmed, 6. Rule Violations, 7. Regime Shift Alerts,
8. Contrarian Challenge, 9. Human Verdict.
"""


class ReviewGenerator:
    """Categorizes verification results and generates review markdown."""

    def categorize(self, verify_results: list[dict]) -> dict:
        """Categorize results into review buckets."""
        report = {
            "true_hits": [],
            "lucky_hits": [],
            "true_misses": [],
            "execution_gaps": [],
            "unconfirmed": [],
            "rule_violations": [],
            "regime_shift_alerts": [],
        }

        for r in verify_results:
            verdict = r["verdict"]
            cause_match = r.get("dimensions", {}).get("cause", {}).get("thesis_cause_match", "unknown")
            exec_review = r.get("action_review", {})
            thesis_exec = exec_review.get("thesis_vs_execution", "")

            # Unconfirmed
            if verdict == "unconfirmed" or not r.get("stat_eligible", True):
                report["unconfirmed"].append(r)
                continue

            # Execution gaps (any _bad suffix)
            if "execution_bad" in thesis_exec:
                report["execution_gaps"].append(r)

            # Rule violations
            if r.get("rule_violations"):
                report["rule_violations"].extend(r["rule_violations"])

            # Regime shift alerts
            if r.get("regime_shift_alerts"):
                report["regime_shift_alerts"].extend(r["regime_shift_alerts"])

            # Categorize by verdict + cause match
            if verdict in ("hit", "partial_hit"):
                if cause_match == "lucky":
                    report["lucky_hits"].append(r)
                else:
                    report["true_hits"].append(r)
            elif verdict == "miss":
                report["true_misses"].append(r)
            # invalidated: not categorized as hit/miss

        return report

    def generate_markdown(self, verify_results: list[dict], date: str) -> str:
        """Generate the mandatory nightly review markdown."""
        report = self.categorize(verify_results)

        sections = [f"# Cross-Market Unified Review -- {date}\n"]

        # Section 1: True Hits
        sections.append("## 1. True Hits (Hit List)")
        sections.append("| Hypothesis | Market | Score | thesis_cause_match |")
        sections.append("|---|---|---|---|")
        for r in report["true_hits"]:
            cause = r.get("dimensions", {}).get("cause", {}).get("thesis_cause_match", "")
            sections.append(
                f"| {r['hypothesis_ref']} | {r['market']} | {r['score']['earned']}/{r['score']['possible']} | {cause} |"
            )
        sections.append("")

        # Section 2: Lucky Hits
        sections.append("## 2. Lucky Hits")
        sections.append("| Hypothesis | Market | Score | Lucky Reason |")
        sections.append("|---|---|---|---|")
        for r in report["lucky_hits"]:
            sections.append(
                f"| {r['hypothesis_ref']} | {r['market']} | {r['score']['earned']}/{r['score']['possible']} | Direction correct, cause mismatch |"
            )
        sections.append("")

        # Section 3: True Misses
        sections.append("## 3. True Misses")
        sections.append("| Hypothesis | Market | Score | Core Misjudgment |")
        sections.append("|---|---|---|---|")
        for r in report["true_misses"]:
            cause = r.get("dimensions", {}).get("cause", {}).get("market_cause", "unknown")
            sections.append(
                f"| {r['hypothesis_ref']} | {r['market']} | {r['score']['earned']}/{r['score']['possible']} | {cause} |"
            )
        sections.append("")

        # Section 4: Execution Gaps
        sections.append("## 4. Execution Gaps")
        sections.append("| Hypothesis | thesis_vs_execution | execution_alpha | Deviation |")
        sections.append("|---|---|---|---|")
        for r in report["execution_gaps"]:
            ar = r.get("action_review", {})
            sections.append(
                f"| {r['hypothesis_ref']} | {ar.get('thesis_vs_execution', '')} | {ar.get('execution_alpha', '')} | {ar.get('deviation', '')} |"
            )
        sections.append("")

        # Section 5: Unconfirmed
        sections.append("## 5. Unconfirmed (Unaudited)")
        sections.append("<!-- stat_eligible = false, for reference only -->")
        for r in report["unconfirmed"]:
            sections.append(f"- {r['hypothesis_ref']} ({r['market']})")
        sections.append("")

        # Section 6: Rule Violation Log
        sections.append("## 6. Rule Violation Log")
        sections.append("| Hypothesis | Violated Rule | Violation Type | Consequence | Loss Attribution |")
        sections.append("|---|---|---|---|---|")
        sections.append("")

        # Section 7: Regime Shift Alerts
        sections.append("## 7. Regime Shift Alerts")
        sections.append("| Rule | Consecutive Compliance | Consecutive Misses | Alert |")
        sections.append("|---|---|---|---|")
        sections.append("### AI Analysis")
        sections.append("<!-- When a rule is strictly followed but leads to consecutive misses -->")
        sections.append("")

        # Section 8: Contrarian Challenge
        sections.append("## 8. Contrarian Challenge")
        sections.append("### Cognitive Blind Spots")
        sections.append("- [ ] <!-- To be filled by contrarian AI -->")
        sections.append("### Survivorship Bias")
        sections.append("- [ ] <!-- Which hits might be sample bias -->")
        sections.append("### Open Questions")
        sections.append("- [ ] <!-- Questions requiring follow-up -->")
        sections.append("")

        # Section 9: Human Verdict
        sections.append("## 9. Human Verdict")
        sections.append("<!-- Left blank, appended after human replies -->")

        return "\n".join(sections)
