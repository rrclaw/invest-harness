import pytest
from lib.db import get_connection, init_db
from lib.state_machine import (
    StateMachine,
    InvalidTransition,
    VALID_STATES,
    POLYMARKET_STATES,
)


@pytest.fixture
def sm(tmp_harness):
    conn = get_connection(tmp_harness)
    init_db(conn)
    return StateMachine(conn)


def test_valid_states_defined():
    assert "IDLE" in VALID_STATES
    assert "HYPOTHESIS_DRAFT" in VALID_STATES
    assert "LOCKED" in VALID_STATES
    assert "MONITORING" in VALID_STATES
    assert "VERIFYING" in VALID_STATES
    assert "REVIEWED" in VALID_STATES
    assert "ERROR" in VALID_STATES
    assert "SUSPENDED" in VALID_STATES


def test_polymarket_states_subset():
    # Polymarket has no MONITORING or VERIFYING
    assert "MONITORING" not in POLYMARKET_STATES
    assert "VERIFYING" not in POLYMARKET_STATES
    assert "LOCKED" in POLYMARKET_STATES


def test_initialize_market(sm):
    sm.initialize("a_stock", "2026-03-26")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "IDLE"
    assert state["exchange_date"] == "2026-03-26"


def test_transition_idle_to_hypo_draft(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "HYPOTHESIS_DRAFT"
    assert state["previous_state"] == "IDLE"


def test_transition_full_lifecycle(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    sm.transition("a_stock", "LOCKED")
    sm.transition("a_stock", "MONITORING")
    sm.transition("a_stock", "VERIFYING")
    sm.transition("a_stock", "REVIEWED")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "REVIEWED"


def test_invalid_transition_raises(sm):
    sm.initialize("a_stock", "2026-03-26")
    # IDLE -> MONITORING is not valid (must go through HYPO_DRAFT -> LOCKED first)
    with pytest.raises(InvalidTransition):
        sm.transition("a_stock", "MONITORING")


def test_any_state_can_go_to_error(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "HYPOTHESIS_DRAFT")
    sm.transition("a_stock", "ERROR", error_detail="API timeout")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "ERROR"
    assert state["error_detail"] == "API timeout"


def test_error_retry_increments(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm.transition("a_stock", "ERROR", error_detail="fail1")
    state = sm.get_state("a_stock")
    assert state["retry_count"] == 1
    sm.transition("a_stock", "ERROR", error_detail="fail2")
    state = sm.get_state("a_stock")
    assert state["retry_count"] == 2


def test_suspended_from_l1(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm._force_state("a_stock", "MONITORING")
    sm.transition("a_stock", "SUSPENDED")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "SUSPENDED"


def test_suspended_requires_human_to_lift(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm._force_state("a_stock", "SUSPENDED")
    # Only valid exit from SUSPENDED is back to previous state via human
    sm.lift_suspension("a_stock")
    state = sm.get_state("a_stock")
    assert state["current_state"] != "SUSPENDED"


def test_polymarket_lifecycle(sm):
    sm.initialize("polymarket", "2026-03-26")
    sm.transition("polymarket", "HYPOTHESIS_DRAFT")
    sm.transition("polymarket", "LOCKED")
    sm.transition("polymarket", "REVIEWED")
    state = sm.get_state("polymarket")
    assert state["current_state"] == "REVIEWED"


def test_polymarket_cannot_enter_monitoring(sm):
    sm.initialize("polymarket", "2026-03-26")
    sm._force_state("polymarket", "LOCKED")
    with pytest.raises(InvalidTransition):
        sm.transition("polymarket", "MONITORING")


def test_get_state_unknown_market(sm):
    with pytest.raises(KeyError):
        sm.get_state("crypto")


def test_reset_to_idle(sm):
    sm.initialize("a_stock", "2026-03-26")
    sm._force_state("a_stock", "REVIEWED")
    sm.reset_to_idle("a_stock", "2026-03-27")
    state = sm.get_state("a_stock")
    assert state["current_state"] == "IDLE"
    assert state["exchange_date"] == "2026-03-27"
