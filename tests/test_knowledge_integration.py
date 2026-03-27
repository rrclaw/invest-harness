"""Integration test: full pipeline from raw file to ChromaDB search."""

import json
import pytest
from pathlib import Path
from lib.chroma_client import ChromaManager
from lib.knowledge import KnowledgePipeline


@pytest.fixture
def full_pipeline(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    for sub in ("raw", "normalized", "curated"):
        (knowledge_dir / sub).mkdir(parents=True)
    chroma = ChromaManager(persist_dir=str(tmp_path / "chroma"))
    dedup = tmp_path / "seen.json"
    pipeline = KnowledgePipeline(knowledge_dir, chroma, dedup)
    return pipeline, chroma


def test_end_to_end_ingest_and_search(full_pipeline):
    pipeline, chroma = full_pipeline

    # Step 1: Ingest raw
    result = pipeline.ingest_raw(
        content=b"Cambricon Q4 2025 earnings report full text...",
        filename="cambricon_q4.pdf",
        date="2026-03-26",
        title="Cambricon Q4 2025 Earnings",
        source_type="company_research",
    )
    assert result["status"] == "ingested"

    # Step 2: Add normalized fact
    fact = {
        "fact_id": "f_20260326_001",
        "fact": "Cambricon 2025Q4 revenue 2.54B CNY, YoY +312%",
        "company": ["Cambricon"],
        "tickers": ["688256.SH"],
        "topic": "quarterly_revenue",
        "as_of": "2025-12-31",
        "date": "2026-03-26",
        "source_ref": "raw/2026-03-26/cambricon_q4.pdf",
        "source_type": "company_research",
        "confidence": 0.95,
        "decay_class": "financial",
        "tags": ["earnings", "revenue", "AI_chip"],
        "status": "active",
        "supersedes": None,
        "supersede_type": None,
    }
    pipeline.add_normalized_fact(fact)

    # Step 3: Search for it
    results = chroma.search_facts("Cambricon revenue", n_results=5)
    assert len(results) == 1
    assert results[0]["id"] == "f_20260326_001"
    assert "2.54B" in results[0]["document"]

    # Step 4: Add consensus tracking
    insight = {
        "consensus_id": "cs_20260326_001",
        "date": "2026-03-26",
        "company": "Cambricon",
        "tickers": ["688256.SH"],
        "theme": ["AI_compute"],
        "consensus_narrative": "Market broadly bullish on AI compute post-policy",
        "sentiment": "bullish",
        "confidence": 0.8,
        "source_refs": ["f_20260326_001"],
        "note": None,
    }
    pipeline.add_curated_insight(insight)

    # Step 5: Search curated
    insights = chroma.search_insights("AI compute sentiment", n_results=5)
    assert len(insights) == 1
    assert insights[0]["metadata"]["sentiment"] == "bullish"


def test_conflict_detection_end_to_end(full_pipeline):
    pipeline, chroma = full_pipeline

    # Add existing high-weight fact
    fact_old = {
        "fact_id": "f_20260325_001",
        "fact": "Cambricon Q3 revenue 1.8B CNY",
        "company": ["Cambricon"],
        "tickers": ["688256.SH"],
        "topic": "quarterly_revenue",
        "as_of": "2025-09-30",
        "date": "2026-03-25",
        "source_ref": "raw/2026-03-25/q3.pdf",
        "source_type": "company_research",
        "confidence": 0.95,
        "decay_class": "financial",
        "tags": ["earnings"],
        "status": "active",
        "supersedes": None,
        "supersede_type": None,
    }
    pipeline.add_normalized_fact(fact_old)

    # New fact from same-weight source: should supersede
    conflict = pipeline.detect_conflict(
        company="Cambricon",
        topic="quarterly_revenue",
        new_weight=pipeline.source_weight("company_research"),
    )
    assert conflict["conflict"] is True
    assert conflict["resolution"] == "supersede"

    # New fact from lower-weight source: pending_conflict
    conflict2 = pipeline.detect_conflict(
        company="Cambricon",
        topic="quarterly_revenue",
        new_weight=pipeline.source_weight("social_rumor"),
    )
    assert conflict2["conflict"] is True
    assert conflict2["resolution"] == "pending_conflict"
