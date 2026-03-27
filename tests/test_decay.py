import pytest
from datetime import date
from lib.decay import calculate_decay_weight, DECAY_RULES


def test_decay_rules_defined():
    assert "ephemeral" in DECAY_RULES
    assert "periodic" in DECAY_RULES
    assert "structural" in DECAY_RULES
    assert "financial" in DECAY_RULES


def test_ephemeral_fresh():
    # Within 7 days -> weight 1.0
    w = calculate_decay_weight("ephemeral", date(2026, 3, 20), date(2026, 3, 26))
    assert w == 1.0


def test_ephemeral_14_days():
    # 8-14 days -> weight 0.5
    w = calculate_decay_weight("ephemeral", date(2026, 3, 12), date(2026, 3, 26))
    assert w == 0.5


def test_ephemeral_30_days():
    # 15-30 days -> weight 0.2
    w = calculate_decay_weight("ephemeral", date(2026, 2, 26), date(2026, 3, 26))
    assert w == 0.2


def test_ephemeral_60_days():
    # 31-60 days -> weight 0.05
    w = calculate_decay_weight("ephemeral", date(2026, 1, 26), date(2026, 3, 26))
    assert w == 0.05


def test_ephemeral_beyond_60():
    # >60 days -> weight 0.05 (floor)
    w = calculate_decay_weight("ephemeral", date(2025, 12, 1), date(2026, 3, 26))
    assert w == 0.05


def test_periodic_fresh():
    w = calculate_decay_weight("periodic", date(2026, 1, 1), date(2026, 3, 26))
    assert w == 1.0  # within 90 days


def test_periodic_180_days():
    w = calculate_decay_weight("periodic", date(2025, 10, 1), date(2026, 3, 26))
    assert w == 0.7  # 91-180 days


def test_periodic_365_days():
    w = calculate_decay_weight("periodic", date(2025, 5, 1), date(2026, 3, 26))
    assert w == 0.4  # 181-365 days


def test_structural_fresh():
    w = calculate_decay_weight("structural", date(2025, 12, 1), date(2026, 3, 26))
    assert w == 1.0  # within 180 days


def test_structural_365_days():
    w = calculate_decay_weight("structural", date(2025, 6, 1), date(2026, 3, 26))
    assert w == 0.8  # 181-365 days


def test_financial_no_decay():
    # Financial facts never decay by time
    w = calculate_decay_weight("financial", date(2020, 1, 1), date(2026, 3, 26))
    assert w == 1.0


def test_unknown_decay_class_raises():
    with pytest.raises(ValueError, match="Unknown decay_class"):
        calculate_decay_weight("unknown", date(2026, 1, 1), date(2026, 3, 26))
