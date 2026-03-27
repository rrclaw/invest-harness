"""Intraday snapshot builder.

Produces monitor_snapshot.schema.json-compliant output.
Pure observation -- no trading decisions.
"""

from datetime import datetime, timezone


def build_snapshot(
    market: str,
    data_source: str,
    quotes: list,
    hypotheses: list[dict],
    health_status: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    snapshot_id = f"snap_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{market}_{datetime.now(timezone.utc).strftime('%H%M')}"

    quote_map = {q.ticker: q for q in quotes}
    hypothesis_checks = []
    for hypo in hypotheses:
        ticker = hypo.get("ticker")
        check = {
            "hypothesis_ref": hypo["hypothesis_id"],
            "trigger_status": "not_triggered",
            "trigger_detail": None,
            "invalidation_status": "not_triggered",
            "invalidation_detail": None,
        }
        if ticker in quote_map:
            q = quote_map[ticker]
            check["trigger_detail"] = f"Price={q.price}, Change={q.change_pct}%"
        hypothesis_checks.append(check)

    return {
        "snapshot_id": snapshot_id,
        "snapshot_time": now,
        "data_source": data_source,
        "market": market,
        "hypothesis_checks": hypothesis_checks,
        "unexpected_events": [],
        "market_summary": None,
        "health_check": {
            "consecutive_failures": health_status["consecutive_failures"],
            "last_heartbeat": health_status["last_heartbeat"],
            "circuit_broken": health_status["circuit_broken"],
            "adapter_status": health_status["adapter_status"],
        },
    }
