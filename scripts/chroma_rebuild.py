"""Rebuild ChromaDB index from JSONL source files.

Idempotent: clears existing collections and re-indexes everything.
Only indexes facts with status='active' (skips superseded/disputed).

Usage:
    python -m scripts.chroma_rebuild [--knowledge-dir path] [--chroma-dir path]
"""

import argparse
import json
from pathlib import Path

from lib.chroma_client import ChromaManager, COLLECTION_NORMALIZED, COLLECTION_CURATED

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def rebuild_index(
    knowledge_dir: str | None = None,
    chroma_dir: str | None = None,
) -> dict:
    """Rebuild ChromaDB from JSONL files. Returns stats dict."""
    knowledge_dir = Path(knowledge_dir or PROJECT_ROOT / "knowledge")
    chroma_dir = chroma_dir or str(PROJECT_ROOT / "chroma_storage")

    chroma = ChromaManager(persist_dir=chroma_dir)

    # Clear existing data
    chroma.clear_collection(COLLECTION_NORMALIZED)
    chroma.clear_collection(COLLECTION_CURATED)

    facts_indexed = 0
    facts_skipped = 0
    insights_indexed = 0

    # Rebuild normalized facts
    norm_dir = knowledge_dir / "normalized"
    for jsonl_path in sorted(norm_dir.rglob("facts.jsonl")):
        for line in jsonl_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            fact = json.loads(line)
            if fact.get("status") != "active":
                facts_skipped += 1
                continue
            chroma.add_fact(
                fact_id=fact["fact_id"],
                text=fact["fact"],
                metadata={
                    "company": fact["company"][0] if fact["company"] else "",
                    "tickers": ",".join(fact["tickers"]),
                    "topic": fact["topic"],
                    "date": fact["date"],
                    "decay_class": fact["decay_class"],
                    "source_type": fact["source_type"],
                    "status": fact["status"],
                },
            )
            facts_indexed += 1

    # Rebuild curated insights
    curated_dir = knowledge_dir / "curated"
    for jsonl_path in sorted(curated_dir.rglob("*.jsonl")):
        for line in jsonl_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            insight = json.loads(line)
            insight_id = insight.get("consensus_id") or insight.get("insight_id", "unknown")
            text = insight.get("consensus_narrative") or insight.get("text", "")
            chroma.add_insight(
                insight_id=insight_id,
                text=text,
                metadata={
                    "company": insight.get("company", ""),
                    "theme": ",".join(insight.get("theme", [])),
                    "sentiment": insight.get("sentiment", ""),
                    "date": insight.get("date", ""),
                },
            )
            insights_indexed += 1

    return {
        "facts_indexed": facts_indexed,
        "facts_skipped": facts_skipped,
        "insights_indexed": insights_indexed,
    }


def main():
    parser = argparse.ArgumentParser(description="Rebuild ChromaDB index from JSONL")
    parser.add_argument("--knowledge-dir", help="Knowledge directory path")
    parser.add_argument("--chroma-dir", help="ChromaDB storage directory path")
    args = parser.parse_args()
    stats = rebuild_index(args.knowledge_dir, args.chroma_dir)
    print(f"Rebuild complete: {stats}")


if __name__ == "__main__":
    main()
