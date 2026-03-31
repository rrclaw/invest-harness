"""Tests for Scanner."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from lib.scanner import Scanner, ScanConfig


@pytest.fixture
def scan_config():
    return ScanConfig(
        lookback_days=3,
        vector_top_k=5,
        max_facts_per_ticker=10,
        max_snippet_chars=200,
        max_insights_per_ticker=5,
        min_relevance_score=0.3,
        auto_lock_min_evidence=2,
        auto_lock_min_sources=2,
        auto_lock_max_miss_rate=0.7,
    )


@pytest.fixture
def mock_knowledge():
    kp = MagicMock()
    kp.get_recent_facts.return_value = [
        {"fact_id": "f1", "company": "贵州茅台", "tickers": ["600519.SH"],
         "topic": "earnings", "status": "active", "text": "Q1 revenue up 15%",
         "source_type": "company_research", "updated_at": "2026-03-29"},
        {"fact_id": "f2", "company": "贵州茅台", "tickers": ["600519.SH"],
         "topic": "channel", "status": "active", "text": "Channel inventory low",
         "source_type": "sell_side", "updated_at": "2026-03-28"},
    ]
    return kp


@pytest.fixture
def mock_chroma():
    cm = MagicMock()
    cm.search_facts.return_value = [
        {"id": "f3", "document": "Industry outlook positive", "metadata": {"source_type": "industry_data"}, "distance": 0.2},
    ]
    cm.search_insights.return_value = []
    return cm


@pytest.fixture
def mock_run_store():
    rs = MagicMock()
    rs.get_candidates_by_ticker.return_value = []
    return rs


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.return_value = json.dumps([{
        "primary_ticker": "600519.SH",
        "related_tickers": [],
        "direction": "long",
        "confidence": "high",
        "thesis": "Strong Q1 with low channel inventory",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "Q1 revenue up 15%"}],
        "suggested_entry": 1680.0,
        "suggested_exit": 1780.0,
        "stop_loss": 1640.0,
        "time_horizon": "1w",
        "risk_factors": ["Macro headwinds"],
    }])
    return llm


def test_build_context_bundle(scan_config, mock_knowledge, mock_chroma, mock_run_store):
    scanner = Scanner(
        knowledge=mock_knowledge, chroma=mock_chroma,
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    bundle = scanner._build_context_bundle(
        ticker="600519.SH", date="20260330",
        recent_facts=[{"fact_id": "f1", "tickers": ["600519.SH"], "text": "Q1 up"}],
    )
    assert "recent_facts" in bundle
    assert "vector_results" in bundle
    assert "historical_performance" in bundle


def test_validate_candidate_schema(scan_config):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=MagicMock(), llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    valid = {
        "primary_ticker": "600519.SH", "direction": "long",
        "confidence": "high", "thesis": "Strong earnings",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
    }
    assert scanner._validate_candidate(valid, watchlist_tickers=["600519.SH"]) is True


def test_validate_candidate_rejects_non_watchlist(scan_config):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=MagicMock(), llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    invalid = {
        "primary_ticker": "999999.SZ", "direction": "long",
        "confidence": "high", "thesis": "Not in watchlist",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
    }
    assert scanner._validate_candidate(invalid, watchlist_tickers=["600519.SH"]) is False


def test_auto_lock_gate_passes(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidate = {
        "primary_ticker": "600519.SH", "confidence": "high",
        "evidence": [
            {"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"},
            {"fact_id": "f2", "relevance_score": 0.8, "snippet": "b"},
        ],
    }
    assert scanner._check_auto_lock_gate(candidate) is True


def test_auto_lock_gate_insufficient_evidence(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidate = {
        "primary_ticker": "600519.SH", "confidence": "high",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"}],
    }
    assert scanner._check_auto_lock_gate(candidate) is False


def test_grade_candidates(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidates = [
        {"primary_ticker": "600519.SH", "confidence": "high",
         "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"},
                      {"fact_id": "f2", "relevance_score": 0.8, "snippet": "b"}],
         "direction": "long", "thesis": "test"},
        {"primary_ticker": "300750.SZ", "confidence": "medium",
         "evidence": [{"fact_id": "f3", "relevance_score": 0.7, "snippet": "c"}],
         "direction": "long", "thesis": "test2"},
        {"primary_ticker": "000001.SZ", "confidence": "low",
         "evidence": [{"fact_id": "f4", "relevance_score": 0.5, "snippet": "d"}],
         "direction": "long", "thesis": "test3"},
    ]
    graded = scanner._assign_actions(candidates)
    assert graded[0]["auto_action"] == "auto_lock"
    assert graded[1]["auto_action"] == "await_approval"
    assert graded[2]["auto_action"] == "log_only"
