import pytest
from lib.dedup import sha256_hash, title_similarity, is_duplicate


def test_sha256_hash_deterministic():
    h1 = sha256_hash(b"hello world")
    h2 = sha256_hash(b"hello world")
    assert h1 == h2
    assert len(h1) == 64  # hex digest


def test_sha256_hash_different_inputs():
    h1 = sha256_hash(b"hello")
    h2 = sha256_hash(b"world")
    assert h1 != h2


def test_title_similarity_identical():
    score = title_similarity("Q4 revenue report", "Q4 revenue report")
    assert score == 1.0


def test_title_similarity_very_different():
    score = title_similarity("Q4 revenue report", "weather forecast tomorrow")
    assert score < 0.3


def test_title_similarity_similar():
    score = title_similarity(
        "Cambricon Q4 2025 revenue 2.54B",
        "Cambricon Q4 2025 revenue reaches 2.54 billion",
    )
    assert score > 0.6


def test_is_duplicate_by_hash(tmp_path):
    seen_file = tmp_path / "seen_hashes.json"
    content = b"exact same file"
    assert is_duplicate(content, "title A", seen_file) is False
    assert is_duplicate(content, "title B", seen_file) is True  # same content


def test_is_duplicate_by_title(tmp_path):
    seen_file = tmp_path / "seen_hashes.json"
    assert is_duplicate(b"content1", "Cambricon Q4 revenue 2.54B", seen_file) is False
    assert (
        is_duplicate(b"different_content", "Cambricon Q4 revenue reaches 2.54B", seen_file)
        is True
    )  # title similarity > 0.8


def test_not_duplicate(tmp_path):
    seen_file = tmp_path / "seen_hashes.json"
    assert is_duplicate(b"aaa", "topic alpha", seen_file) is False
    assert is_duplicate(b"bbb", "topic beta completely unrelated", seen_file) is False
