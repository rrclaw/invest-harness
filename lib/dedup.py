"""SHA256 + title similarity deduplication for raw ingestion."""

import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path

TITLE_SIMILARITY_THRESHOLD = 0.8


def sha256_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def title_similarity(a: str, b: str) -> float:
    """Ratio-based similarity between two titles. Returns 0.0-1.0."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_duplicate(
    content: bytes, title: str, seen_file: str | Path
) -> bool:
    """Check if content or title is a duplicate of previously seen items.

    Uses a JSON file to persist seen hashes and titles across calls.
    Returns True if duplicate detected (by hash OR title similarity).
    """
    seen_file = Path(seen_file)
    if seen_file.exists():
        seen = json.loads(seen_file.read_text())
    else:
        seen = {"hashes": [], "titles": []}

    content_hash = sha256_hash(content)

    # Check exact content match
    if content_hash in seen["hashes"]:
        return True

    # Check title similarity against all seen titles
    for existing_title in seen["titles"]:
        if title_similarity(title, existing_title) >= TITLE_SIMILARITY_THRESHOLD:
            return True

    # Not a duplicate -- record it
    seen["hashes"].append(content_hash)
    seen["titles"].append(title)
    seen_file.write_text(json.dumps(seen))
    return False
