import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_harness(tmp_path):
    """Create a temporary harness directory for testing."""
    db_path = tmp_path / "harness.db"
    return db_path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent
