import pytest
from pathlib import Path
from scripts.cold_backup import run_backup


@pytest.fixture
def harness_env(tmp_path):
    """Set up minimal harness environment for backup testing."""
    (tmp_path / "harness.db").write_text("fake db")
    chroma = tmp_path / "chroma_storage"
    chroma.mkdir()
    (chroma / "index.bin").write_bytes(b"fake index")
    knowledge = tmp_path / "knowledge"
    (knowledge / "normalized" / "2026-03-26").mkdir(parents=True)
    (knowledge / "normalized" / "2026-03-26" / "facts.jsonl").write_text('{"test": 1}')
    (knowledge / "curated").mkdir(parents=True)
    (knowledge / "raw" / "2026-03-26").mkdir(parents=True)
    (knowledge / "raw" / "2026-03-26" / "file.txt").write_text("raw data")
    backups = tmp_path / "backups"
    backups.mkdir()
    return tmp_path


def test_backup_creates_files(harness_env):
    stats = run_backup(harness_dir=str(harness_env))
    backup_dir = harness_env / "backups"
    files = list(backup_dir.iterdir())
    # Should have db backup + chroma tar + knowledge tar + raw tar
    assert stats["db_backed_up"] is True
    assert stats["chroma_backed_up"] is True
    assert stats["knowledge_backed_up"] is True


def test_backup_retention_keeps_4(harness_env):
    # Run 5 backups with different dates
    for i in range(5):
        stats = run_backup(
            harness_dir=str(harness_env),
            date_override=f"2026030{i+1}",
        )
    backup_dir = harness_env / "backups"
    db_backups = list(backup_dir.glob("harness_*.db"))
    assert len(db_backups) <= 4  # Retention: last 4
