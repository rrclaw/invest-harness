import pytest
from lib.contrarian import ContrarianChallenger


def test_consensus_cross_reference_aligned_hit():
    challenger = ContrarianChallenger()
    result = challenger.classify_consensus_outcome(
        thesis_cause_match="aligned",
        consensus_sentiment="bullish",
        verdict="hit",
    )
    assert result["category"] == "aligned_with_consensus_hit"
    assert "crowded trade" in result["warning"].lower()


def test_consensus_cross_reference_against_hit():
    challenger = ContrarianChallenger()
    result = challenger.classify_consensus_outcome(
        thesis_cause_match="aligned",
        consensus_sentiment="bearish",  # against consensus
        verdict="hit",
    )
    assert result["category"] == "against_consensus_hit"
    assert "alpha" in result["warning"].lower()


def test_consensus_cross_reference_aligned_miss():
    challenger = ContrarianChallenger()
    result = challenger.classify_consensus_outcome(
        thesis_cause_match="aligned",
        consensus_sentiment="bullish",
        verdict="miss",
    )
    assert result["category"] == "aligned_with_consensus_miss"
    assert "regime" in result["warning"].lower()


def test_consensus_cross_reference_against_miss():
    challenger = ContrarianChallenger()
    result = challenger.classify_consensus_outcome(
        thesis_cause_match="aligned",
        consensus_sentiment="bearish",
        verdict="miss",
    )
    assert result["category"] == "against_consensus_miss"


def test_detect_blind_spots_consecutive_hits():
    challenger = ContrarianChallenger()
    history = [{"verdict": "hit"} for _ in range(5)]
    spots = challenger.detect_blind_spots(history)
    assert any("consecutive" in s.lower() for s in spots)


def test_detect_blind_spots_no_misses():
    challenger = ContrarianChallenger()
    history = [{"verdict": "hit"}, {"verdict": "partial_hit"}]
    spots = challenger.detect_blind_spots(history)
    assert any("survivorship" in s.lower() or "sample" in s.lower() for s in spots)


def test_detect_blind_spots_empty():
    challenger = ContrarianChallenger()
    spots = challenger.detect_blind_spots([])
    assert spots == []
