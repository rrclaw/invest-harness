import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.ingest import run_ingest


@pytest.fixture
def harness_env(tmp_path):
    """Set up a minimal harness environment for ingest testing."""
    knowledge = tmp_path / "knowledge"
    for sub in ("raw", "normalized", "curated"):
        (knowledge / sub).mkdir(parents=True)
    chroma_dir = tmp_path / "chroma_storage"
    chroma_dir.mkdir()
    dedup = tmp_path / "dedup.json"
    return {
        "knowledge_dir": knowledge,
        "chroma_dir": chroma_dir,
        "dedup_file": dedup,
    }


def test_ingest_single_file(harness_env, tmp_path):
    input_file = tmp_path / "report.txt"
    input_file.write_bytes(b"Cambricon Q4 revenue data")

    with patch("scripts.ingest.create_chroma_manager") as mock_chroma_factory:
        mock_chroma = MagicMock()
        mock_chroma_factory.return_value = mock_chroma

        result = run_ingest(
            file_path=str(input_file),
            date="2026-03-26",
            title="Cambricon Q4 Report",
            source_type="company_research",
            knowledge_dir=str(harness_env["knowledge_dir"]),
            chroma_dir=str(harness_env["chroma_dir"]),
            dedup_file=str(harness_env["dedup_file"]),
        )

    assert result["raw_status"] == "ingested"


def test_ingest_duplicate_file(harness_env, tmp_path):
    input_file = tmp_path / "report.txt"
    input_file.write_bytes(b"Same content")

    with patch("scripts.ingest.create_chroma_manager") as mock_chroma_factory:
        mock_chroma = MagicMock()
        mock_chroma_factory.return_value = mock_chroma

        kwargs = dict(
            file_path=str(input_file),
            date="2026-03-26",
            title="Same Title",
            source_type="media_news",
            knowledge_dir=str(harness_env["knowledge_dir"]),
            chroma_dir=str(harness_env["chroma_dir"]),
            dedup_file=str(harness_env["dedup_file"]),
        )
        run_ingest(**kwargs)
        result = run_ingest(**kwargs)

    assert result["raw_status"] == "duplicate"
