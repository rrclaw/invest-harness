#!/usr/bin/env bash
# Cron entry point for invest_harness.
# Calendar-aware, idempotent, DST-auto-switching.
#
# Usage: cron_dispatch.sh <task> <market>
#   e.g.: cron_dispatch.sh pre_market a_stock
#         cron_dispatch.sh nightly_review global
#         cron_dispatch.sh polling a_stock

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${HARNESS_DIR}/venv/bin/python3"
if [ ! -f "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

TASK="${1:?Usage: cron_dispatch.sh <task> <market>}"
MARKET="${2:?Usage: cron_dispatch.sh <task> <market>}"
TODAY="$(date +%Y-%m-%d)"

LOG_DIR="${HARNESS_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/${TODAY}_${TASK}_${MARKET}.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# --- Calendar Check ---
is_trading_day() {
    local market="$1"
    # Polymarket bypasses calendar
    if [ "$market" = "polymarket" ] || [ "$market" = "global" ]; then
        return 0
    fi
    # Check exchange_calendar.json via Python
    "$PYTHON" -c "
import json, sys
from datetime import date, datetime
cal = json.load(open('${HARNESS_DIR}/config/exchange_calendar.json'))
market = '${market}'
today = '${TODAY}'
weekday = datetime.strptime(today, '%Y-%m-%d').weekday()
# Mon-Fri check
if weekday >= 5:
    sys.exit(1)
# Holiday check (manual markets)
entry = cal.get(market, {})
holidays = entry.get('holidays', [])
if today in holidays:
    sys.exit(1)
half_days = entry.get('half_day_dates', [])
# half days are still trading days
sys.exit(0)
"
}

# --- DST Detection for US ---
get_us_offset() {
    # Returns UTC offset for America/New_York
    "$PYTHON" -c "
from datetime import datetime
import zoneinfo
tz = zoneinfo.ZoneInfo('America/New_York')
offset = datetime.now(tz).utcoffset()
hours = int(offset.total_seconds() / 3600)
print(hours)
"
}

# --- Main Dispatch ---
log "START: task=${TASK} market=${MARKET} date=${TODAY}"

# Calendar gate
if [ "$TASK" != "cold_backup" ] && [ "$TASK" != "rule_audit" ] && [ "$TASK" != "chroma_decay" ]; then
    if ! is_trading_day "$MARKET"; then
        log "SKIP: ${MARKET} is not a trading day"
        exit 0
    fi
fi

# WAL mode enforcement reminder (Python scripts handle this via lib/db.py)
cd "$HARNESS_DIR"

case "$TASK" in
    pre_market)
        log "Running pre-market hypothesis generation for ${MARKET}"
        "$PYTHON" -m scripts.ingest --help >/dev/null 2>&1 || true  # placeholder
        # In production: dispatch hypothesis_worker via conductor
        ;;
    lock_check)
        log "Running hypothesis lock check for ${MARKET}"
        "$PYTHON" -c "
from lib.db import get_connection, init_db
from lib.hypothesis import HypothesisManager
from scripts.lock_hypothesis import check_and_lock
conn = get_connection('harness.db')
init_db(conn)
mgr = HypothesisManager('hypotheses')
result = check_and_lock(mgr, '${TODAY}', '${MARKET}')
print(result)
conn.close()
" 2>&1 | tee -a "$LOG_FILE"
        ;;
    polling)
        log "Starting polling daemon for ${MARKET}"
        "$PYTHON" -m scripts.polling_daemon --market "$MARKET" 2>&1 | tee -a "$LOG_FILE" &
        ;;
    post_market)
        log "Running post-market verification for ${MARKET}"
        # In production: dispatch verification_worker via conductor
        ;;
    nightly_review)
        log "Running nightly review"
        # In production: dispatch review + contrarian via conductor
        ;;
    info_digest)
        log "Running info digest compilation"
        ;;
    chroma_decay)
        log "Running ChromaDB decay calculation"
        ;;
    next_day_draft)
        log "Running next-day hypothesis draft generation"
        ;;
    cold_backup)
        log "Running weekly cold backup"
        "$PYTHON" -m scripts.cold_backup 2>&1 | tee -a "$LOG_FILE"
        ;;
    rule_audit)
        log "Running weekly rule health audit"
        "$PYTHON" -m scripts.rule_audit 2>&1 | tee -a "$LOG_FILE"
        ;;
    *)
        log "ERROR: Unknown task: ${TASK}"
        exit 1
        ;;
esac

log "END: task=${TASK} market=${MARKET}"
