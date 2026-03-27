import pytest
from lib.chroma_client import ChromaManager

NORMALIZED = "normalized_facts"
CURATED = "curated_insights"


@pytest.fixture
def chroma(tmp_path):
    return ChromaManager(persist_dir=str(tmp_path / "chroma"))


def test_collections_created(chroma):
    collections = chroma.list_collections()
    assert NORMALIZED in collections
    assert CURATED in collections


def test_add_and_search_fact(chroma):
    chroma.add_fact(
        fact_id="f_20260326_001",
        text="Cambricon Q4 revenue 2.54B CNY, YoY +312%",
        metadata={
            "company": "Cambricon",
            "tickers": "688256.SH",
            "topic": "quarterly_revenue",
            "date": "2026-03-26",
            "decay_class": "financial",
            "source_type": "company_research",
            "status": "active",
        },
    )
    results = chroma.search_facts("Cambricon revenue", n_results=5)
    assert len(results) >= 1
    assert results[0]["id"] == "f_20260326_001"


def test_add_and_search_insight(chroma):
    chroma.add_insight(
        insight_id="cs_20260326_001",
        text="Market broadly bullish on AI compute post-policy announcement",
        metadata={
            "company": "Cambricon",
            "theme": "AI_compute",
            "sentiment": "bullish",
            "date": "2026-03-26",
        },
    )
    results = chroma.search_insights("AI compute bullish", n_results=5)
    assert len(results) >= 1
    assert results[0]["id"] == "cs_20260326_001"


def test_search_empty_collection(chroma):
    results = chroma.search_facts("anything", n_results=5)
    assert results == []


def test_delete_fact(chroma):
    chroma.add_fact(
        fact_id="f_delete_me",
        text="Temporary fact",
        metadata={"company": "Test", "tickers": "TEST", "topic": "test",
                   "date": "2026-01-01", "decay_class": "ephemeral",
                   "source_type": "media_news", "status": "active"},
    )
    chroma.delete_fact("f_delete_me")
    results = chroma.search_facts("Temporary fact", n_results=5)
    assert all(r["id"] != "f_delete_me" for r in results)


def test_update_fact_status(chroma):
    chroma.add_fact(
        fact_id="f_update_me",
        text="Old fact",
        metadata={"company": "X", "tickers": "X", "topic": "t",
                   "date": "2026-01-01", "decay_class": "ephemeral",
                   "source_type": "media_news", "status": "active"},
    )
    chroma.update_fact_metadata("f_update_me", {"status": "superseded"})
    results = chroma.search_facts("Old fact", n_results=5)
    matched = [r for r in results if r["id"] == "f_update_me"]
    assert len(matched) == 1
    assert matched[0]["metadata"]["status"] == "superseded"


def test_search_facts_with_filter(chroma):
    chroma.add_fact(
        fact_id="f_a",
        text="Alpha company revenue",
        metadata={"company": "Alpha", "tickers": "ALPHA", "topic": "revenue",
                   "date": "2026-03-26", "decay_class": "financial",
                   "source_type": "company_research", "status": "active"},
    )
    chroma.add_fact(
        fact_id="f_b",
        text="Beta company revenue",
        metadata={"company": "Beta", "tickers": "BETA", "topic": "revenue",
                   "date": "2026-03-26", "decay_class": "financial",
                   "source_type": "company_research", "status": "active"},
    )
    results = chroma.search_facts(
        "revenue", n_results=5, where={"company": "Alpha"}
    )
    assert len(results) == 1
    assert results[0]["id"] == "f_a"


def test_clear_collection(chroma):
    chroma.add_fact(
        fact_id="f_clear",
        text="To be cleared",
        metadata={"company": "X", "tickers": "X", "topic": "t",
                   "date": "2026-01-01", "decay_class": "ephemeral",
                   "source_type": "media_news", "status": "active"},
    )
    chroma.clear_collection(NORMALIZED)
    results = chroma.search_facts("cleared", n_results=5)
    assert results == []
