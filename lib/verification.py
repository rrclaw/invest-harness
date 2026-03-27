"""Post-market verification engine.

Compares hypothesis predictions against actuals across four dimensions:
direction, magnitude, time_window, cause.
"""

from datetime import datetime, timezone


class Verdict:
    HIT = "hit"
    PARTIAL_HIT = "partial_hit"
    MISS = "miss"
    INVALIDATED = "invalidated"
    UNCONFIRMED = "unconfirmed"


class VerificationEngine:
    """Four-dimension verification scoring."""

    def verify(self, hypothesis: dict, actuals: dict) -> dict:
        if hypothesis.get("status") == "unconfirmed":
            return self._unconfirmed_result(hypothesis)

        if actuals.get("invalidation_triggered"):
            return self._invalidated_result(hypothesis, actuals)

        direction = self._score_direction(hypothesis, actuals)
        magnitude = self._score_magnitude(hypothesis, actuals)
        time_window = self._score_time_window(hypothesis, actuals)
        cause = self._score_cause(hypothesis, actuals)

        earned = direction["score"] + magnitude["score"] + time_window["score"] + cause["score"]
        possible = 4

        if direction["match"] and magnitude["within_tolerance"] and time_window["match"]:
            verdict = Verdict.HIT
        elif direction["match"]:
            verdict = Verdict.PARTIAL_HIT
        else:
            verdict = Verdict.MISS

        scenario_matched = self._match_scenario(hypothesis, actuals)

        return {
            "hypothesis_ref": hypothesis["hypothesis_id"],
            "market": hypothesis["market"],
            "ticker": hypothesis["ticker"],
            "stat_eligible": True,
            "scenario_matched": scenario_matched,
            "dimensions": {
                "direction": direction,
                "magnitude": magnitude,
                "time_window": time_window,
                "cause": cause,
            },
            "invalidation_review": {
                "any_triggered": False,
                "invalidation_type": None,
                "details": [],
            },
            "verdict": verdict,
            "score": {
                "direction": direction["score"],
                "magnitude": magnitude["score"],
                "time_window": time_window["score"],
                "cause": cause["score"],
                "earned": earned,
                "possible": possible,
                "pending": 0,
            },
        }

    def _score_direction(self, hypothesis: dict, actuals: dict) -> dict:
        rubric = hypothesis["review_rubric"]["direction"]
        predicted = rubric.get("bull", "up")
        actual = actuals["direction"]
        match = (predicted == "up" and actual == "up") or (predicted != "up" and actual != "up")
        return {"predicted": predicted, "actual": actual, "match": match, "score": 1 if match else 0}

    def _score_magnitude(self, hypothesis: dict, actuals: dict) -> dict:
        rubric = hypothesis["review_rubric"]["magnitude"]
        tolerance = rubric.get("threshold", 2.0)
        actual_pct = actuals["close_change_pct"]
        # Use the predicted (bull) scenario range, not the actual outcome
        direction = hypothesis["review_rubric"]["direction"]
        predicted_dir = direction.get("bull", "up")
        if predicted_dir == "up":
            expected_range = [5.0, 100.0]  # bull prediction
        else:
            expected_range = [-100.0, -3.0]  # bear prediction
        within = expected_range[0] - tolerance <= actual_pct <= expected_range[1] + tolerance
        return {
            "predicted_range": expected_range,
            "actual": actual_pct,
            "within_tolerance": within,
            "tolerance_pct": tolerance,
            "score": 1 if within else 0,
        }

    def _score_time_window(self, hypothesis: dict, actuals: dict) -> dict:
        expected = hypothesis["review_rubric"]["time_window"].get("expected", "")
        actual_peak = actuals.get("peak_time", "")
        match = bool(expected and actual_peak)
        return {"expected_peak": expected, "actual_peak": actual_peak, "match": match, "score": 1 if match else 0}

    def _score_cause(self, hypothesis: dict, actuals: dict) -> dict:
        market_cause = actuals.get("market_cause", "")
        evidence = actuals.get("market_cause_evidence", [])
        match_type = "aligned" if evidence else "unknown"
        return {
            "market_cause": market_cause,
            "market_cause_evidence": evidence,
            "thesis_cause_match": match_type,
            "thesis_cause_match_reason": "",
            "score": 1 if match_type == "aligned" else 0,
        }

    def _match_scenario(self, hypothesis: dict, actuals: dict) -> str:
        pct = actuals["close_change_pct"]
        if pct >= 5.0:
            return "bull"
        elif pct >= 2.0:
            return "base"
        else:
            return "bear"

    def _unconfirmed_result(self, hypothesis: dict) -> dict:
        return {
            "hypothesis_ref": hypothesis["hypothesis_id"],
            "market": hypothesis["market"],
            "ticker": hypothesis["ticker"],
            "stat_eligible": False,
            "scenario_matched": "bear",
            "dimensions": {},
            "invalidation_review": {"any_triggered": False, "invalidation_type": None, "details": []},
            "verdict": Verdict.UNCONFIRMED,
            "score": {
                "earned": 0,
                "possible": 4,
                "pending": 0,
                "direction": 0,
                "magnitude": 0,
                "time_window": 0,
                "cause": 0,
            },
        }

    def _invalidated_result(self, hypothesis: dict, actuals: dict) -> dict:
        return {
            "hypothesis_ref": hypothesis["hypothesis_id"],
            "market": hypothesis["market"],
            "ticker": hypothesis["ticker"],
            "stat_eligible": True,
            "scenario_matched": "bear",
            "dimensions": {},
            "invalidation_review": {
                "any_triggered": True,
                "invalidation_type": "pre_trigger_invalidated",
                "details": actuals.get("invalidation_conditions_triggered", []),
            },
            "verdict": Verdict.INVALIDATED,
            "score": {
                "earned": 0,
                "possible": 4,
                "pending": 0,
                "direction": 0,
                "magnitude": 0,
                "time_window": 0,
                "cause": 0,
            },
        }
