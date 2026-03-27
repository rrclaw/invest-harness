"""Post-market verification entry point.

Compares hypothesis predictions against actual market data,
generates verification result, and writes to reviews/ directory.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from lib.verification import VerificationEngine


def run_post_verify(
    hypothesis: dict,
    actuals: dict,
    date: str,
    reviews_dir: str,
) -> dict:
    """Run post-market verification for a single hypothesis.

    Args:
        hypothesis: Full hypothesis dict.
        actuals: Actual market data dict.
        date: Exchange date (YYYY-MM-DD).
        reviews_dir: Path to reviews/ directory.

    Returns:
        Verification result dict.
    """
    engine = VerificationEngine()
    result = engine.verify(hypothesis, actuals)

    # Add metadata
    result["verify_id"] = f"v_{date.replace('-', '')}_{hypothesis['market']}_001"
    result["exchange_date"] = date
    result["verified_at"] = datetime.now(timezone.utc).isoformat()
    result["data_source"] = "adapter"

    # Write to reviews directory
    day_dir = Path(reviews_dir) / date
    day_dir.mkdir(parents=True, exist_ok=True)
    output_path = day_dir / f"post_market_{hypothesis['market']}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    return result
