"""Feedback Engine -- closed-loop weight adjustment, rule proposals, lesson extraction."""

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_WEIGHT = 0.7
HIT_MULTIPLIER = 1.05
MISS_MULTIPLIER = 0.90
WEIGHT_CAP = 1.0
WEIGHT_FLOOR = 0.1


class FeedbackEngine:
    def __init__(self, *, knowledge, chroma, llm_call, rules):
        self._knowledge = knowledge
        self._chroma = chroma
        self._llm_call = llm_call
        self._rules = rules

    def adjust_weights(self, verify_results: list[dict]) -> list[dict]:
        """Adjust knowledge source weights based on verification verdicts.

        hit -> weight *= 1.05 (cap 1.0)
        miss -> weight *= 0.90 (floor 0.1)
        partial_hit / invalidated -> no change
        """
        adjustments = []
        for vr in verify_results:
            verdict = vr.get("verdict")
            if verdict not in ("hit", "miss"):
                continue
            multiplier = HIT_MULTIPLIER if verdict == "hit" else MISS_MULTIPLIER
            for fact_id in vr.get("evidence_fact_ids", []):
                old_weight = DEFAULT_SOURCE_WEIGHT
                new_weight = max(WEIGHT_FLOOR, min(WEIGHT_CAP, old_weight * multiplier))
                success = self._knowledge.update_source_weight(fact_id, new_weight)
                if success:
                    adjustments.append({
                        "fact_id": fact_id,
                        "old_weight": old_weight,
                        "new_weight": new_weight,
                        "reason": verdict,
                        "hypothesis_ref": vr.get("hypothesis_ref"),
                    })
        return adjustments

    def generate_rule_proposals(self, misses: list[dict]) -> list[dict]:
        """Use LLM to propose rule changes based on misses."""
        if not misses:
            return []

        prompt_path = Path(__file__).parent.parent / "prompts" / "rule_proposal.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""
        prompt = prompt.replace("{misses}", json.dumps(misses, ensure_ascii=False, default=str))
        prompt = prompt.replace("{rules}", json.dumps(
            [{"rule_id": r.rule_id, "title": r.title, "body": r.body}
             for r in self._rules] if self._rules else [],
            ensure_ascii=False,
        ))

        try:
            raw = self._llm_call(prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            proposals = json.loads(raw[start:end]) if start >= 0 else []
        except Exception:
            logger.error("Failed to parse rule proposals from LLM")
            return []

        for p in proposals:
            p["proposal_id"] = str(uuid.uuid4())
            p["status"] = "pending_approval"

        return proposals

    def extract_lessons(self, *, review_summary: dict, trend_summary: dict) -> list[dict]:
        """Use LLM to extract reusable lessons from review."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "lesson_extract.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""
        prompt = prompt.replace("{review}", json.dumps(review_summary, ensure_ascii=False, default=str))
        prompt = prompt.replace("{trend}", json.dumps(trend_summary, ensure_ascii=False, default=str))

        existing = []
        try:
            if self._knowledge:
                insights_path = Path(self._knowledge._dir) / "curated" / "insights.jsonl"
                if insights_path.exists():
                    existing = [json.loads(l) for l in insights_path.read_text().strip().split("\n") if l.strip()]
        except Exception:
            pass
        prompt = prompt.replace("{existing_insights}", json.dumps(existing[-20:], ensure_ascii=False, default=str))

        try:
            raw = self._llm_call(prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            lessons = json.loads(raw[start:end]) if start >= 0 else []
        except Exception:
            logger.error("Failed to parse lessons from LLM")
            return []

        for lesson in lessons:
            try:
                if self._knowledge:
                    self._knowledge.add_curated_insight(lesson)
            except Exception:
                logger.warning(f"Failed to save insight: {lesson.get('insight_text', '?')[:50]}")

        return lessons

    def apply_rule_proposal(self, proposal: dict, *, approved: bool,
                            reason: str | None = None) -> dict:
        """Apply or reject a rule proposal."""
        if approved:
            proposal["status"] = "approved"
        else:
            proposal["status"] = "rejected"
            proposal["rejection_reason"] = reason
        return proposal
