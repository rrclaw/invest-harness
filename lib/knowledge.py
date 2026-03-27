"""Three-tier knowledge pipeline: Raw -> Normalized -> Curated.

Raw: immutable original files + extraction metadata.
Normalized: structured facts (JSONL) indexed in ChromaDB.
Curated: distilled insights + consensus tracking in ChromaDB.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from lib.dedup import is_duplicate
from lib.schema_validator import validate

SOURCE_WEIGHTS = {
    "company_research": 1.0,
    "personal_note": 0.9,
    "industry_data": 0.85,
    "expert_minutes": 0.8,
    "sell_side": 0.7,
    "media_news": 0.5,
    "social_rumor": 0.3,
}


class KnowledgePipeline:
    """Orchestrates the three-tier knowledge pipeline."""

    def __init__(self, knowledge_dir: str | Path, chroma, dedup_file: str | Path):
        self._dir = Path(knowledge_dir)
        self._chroma = chroma
        self._dedup_file = Path(dedup_file)

    def source_weight(self, source_type: str) -> float:
        return SOURCE_WEIGHTS.get(source_type, 0.0)

    # --- Raw Layer ---

    def ingest_raw(
        self,
        content: bytes,
        filename: str,
        date: str,
        title: str,
        source_type: str,
    ) -> dict:
        """Store raw file + metadata. Returns status dict."""
        if is_duplicate(content, title, self._dedup_file):
            return {"status": "duplicate", "filename": filename}

        day_dir = self._dir / "raw" / date
        day_dir.mkdir(parents=True, exist_ok=True)

        # Write original file
        (day_dir / filename).write_bytes(content)

        # Write metadata
        meta = {
            "original": filename,
            "source_type": source_type,
            "title": title,
            "extraction_method": None,
            "extraction_quality": None,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path = day_dir / f"{Path(filename).stem}.meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

        return {"status": "ingested", "filename": filename, "meta_path": str(meta_path)}

    # --- Normalized Layer ---

    def add_normalized_fact(self, fact: dict) -> dict:
        """Validate, write to JSONL, and index in ChromaDB."""
        validate(fact, "fact")

        date = fact["date"]
        day_dir = self._dir / "normalized" / date
        day_dir.mkdir(parents=True, exist_ok=True)

        jsonl_path = day_dir / "facts.jsonl"
        with open(jsonl_path, "a") as f:
            f.write(json.dumps(fact, ensure_ascii=False) + "\n")

        # Index in ChromaDB
        # ChromaDB metadata must be flat strings/numbers, not lists
        chroma_meta = {
            "company": fact["company"][0] if fact["company"] else "",
            "tickers": ",".join(fact["tickers"]),
            "topic": fact["topic"],
            "date": fact["date"],
            "decay_class": fact["decay_class"],
            "source_type": fact["source_type"],
            "status": fact["status"],
        }
        self._chroma.add_fact(
            fact_id=fact["fact_id"],
            text=fact["fact"],
            metadata=chroma_meta,
        )

        return {"status": "normalized", "fact_id": fact["fact_id"]}

    # --- Conflict Detection ---

    def detect_conflict(
        self, company: str, topic: str, new_weight: float
    ) -> dict:
        """Check if a new fact conflicts with existing facts.

        Returns:
            dict with 'conflict' bool and 'resolution' if applicable.
            resolution: 'supersede' | 'pending_conflict' | None
        """
        existing = self._chroma.search_facts(
            f"{company} {topic}",
            n_results=5,
            where={"company": company},
        )

        # Filter to same topic + active status
        matches = [
            r for r in existing
            if r.get("metadata", {}).get("topic") == topic
            and r.get("metadata", {}).get("status") == "active"
        ]

        if not matches:
            return {"conflict": False, "resolution": None, "existing_ids": []}

        # Compare weights
        existing_ids = [m["id"] for m in matches]
        old_type = matches[0]["metadata"].get("source_type", "media_news")
        old_weight = self.source_weight(old_type)

        if new_weight >= old_weight:
            return {
                "conflict": True,
                "resolution": "supersede",
                "existing_ids": existing_ids,
            }
        else:
            return {
                "conflict": True,
                "resolution": "pending_conflict",
                "existing_ids": existing_ids,
            }

    # --- Curated Layer ---

    def add_curated_insight(self, insight: dict) -> dict:
        """Write curated insight to JSONL and index in ChromaDB."""
        # Determine file based on presence of consensus_id
        if "consensus_id" in insight:
            filename = "consensus_tracking.jsonl"
            validate(insight, "consensus_tracking")
            insight_id = insight["consensus_id"]
            text = insight["consensus_narrative"]
        else:
            filename = "insights.jsonl"
            insight_id = insight.get("insight_id", "unknown")
            text = insight.get("text", "")

        jsonl_path = self._dir / "curated" / filename
        with open(jsonl_path, "a") as f:
            f.write(json.dumps(insight, ensure_ascii=False) + "\n")

        chroma_meta = {
            "company": insight.get("company", ""),
            "theme": ",".join(insight.get("theme", [])),
            "sentiment": insight.get("sentiment", ""),
            "date": insight.get("date", ""),
        }
        self._chroma.add_insight(
            insight_id=insight_id,
            text=text,
            metadata=chroma_meta,
        )

        return {"status": "curated", "insight_id": insight_id}
