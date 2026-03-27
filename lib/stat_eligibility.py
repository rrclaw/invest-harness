"""Statistical eligibility matrix.

Iron Law 3: Incomplete evidence = excluded from all statistical pools.
"No complete credentials, no entry."
"""

REQUIRED_AUDIT_FIELDS = {
    "model_version",
    "prompt_hash",
    "generated_at",
    "prompt_ref",
    "fallback_used",
    "idempotency_key",
}


def check_eligibility(
    status: str,
    audit: dict,
    amend_log: list,
    fallback_used: bool,
    invalidation_type: str | None,
) -> dict:
    """Determine statistical eligibility for a hypothesis."""
    result = {
        "stat_eligible": False,
        "win_rate_pool": False,
        "rule_iteration_pool": False,
        "backtest_pool": False,
        "reason": "",
    }

    present_fields = set(audit.keys())
    if not REQUIRED_AUDIT_FIELDS.issubset(present_fields):
        missing = REQUIRED_AUDIT_FIELDS - present_fields
        result["reason"] = f"Audit fields incomplete: missing {missing}"
        return result

    if status == "unconfirmed":
        result["reason"] = "unconfirmed hypothesis"
        return result

    if status == "amended" and not amend_log:
        result["reason"] = "amended but amend_log is empty"
        return result

    result["stat_eligible"] = True

    if invalidation_type == "pre_trigger":
        result["win_rate_pool"] = False
        result["rule_iteration_pool"] = True
        result["backtest_pool"] = False
        result["reason"] = "pre-trigger invalidation: disproval valid for rules"
        return result

    if invalidation_type == "post_trigger":
        result["win_rate_pool"] = True
        result["rule_iteration_pool"] = True
        result["backtest_pool"] = True
        result["reason"] = "post-trigger invalidation: full participation"
        return result

    if fallback_used:
        result["win_rate_pool"] = True
        result["rule_iteration_pool"] = False
        result["backtest_pool"] = False
        result["reason"] = "fallback engine used: win-rate only"
        return result

    if status == "amended":
        result["win_rate_pool"] = True
        result["rule_iteration_pool"] = True
        result["backtest_pool"] = False
        result["reason"] = "amended with complete log: no backtest"
        return result

    result["win_rate_pool"] = True
    result["rule_iteration_pool"] = True
    result["backtest_pool"] = True
    result["reason"] = "fully eligible"
    return result
