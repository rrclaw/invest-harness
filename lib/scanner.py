"""Scanner — knowledge base opportunity screening with LLM analysis."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "scan_candidate.schema.json"


@dataclass
class ScanConfig:
    lookback_days: int = 3
    vector_top_k: int = 5
    max_facts_per_ticker: int = 10
    max_snippet_chars: int = 200
    max_insights_per_ticker: int = 5
    min_relevance_score: float = 0.3
    auto_lock_min_evidence: int = 2
    auto_lock_min_sources: int = 2
    auto_lock_max_miss_rate: float = 0.7
    blacklist: list = field(default_factory=list)


class Scanner:
    def __init__(self, *, knowledge, chroma, run_store, llm_call, rules, config: ScanConfig):
        self._knowledge = knowledge
        self._chroma = chroma
        self._run_store = run_store
        self._llm_call = llm_call
        self._rules = rules
        self._config = config
        self._schema = None
        if SCHEMA_PATH.exists():
            self._schema = json.loads(SCHEMA_PATH.read_text())

    def scan(self, *, market: str, date: str, watchlist_tickers: list[str]) -> dict:
        """Run full scan pipeline. Returns dict with candidates and grading."""
        # Step 1: Incremental KB retrieval
        recent_facts = self._get_recent_facts(market, date, watchlist_tickers)

        # Step 2: Per-ticker context bundles
        ticker_bundles = {}
        for ticker in watchlist_tickers:
            ticker_facts = [f for f in recent_facts
                           if ticker in f.get("tickers", [])]
            bundle = self._build_context_bundle(ticker, date, ticker_facts)
            if bundle["recent_facts"] or bundle["vector_results"]:
                ticker_bundles[ticker] = bundle

        if not ticker_bundles:
            return {"candidates": [], "summary": {"high": 0, "medium": 0, "low": 0}}

        # Step 3: LLM analysis
        prompt = self._build_prompt(ticker_bundles)
        raw_output = self._llm_call(prompt)
        candidates = self._parse_and_validate(raw_output, watchlist_tickers)

        # Step 4: Assign actions
        graded = self._assign_actions(candidates)

        summary = {
            "high": sum(1 for c in graded if c["confidence"] == "high"),
            "medium": sum(1 for c in graded if c["confidence"] == "medium"),
            "low": sum(1 for c in graded if c["confidence"] == "low"),
        }

        return {"candidates": graded, "summary": summary}

    def _get_recent_facts(self, market, date, tickers):
        try:
            return self._knowledge.get_recent_facts(
                days=self._config.lookback_days,
                tickers=tickers,
                status="active",
            )
        except Exception:
            logger.warning("Failed to get recent facts, returning empty")
            return []

    def _build_context_bundle(self, ticker, date, recent_facts):
        # Vector retrieval
        vector_results = []
        try:
            raw_results = self._chroma.search_facts(
                query=f"{ticker} investment opportunity risk",
                n_results=self._config.vector_top_k,
            )
            vector_results = [
                r for r in raw_results
                if r.get("distance", 1.0) <= (1 - self._config.min_relevance_score)
            ]
        except Exception:
            logger.warning(f"Vector retrieval failed for {ticker}, degrading")

        # Merge dedup by fact_id
        seen_ids = {f["fact_id"] for f in recent_facts}
        for vr in vector_results:
            if vr["id"] not in seen_ids:
                recent_facts.append({
                    "fact_id": vr["id"],
                    "text": vr.get("document", ""),
                    "source_type": vr.get("metadata", {}).get("source_type", "unknown"),
                })
                seen_ids.add(vr["id"])

        # Budget control
        recent_facts = recent_facts[:self._config.max_facts_per_ticker]
        for f in recent_facts:
            if "text" in f:
                f["text"] = f["text"][:self._config.max_snippet_chars]

        # Historical performance
        historical = {"available": False, "hit_rate": None, "miss_rate": None}
        try:
            past = self._run_store.get_candidates_by_ticker(ticker, days=30)
            if past:
                historical["available"] = True
                historical["total"] = len(past)
        except Exception:
            pass

        # Insights
        insights = []
        try:
            raw_insights = self._chroma.search_insights(
                query=ticker, n_results=self._config.max_insights_per_ticker,
            )
            insights = raw_insights
        except Exception:
            pass

        return {
            "recent_facts": recent_facts,
            "vector_results": vector_results,
            "historical_performance": historical,
            "insights": insights,
        }

    def _build_prompt(self, ticker_bundles: dict) -> str:
        prompt_template = ""
        prompt_path = Path(__file__).parent.parent / "prompts" / "scan.md"
        if prompt_path.exists():
            prompt_template = prompt_path.read_text()

        context_str = json.dumps(ticker_bundles, ensure_ascii=False, default=str)
        rules_str = json.dumps(
            [{"rule_id": r.rule_id, "title": r.title, "body": r.body}
             for r in self._rules] if self._rules else [],
            ensure_ascii=False,
        )

        return prompt_template.replace("{context_bundle}", context_str).replace("{rules}", rules_str)

    def _parse_and_validate(self, raw_output: str, watchlist_tickers: list[str]) -> list[dict]:
        try:
            start = raw_output.find("[")
            end = raw_output.rfind("]") + 1
            if start >= 0 and end > start:
                candidates = json.loads(raw_output[start:end])
            else:
                candidates = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.error("LLM output is not valid JSON")
            return []

        if not isinstance(candidates, list):
            return []

        valid = []
        for c in candidates:
            if self._validate_candidate(c, watchlist_tickers):
                valid.append(c)
            else:
                logger.warning(f"Candidate failed validation: {c.get('primary_ticker', '?')}")

        return valid

    def _validate_candidate(self, candidate: dict, watchlist_tickers: list[str]) -> bool:
        # Layer 1: Schema validation
        if self._schema:
            try:
                jsonschema.validate(instance=candidate, schema=self._schema)
            except jsonschema.ValidationError as e:
                logger.warning(f"Schema validation failed: {e.message}")
                return False

        # Layer 2: Business validation
        if candidate.get("primary_ticker") not in watchlist_tickers:
            logger.warning(f"primary_ticker {candidate.get('primary_ticker')} not in watchlist")
            return False

        evidence = candidate.get("evidence", [])
        if not evidence:
            return False

        return True

    def _check_auto_lock_gate(self, candidate: dict) -> bool:
        """Check if high-confidence candidate passes risk gates for auto-lock."""
        evidence = candidate.get("evidence", [])

        # Gate 1: Minimum evidence count
        if len(evidence) < self._config.auto_lock_min_evidence:
            return False

        # Gate 2: Blacklist
        if candidate.get("primary_ticker") in self._config.blacklist:
            return False

        # Gate 3: Historical miss rate
        try:
            past = self._run_store.get_candidates_by_ticker(
                candidate["primary_ticker"], days=30
            )
            if past:
                # Will be refined when feedback data accumulates
                pass
        except Exception:
            pass

        return True

    def _assign_actions(self, candidates: list[dict]) -> list[dict]:
        """Assign auto_action based on confidence + risk gates."""
        for c in candidates:
            conf = c.get("confidence", "low")
            if conf == "high" and self._check_auto_lock_gate(c):
                c["auto_action"] = "auto_lock"
            elif conf == "high":
                c["auto_action"] = "await_approval"
            elif conf == "medium":
                c["auto_action"] = "await_approval"
            else:
                c["auto_action"] = "log_only"
        return candidates
