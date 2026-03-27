"""CLI entry point for knowledge ingestion.

Usage:
    python -m scripts.ingest --file path/to/file --date 2026-03-26 \
        --title "Report Title" --source-type company_research
"""

import argparse
import sys
from pathlib import Path

from lib.chroma_client import ChromaManager
from lib.knowledge import KnowledgePipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_chroma_manager(chroma_dir: str) -> ChromaManager:
    return ChromaManager(persist_dir=chroma_dir)


def run_ingest(
    file_path: str,
    date: str,
    title: str,
    source_type: str,
    knowledge_dir: str | None = None,
    chroma_dir: str | None = None,
    dedup_file: str | None = None,
) -> dict:
    """Run the ingestion pipeline for a single file."""
    knowledge_dir = knowledge_dir or str(PROJECT_ROOT / "knowledge")
    chroma_dir = chroma_dir or str(PROJECT_ROOT / "chroma_storage")
    dedup_file = dedup_file or str(PROJECT_ROOT / "knowledge" / "raw" / "seen_hashes.json")

    chroma = create_chroma_manager(chroma_dir)
    pipeline = KnowledgePipeline(
        knowledge_dir=knowledge_dir,
        chroma=chroma,
        dedup_file=dedup_file,
    )

    content = Path(file_path).read_bytes()
    filename = Path(file_path).name

    raw_result = pipeline.ingest_raw(
        content=content,
        filename=filename,
        date=date,
        title=title,
        source_type=source_type,
    )

    return {"raw_status": raw_result["status"], "filename": filename}


def main():
    parser = argparse.ArgumentParser(description="Ingest a file into the knowledge pipeline")
    parser.add_argument("--file", required=True, help="Path to file to ingest")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument(
        "--source-type",
        required=True,
        choices=[
            "company_research", "personal_note", "industry_data",
            "expert_minutes", "sell_side", "media_news", "social_rumor",
        ],
    )
    args = parser.parse_args()
    result = run_ingest(args.file, args.date, args.title, args.source_type)
    print(f"Ingest result: {result}")


if __name__ == "__main__":
    main()
