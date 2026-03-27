"""Rule engine: load, merge, rank, and lifecycle management.

Rules are YAML-frontmatter Markdown files. Flat composition (no OOP inheritance).
Load order: universal.md -> {market}.md -> flat merge -> rank by relevance -> inject top N.

Iron Law 2: Non-human-triggered rule writes are absolutely forbidden.
This module provides read + status update only. Writes happen via approval flow.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Rule:
    rule_id: str
    title: str
    market: str
    status: str
    priority: str
    scope: dict
    not_applicable: list
    created_at: str
    evidence_refs: list
    last_reviewed: str
    last_hit_count: int
    deprecated_reason: str | None
    body: str
    source_file: str


# Regex to split multiple rules in a single file (separated by ---)
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*?)(?=\n---\s*\n|\Z)",
    re.DOTALL | re.MULTILINE,
)


class RuleEngine:
    """Loads, merges, and ranks investment rules."""

    def __init__(self, rules_dir: str | Path):
        self._dir = Path(rules_dir)

    def _parse_file(self, path: Path) -> list[Rule]:
        """Parse a rule file with one or more YAML-frontmatter sections."""
        if path.name == "rule_candidates.md":
            return []  # Candidates are NOT rules

        content = path.read_text()
        rules = []

        for match in _FRONTMATTER_RE.finditer(content):
            fm_text = match.group(1)
            body = match.group(2).strip()
            try:
                fm = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                continue

            if not isinstance(fm, dict) or "rule_id" not in fm:
                continue

            rules.append(
                Rule(
                    rule_id=fm["rule_id"],
                    title=fm.get("title", ""),
                    market=fm.get("market", "universal"),
                    status=fm.get("status", "draft"),
                    priority=fm.get("priority", "medium"),
                    scope=fm.get("scope", {}),
                    not_applicable=fm.get("not_applicable", []),
                    created_at=str(fm.get("created_at", "")),
                    evidence_refs=fm.get("evidence_refs", []),
                    last_reviewed=str(fm.get("last_reviewed", "")),
                    last_hit_count=fm.get("last_hit_count", 0),
                    deprecated_reason=fm.get("deprecated_reason"),
                    body=body,
                    source_file=str(path),
                )
            )

        return rules

    def load_all(self) -> list[Rule]:
        """Load all rules from all files (all statuses)."""
        rules = []
        for path in sorted(self._dir.glob("*.md")):
            rules.extend(self._parse_file(path))
        return rules

    def load_active(self) -> list[Rule]:
        """Load only active rules."""
        return [r for r in self.load_all() if r.status == "active"]

    def load_for_market(self, market: str) -> list[Rule]:
        """Load active rules for a market: universal + market-specific."""
        active = self.load_active()
        return [
            r
            for r in active
            if r.market in ("universal", market)
        ]

    def rank_for_hypothesis(
        self,
        market: str,
        themes: list[str],
        ticker: str,
        max_rules: int = 10,
    ) -> list[Rule]:
        """Rank active rules by relevance to a hypothesis and return top N.

        Relevance scoring:
        - Theme overlap: +2 per matching theme
        - Ticker match: +3
        - Market specific > universal: +1
        - Priority high: +1
        """
        candidates = self.load_for_market(market)
        scored = []
        for rule in candidates:
            score = 0
            rule_themes = set(rule.scope.get("themes", []))
            score += 2 * len(rule_themes.intersection(themes))
            rule_tickers = rule.scope.get("tickers", [])
            if ticker in rule_tickers:
                score += 3
            if rule.market != "universal":
                score += 1
            if rule.priority == "high":
                score += 1
            scored.append((score, rule))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:max_rules]]

    def update_status(
        self,
        rule_id: str,
        new_status: str,
        source_file: str | Path,
        deprecated_reason: str | None = None,
    ) -> None:
        """Update a rule's status in its source file.

        This MUST only be called from the approval flow (Iron Law 2).
        """
        if new_status == "deprecated" and not deprecated_reason:
            raise ValueError(
                "deprecated_reason is required when deprecating a rule"
            )

        path = Path(source_file)
        content = path.read_text()

        # Find and replace the status field for the specific rule
        # Simple approach: find the frontmatter block for this rule_id
        pattern = re.compile(
            rf"(---\s*\nrule_id:\s*{re.escape(rule_id)}\n.*?)(status:\s*\w+)(.*?\n---)",
            re.DOTALL,
        )

        def replacer(match):
            before = match.group(1)
            after = match.group(3)
            new_line = f"status: {new_status}"
            result = before + new_line + after
            if deprecated_reason and "deprecated_reason:" in result:
                result = re.sub(
                    r"deprecated_reason:.*",
                    f"deprecated_reason: {deprecated_reason}",
                    result,
                )
            return result

        new_content = pattern.sub(replacer, content)
        path.write_text(new_content)
