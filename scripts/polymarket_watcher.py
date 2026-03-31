"""Polymarket watcher — daily check for resolved markets, price spikes, expiring."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

PRICE_SPIKE_THRESHOLD = 0.10  # 10% daily change
EXPIRY_HOURS_THRESHOLD = 24


class PolymarketWatcher:
    def __init__(self, *, adapter, run_store, watchlist: list[str]):
        self._adapter = adapter
        self._store = run_store
        self._watchlist = watchlist

    def check_market(self, condition_id: str) -> list[dict]:
        """Check a single market for events."""
        events = []
        try:
            market = self._adapter.get_market(condition_id)
        except Exception as e:
            logger.warning(f"Failed to fetch market {condition_id}: {e}")
            return events

        if market.get("resolved"):
            events.append({
                "type": "resolved",
                "condition_id": condition_id,
                "outcome": market.get("outcome"),
                "final_price": market.get("final_price"),
            })
            return events

        price_change = abs(market.get("price_change_24h", 0))
        if price_change >= PRICE_SPIKE_THRESHOLD:
            events.append({
                "type": "price_spike",
                "condition_id": condition_id,
                "price_change_24h": price_change,
                "current_price": market.get("yes_price"),
            })

        hours_to_expiry = market.get("hours_to_expiry", float("inf"))
        if hours_to_expiry < EXPIRY_HOURS_THRESHOLD:
            events.append({
                "type": "expiring_soon",
                "condition_id": condition_id,
                "hours_to_expiry": hours_to_expiry,
            })

        return events

    def run(self) -> dict:
        """Run full check cycle across all watchlist markets."""
        all_events = []
        for cid in self._watchlist:
            events = self.check_market(cid)
            all_events.extend(events)

        resolved = [e for e in all_events if e["type"] == "resolved"]
        alerts = [e for e in all_events if e["type"] in ("price_spike", "expiring_soon")]

        return {
            "checked": len(self._watchlist),
            "resolved": len(resolved),
            "alerts": len(alerts),
            "events": all_events,
        }


if __name__ == "__main__":
    import json
    from lib.db import get_connection, init_db
    from lib.run_store import RunStore
    from lib.config import HarnessConfig
    from lib.watchlist import list_tickers

    project_root = Path(__file__).parent.parent
    config = HarnessConfig(project_root / "config")
    conn = get_connection(str(project_root / "harness.db"))
    init_db(conn)
    store = RunStore(conn)

    wl_path = project_root / "config" / "local" / "watchlist.json"
    poly_tickers = list_tickers(wl_path, market="polymarket")
    condition_ids = [t.get("condition_id", t.get("ticker", "")) for t in poly_tickers]

    if not condition_ids:
        print(json.dumps({"status": "skipped", "reason": "no_polymarket_watchlist"}))
        sys.exit(0)

    from adapters.market_data import get_adapter
    adapter = get_adapter("polymarket")

    watcher = PolymarketWatcher(adapter=adapter, run_store=store, watchlist=condition_ids)
    result = watcher.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
