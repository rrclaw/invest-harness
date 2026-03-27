"""Time-decay weight calculation for knowledge facts.

Decay classes determine how quickly a fact's weight degrades over time.
'financial' class has NO time decay -- only replaced by same-metric new data.
"""

from datetime import date

# Each rule is a list of (max_days, weight) tuples, checked in order.
# If age exceeds all thresholds, the last weight is the floor.
DECAY_RULES: dict[str, list[tuple[int, float]]] = {
    "ephemeral": [
        (7, 1.0),
        (14, 0.5),
        (30, 0.2),
        (9999, 0.05),
    ],
    "periodic": [
        (90, 1.0),
        (180, 0.7),
        (365, 0.4),
        (9999, 0.4),
    ],
    "structural": [
        (180, 1.0),
        (365, 0.8),
        (730, 0.6),
        (9999, 0.6),
    ],
    "financial": [],  # No time decay
}


def calculate_decay_weight(
    decay_class: str, fact_date: date, reference_date: date
) -> float:
    """Calculate the decay-adjusted weight for a fact.

    Args:
        decay_class: One of 'ephemeral', 'periodic', 'structural', 'financial'.
        fact_date: The date the fact was created or last updated.
        reference_date: The date to calculate decay against (usually today).

    Returns:
        Weight multiplier between 0.0 and 1.0.
    """
    if decay_class not in DECAY_RULES:
        raise ValueError(f"Unknown decay_class: {decay_class!r}")

    if decay_class == "financial":
        return 1.0

    age_days = (reference_date - fact_date).days
    rules = DECAY_RULES[decay_class]

    for max_days, weight in rules:
        if age_days <= max_days:
            return weight

    # Should not reach here given 9999 sentinel, but safety fallback
    return rules[-1][1]
