import json
import pytest
from pathlib import Path
from scripts.chroma_rebuild import rebuild_index


@pytest.fixture
def knowledge_with_data(tmp_path):
    """Create knowledge dir with JSONL data for rebuild testing."""
    norm_dir = tmp_path / "knowledge" / "normalized" / "2026-03-26"
    norm_dir.mkdir(parents=True)
    facts = [
        {
            "fact_id": "f_20260326_001",
            "fact": "Cambricon Q4 revenue 2.54B",
            "company": ["Cambricon"],
            "tickers": ["688256.SH"],
            "topic": "quarterly_revenue",
            "as_of": "2025-12-31",
            "date": "2026-03-26",
            "source_ref": "raw/2026-03-26/report.pdf",
            "source_type": "company_research",
            "confidence": 0.95,
            "decay_class": "financial",
            "tags": ["earnings"],
            "status": "active",
            "supersedes": None,
            "supersede_type": None,
        },
        {
            "fact_id": "f_20260326_002",
            "fact": "CATL capacity expansion approved",
            "company": ["CATL"],
            "tickers": ["300750.SZ"],
            "topic": "capacity",
            "as_of": "2026-03-25",
            "date": "2026-03-26",
            "source_ref": "raw/2026-03-26/news.md",
            "source_type": "media_news",
            "confidence": 0.7,
            "decay_class": "structural",
            "tags": ["capacity"],
            "status": "active",
            "supersedes": None,
            "supersede_type": None,
        },
    ]
    jsonl_path = norm_dir / "facts.jsonl"
    with open(jsonl_path, "w") as f:
        for fact in facts:
            f.write(json.dumps(fact) + "\n")

    curated_dir = tmp_path / "knowledge" / "curated"
    curated_dir.mkdir(parents=True)
    consensus = {
        "consensus_id": "cs_20260326_001",
        "date": "2026-03-26",
        "company": "Cambricon",
        "tickers": ["688256.SH"],
        "theme": ["AI_compute"],
        "consensus_narrative": "Market bullish",
        "sentiment": "bullish",
        "confidence": 0.8,
        "source_refs": [],
        "note": None,
    }
    with open(curated_dir / "consensus_tracking.jsonl", "w") as f:
        f.write(json.dumps(consensus) + "\n")

    return tmp_path / "knowledge"


def test_rebuild_populates_chroma(knowledge_with_data, tmp_path):
    chroma_dir = tmp_path / "chroma_fresh"
    stats = rebuild_index(
        knowledge_dir=str(knowledge_with_data),
        chroma_dir=str(chroma_dir),
    )
    assert stats["facts_indexed"] == 2
    assert stats["insights_indexed"] == 1


def test_rebuild_clears_existing(knowledge_with_data, tmp_path):
    chroma_dir = tmp_path / "chroma_fresh"
    rebuild_index(knowledge_dir=str(knowledge_with_data), chroma_dir=str(chroma_dir))
    # Second rebuild should not double-count
    stats = rebuild_index(knowledge_dir=str(knowledge_with_data), chroma_dir=str(chroma_dir))
    assert stats["facts_indexed"] == 2


def test_rebuild_skips_superseded(knowledge_with_data, tmp_path):
    # Add a superseded fact
    norm_dir = knowledge_with_data / "normalized" / "2026-03-26"
    with open(norm_dir / "facts.jsonl", "a") as f:
        superseded = {
            "fact_id": "f_20260326_003", "fact": "Old data", "company": ["X"],
            "tickers": ["X"], "topic": "t", "as_of": "2025-01-01",
            "date": "2026-03-26", "source_ref": "raw/x", "source_type": "media_news",
            "confidence": 0.5, "decay_class": "ephemeral", "tags": [],
            "status": "superseded", "supersedes": None, "supersede_type": None,
        }
        f.write(json.dumps(superseded) + "\n")

    chroma_dir = tmp_path / "chroma_fresh2"
    stats = rebuild_index(knowledge_dir=str(knowledge_with_data), chroma_dir=str(chroma_dir))
    # Only active facts should be indexed
    assert stats["facts_indexed"] == 2
    assert stats["facts_skipped"] == 1
