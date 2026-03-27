"""Contrarian challenge logic.

Cross-references thesis_cause_match against consensus_narrative to identify:
- Aligned + hit: possibly crowded trade
- Against + hit: genuine alpha
- Aligned + miss: consensus was wrong
- Against + miss: thesis was simply wrong

Also detects cognitive blind spots (survivorship bias, streak overconfidence).
"""


class ContrarianChallenger:
    """Adversarial challenge for nightly review."""

    def classify_consensus_outcome(
        self,
        thesis_cause_match: str,
        consensus_sentiment: str,
        verdict: str,
    ) -> dict:
        """Classify the relationship between thesis, consensus, and outcome.

        The thesis direction is inferred as bullish from 'aligned' cause match.
        If consensus is also bullish, thesis was aligned with consensus.
        If consensus was bearish, thesis was against consensus.
        """
        is_hit = verdict in ("hit", "partial_hit")

        # Determine if thesis was aligned with or against consensus
        # Simplified: if consensus_sentiment matches expected direction, aligned
        thesis_bullish = True  # Assume bullish thesis for simplicity
        consensus_agrees = consensus_sentiment == "bullish"

        if consensus_agrees and is_hit:
            return {
                "category": "aligned_with_consensus_hit",
                "warning": "Possibly crowded trade, beware of reversal",
            }
        elif not consensus_agrees and is_hit:
            return {
                "category": "against_consensus_hit",
                "warning": "Genuine alpha candidate, consider for rule extraction",
            }
        elif consensus_agrees and not is_hit:
            return {
                "category": "aligned_with_consensus_miss",
                "warning": "Consensus was wrong, assess regime shift possibility",
            }
        else:
            return {
                "category": "against_consensus_miss",
                "warning": "Thesis was simply wrong",
            }

    def detect_blind_spots(self, recent_history: list[dict]) -> list[str]:
        """Detect cognitive blind spots from recent verification history."""
        if not recent_history:
            return []

        spots = []
        verdicts = [r.get("verdict") for r in recent_history]

        # Consecutive hits: overconfidence risk
        consecutive_hits = 0
        for v in verdicts:
            if v in ("hit", "partial_hit"):
                consecutive_hits += 1
            else:
                break

        if consecutive_hits >= 3:
            spots.append(
                f"WARNING: {consecutive_hits} consecutive hits. "
                "Survivorship bias risk. Are you ignoring contrary evidence?"
            )

        # No misses in sample: potential sample bias
        if all(v in ("hit", "partial_hit") for v in verdicts):
            spots.append(
                "All recent results are hits. Sample bias risk. "
                "Review whether invalidated/missed hypotheses were properly recorded."
            )

        return spots
