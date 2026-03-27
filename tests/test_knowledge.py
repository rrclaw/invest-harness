import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from lib.knowledge import KnowledgePipeline

# Source type weights from spec
SOURCE_WEIGHTS = {
    "company_research": 1.0,
    "personal_note": 0.9,
    "industry_data": 0.85,
    "expert_minutes": 0.8,
    "sell_side": 0.7,
    "media_news": 0.5,
    "social_rumor": 0.3,
}


@pytest.fixture
def knowledge_dir(tmp_path):
    raw = tmp_path / "knowledge" / "raw"
    normalized = tmp_path / "knowledge" / "normalized"
    curated = tmp_path / "knowledge" / "curated"
    raw.mkdir(parents=True)
    normalized.mkdir(parents=True)
    curated.mkdir(parents=True)
    return tmp_path / "knowledge"


@pytest.fixture
def pipeline(knowledge_dir, tmp_path):
    chroma = MagicMock()
    dedup_file = tmp_path / "seen_hashes.json"
    return KnowledgePipeline(
        knowledge_dir=knowledge_dir,
        chroma=chroma,
        dedup_file=dedup_file,
    )


def test_ingest_raw_stores_file(pipeline, knowledge_dir):
    result = pipeline.ingest_raw(
        content=b"PDF content here",
        filename="report.pdf",
        date="2026-03-26",
        title="Cambricon Q4 Report",
        source_type="company_research",
    )
    raw_dir = knowledge_dir / "raw" / "2026-03-26"
    assert raw_dir.exists()
    assert (raw_dir / "report.pdf").exists()
    assert (raw_dir / "report.pdf").read_bytes() == b"PDF content here"


def test_ingest_raw_creates_metadata(pipeline, knowledge_dir):
    pipeline.ingest_raw(
        content=b"content",
        filename="test.pdf",
        date="2026-03-26",
        title="Test Report",
        source_type="expert_minutes",
    )
    meta_path = knowledge_dir / "raw" / "2026-03-26" / "test.meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["original"] == "test.pdf"
    assert meta["source_type"] == "expert_minutes"
    assert "extracted_at" in meta


def test_ingest_raw_dedup_rejects_duplicate(pipeline):
    pipeline.ingest_raw(b"same", "a.pdf", "2026-03-26", "Title", "media_news")
    result = pipeline.ingest_raw(b"same", "b.pdf", "2026-03-26", "Title", "media_news")
    assert result["status"] == "duplicate"


def test_normalize_fact_writes_jsonl(pipeline, knowledge_dir):
    fact = {
        "fact_id": "f_20260326_001",
        "fact": "Revenue 2.54B",
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
    }
    pipeline.add_normalized_fact(fact)
    jsonl_path = knowledge_dir / "normalized" / "2026-03-26" / "facts.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["fact_id"] == "f_20260326_001"


def test_normalize_fact_indexes_in_chroma(pipeline):
    fact = {
        "fact_id": "f_20260326_001",
        "fact": "Revenue 2.54B",
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
    }
    pipeline.add_normalized_fact(fact)
    pipeline._chroma.add_fact.assert_called_once()
    call_kwargs = pipeline._chroma.add_fact.call_args
    assert call_kwargs[1]["fact_id"] == "f_20260326_001"


def test_source_weight_lookup(pipeline):
    assert pipeline.source_weight("company_research") == 1.0
    assert pipeline.source_weight("social_rumor") == 0.3


def test_conflict_detection_no_existing(pipeline):
    pipeline._chroma.search_facts.return_value = []
    result = pipeline.detect_conflict(
        company="Cambricon", topic="quarterly_revenue", new_weight=1.0
    )
    assert result["conflict"] is False


def test_conflict_detection_same_weight(pipeline):
    pipeline._chroma.search_facts.return_value = [
        {
            "id": "f_old",
            "metadata": {
                "company": "Cambricon",
                "topic": "quarterly_revenue",
                "source_type": "company_research",
                "status": "active",
            },
        }
    ]
    result = pipeline.detect_conflict(
        company="Cambricon", topic="quarterly_revenue", new_weight=1.0
    )
    assert result["conflict"] is True
    assert result["resolution"] == "supersede"


def test_conflict_detection_lower_challenges_higher(pipeline):
    pipeline._chroma.search_facts.return_value = [
        {
            "id": "f_old",
            "metadata": {
                "company": "Cambricon",
                "topic": "quarterly_revenue",
                "source_type": "company_research",
                "status": "active",
            },
        }
    ]
    result = pipeline.detect_conflict(
        company="Cambricon", topic="quarterly_revenue", new_weight=0.5
    )
    assert result["conflict"] is True
    assert result["resolution"] == "pending_conflict"


def test_add_curated_insight(pipeline, knowledge_dir):
    insight = {
        "consensus_id": "cs_20260326_001",
        "date": "2026-03-26",
        "company": "Cambricon",
        "tickers": ["688256.SH"],
        "theme": ["AI_compute"],
        "consensus_narrative": "Market bullish on AI compute",
        "sentiment": "bullish",
        "confidence": 0.8,
        "source_refs": ["f_20260326_001"],
        "note": None,
    }
    pipeline.add_curated_insight(insight)
    jsonl_path = knowledge_dir / "curated" / "consensus_tracking.jsonl"
    assert jsonl_path.exists()
    pipeline._chroma.add_insight.assert_called_once()
