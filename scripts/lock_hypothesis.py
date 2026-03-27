"""Hypothesis lock check at deadline.

Called at hypothesis_lock time from cron. If hypothesis is still draft
(no human approval), marks it as unconfirmed and fires L2 alert.
"""

from lib.hypothesis import HypothesisManager


def check_and_lock(mgr: HypothesisManager, date: str, market: str) -> dict:
    """Check hypothesis lock status at deadline.

    Returns dict with 'action': 'already_locked' | 'unconfirmed' | 'no_hypothesis'.
    """
    hypo = mgr.load_for_date(date, market)

    if hypo is None:
        return {"action": "no_hypothesis", "market": market, "date": date}

    if mgr.is_locked(date, market) or hypo["status"] == "locked":
        return {"action": "already_locked", "market": market, "date": date}

    # Deadline reached without approval -> mark unconfirmed
    mgr.mark_unconfirmed(date, market)
    return {
        "action": "unconfirmed",
        "market": market,
        "date": date,
        "hypothesis_id": hypo["hypothesis_id"],
    }
