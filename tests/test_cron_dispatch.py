import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def harness_root(project_root):
    return project_root


def test_cron_dispatch_shows_usage_on_missing_args(harness_root):
    result = subprocess.run(
        [str(harness_root / "scripts" / "cron_dispatch.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_cron_dispatch_unknown_task(harness_root):
    result = subprocess.run(
        [str(harness_root / "scripts" / "cron_dispatch.sh"), "unknown_task", "a_stock"],
        capture_output=True,
        text=True,
        cwd=str(harness_root),
    )
    assert result.returncode != 0
    assert "Unknown task" in result.stdout or "Unknown task" in result.stderr
