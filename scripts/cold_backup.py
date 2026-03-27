"""Weekly cold backup script.

Backs up:
1. harness.db
2. chroma_storage/ (tar.gz)
3. knowledge/normalized/ + curated/ (tar.gz)
4. knowledge/raw/ (tar.gz, incremental)

Retention: last 4 weekly backups.
"""

import argparse
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RETENTION_COUNT = 4


def run_backup(
    harness_dir: str | None = None,
    date_override: str | None = None,
) -> dict:
    """Execute cold backup. Returns stats dict."""
    root = Path(harness_dir or PROJECT_ROOT)
    backup_dir = root / "backups"
    backup_dir.mkdir(exist_ok=True)
    datestamp = date_override or datetime.now().strftime("%Y%m%d")

    stats = {
        "db_backed_up": False,
        "chroma_backed_up": False,
        "knowledge_backed_up": False,
        "raw_backed_up": False,
        "datestamp": datestamp,
    }

    # 1. harness.db
    db_path = root / "harness.db"
    if db_path.exists():
        shutil.copy2(db_path, backup_dir / f"harness_{datestamp}.db")
        stats["db_backed_up"] = True

    # 2. chroma_storage/
    chroma_dir = root / "chroma_storage"
    if chroma_dir.exists():
        tar_path = backup_dir / f"chroma_{datestamp}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(chroma_dir, arcname="chroma_storage")
        stats["chroma_backed_up"] = True

    # 3. knowledge/normalized/ + curated/
    knowledge_dir = root / "knowledge"
    if knowledge_dir.exists():
        tar_path = backup_dir / f"knowledge_{datestamp}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            for sub in ("normalized", "curated"):
                sub_dir = knowledge_dir / sub
                if sub_dir.exists():
                    tar.add(sub_dir, arcname=f"knowledge/{sub}")
        stats["knowledge_backed_up"] = True

    # 4. knowledge/raw/
    raw_dir = knowledge_dir / "raw" if knowledge_dir.exists() else None
    if raw_dir and raw_dir.exists():
        tar_path = backup_dir / f"raw_{datestamp}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(raw_dir, arcname="knowledge/raw")
        stats["raw_backed_up"] = True

    # Retention: keep only last N backups per type
    _enforce_retention(backup_dir, "harness_*.db")
    _enforce_retention(backup_dir, "chroma_*.tar.gz")
    _enforce_retention(backup_dir, "knowledge_*.tar.gz")
    _enforce_retention(backup_dir, "raw_*.tar.gz")

    return stats


def _enforce_retention(backup_dir: Path, pattern: str) -> None:
    """Delete old backups beyond retention count."""
    files = sorted(backup_dir.glob(pattern), key=lambda f: f.name, reverse=True)
    for old_file in files[RETENTION_COUNT:]:
        old_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="Run weekly cold backup")
    parser.add_argument("--harness-dir", help="Harness root directory")
    args = parser.parse_args()
    stats = run_backup(args.harness_dir)
    print(f"Backup complete: {stats}")


if __name__ == "__main__":
    main()
