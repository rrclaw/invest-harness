"""Hypothesis CRUD, locking, and amendment.

Iron Law 1: Once _lock.{market} exists, NO script may modify the locked hypothesis.
Only the amendment flow (human deletes lock -> system detects -> amend) can modify.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from lib.schema_validator import validate


class HypothesisManager:
    """Manages hypothesis lifecycle: draft -> lock -> amend."""

    def __init__(self, hypotheses_dir: str | Path):
        self._dir = Path(hypotheses_dir)

    def _day_dir(self, date: str) -> Path:
        d = self._dir / date
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _hypo_path(self, date: str, market: str) -> Path:
        return self._day_dir(date) / f"{market}.json"

    def _lock_path(self, date: str, market: str) -> Path:
        return self._day_dir(date) / f"_lock.{market}"

    def is_locked(self, date: str, market: str) -> bool:
        return self._lock_path(date, market).exists()

    def save_draft(self, hypothesis: dict, date: str) -> None:
        """Save a hypothesis draft. Raises if market is locked."""
        market = hypothesis["market"]
        if self.is_locked(date, market):
            raise PermissionError(
                f"Cannot modify {market} hypothesis for {date}: locked. "
                "Delete _lock file to amend."
            )
        validate(hypothesis, "hypothesis")
        path = self._hypo_path(date, market)
        path.write_text(json.dumps(hypothesis, ensure_ascii=False, indent=2))

    def load_for_date(self, date: str, market: str) -> dict | None:
        """Load hypothesis for a given date and market. Returns None if not found."""
        path = self._hypo_path(date, market)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_for_date(self, date: str) -> list[dict]:
        """Load all hypotheses for a given date."""
        day_dir = self._dir / date
        if not day_dir.exists():
            return []
        results = []
        for path in sorted(day_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            results.append(json.loads(path.read_text()))
        return results

    def lock(self, date: str, market: str, approved_by: str) -> None:
        """Lock a hypothesis after human approval."""
        hypo = self.load_for_date(date, market)
        if hypo is None:
            raise FileNotFoundError(f"No hypothesis for {market} on {date}")

        now = datetime.now(timezone.utc).isoformat()
        hypo["status"] = "locked"
        hypo["locked_at"] = now
        hypo["approved_by"] = approved_by

        path = self._hypo_path(date, market)
        path.write_text(json.dumps(hypo, ensure_ascii=False, indent=2))

        # Create lock file
        self._lock_path(date, market).write_text(now)

    def mark_unconfirmed(self, date: str, market: str) -> None:
        """Mark hypothesis as unconfirmed (approval timeout)."""
        hypo = self.load_for_date(date, market)
        if hypo is None:
            raise FileNotFoundError(f"No hypothesis for {market} on {date}")
        hypo["status"] = "unconfirmed"
        path = self._hypo_path(date, market)
        path.write_text(json.dumps(hypo, ensure_ascii=False, indent=2))

    def amend(
        self,
        date: str,
        market: str,
        reason: str,
        original_action: str,
        revised_action: str,
        amended_by: str,
    ) -> None:
        """Amend a hypothesis after human deletes lock file.

        Raises PermissionError if lock file still exists (Iron Law 1).
        """
        if self.is_locked(date, market):
            raise PermissionError(
                f"Cannot amend {market} on {date}: lock file still exists. "
                "Human must delete _lock.{market} first."
            )

        hypo = self.load_for_date(date, market)
        if hypo is None:
            raise FileNotFoundError(f"No hypothesis for {market} on {date}")

        now = datetime.now(timezone.utc).isoformat()
        hypo["status"] = "amended"
        hypo["amend_log"].append(
            {
                "amended_at": now,
                "reason": reason,
                "original_action": original_action,
                "revised_action": revised_action,
                "amended_by": amended_by,
            }
        )

        path = self._hypo_path(date, market)
        path.write_text(json.dumps(hypo, ensure_ascii=False, indent=2))
