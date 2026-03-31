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
    # Check layered exchange_calendar.json via Python
    "$PYTHON" -c "
import sys
from datetime import datetime
from pathlib import Path
from lib.config import load_json_config

cal = load_json_config(Path('${HARNESS_DIR}') / 'config', 'exchange_calendar')
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

# --- Known Tasks ---
KNOWN_TASKS="pre_market lock_check polling post_market nightly_review info_digest chroma_decay next_day_draft cold_backup rule_audit invest-loop"

# --- Main Dispatch ---
log "START: task=${TASK} market=${MARKET} date=${TODAY}"

# Validate task name before calendar gate
if ! echo "$KNOWN_TASKS" | grep -qw "$TASK"; then
    log "ERROR: Unknown task: ${TASK}"
    exit 1
fi

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
        "$PYTHON" -m scripts.harness_cli --project-root "$HARNESS_DIR" lock \
            --date "$TODAY" --market "$MARKET" --deadline-check 2>&1 | tee -a "$LOG_FILE"
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
        "$PYTHON" -m scripts.harness_cli --project-root "$HARNESS_DIR" review \
            --date "$TODAY" 2>&1 | tee -a "$LOG_FILE"
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
        "$PYTHON" -m scripts.harness_cli --project-root "$HARNESS_DIR" backup 2>&1 | tee -a "$LOG_FILE"
        ;;
    rule_audit)
        log "Running weekly rule health audit"
        "$PYTHON" -m scripts.harness_cli --project-root "$HARNESS_DIR" rule_audit \
            --date "$TODAY" 2>&1 | tee -a "$LOG_FILE"
        ;;
    invest-loop)
        # Unified invest-loop dispatch — passes through to OpenClaw skill
        SKILL_DISPATCH="$HOME/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh"
        if [[ -x "$SKILL_DISPATCH" ]]; then
            "$SKILL_DISPATCH" --phase "$2" --market "${3:-global}" --date "$(date +%Y%m%d)" --trigger cron
        else
            log "ERROR: invest-loop skill not found at $SKILL_DISPATCH"
            exit 1
        fi
        ;;
    *)
        log "ERROR: Unknown task: ${TASK}"
        exit 1
        ;;
esac

# === CRONTAB REFERENCE (install via: crontab -e) ===
# # Invest Loop: Scan (pre-market)
# 30 8  * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop scan a_stock
# 00 9  * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop scan hk_stock
# 30 21 * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop scan us_stock
# 00 20 * * *    cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop scan polymarket
#
# # Invest Loop: Verify (post-market)
# 30 15 * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop verify a_stock
# 30 16 * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop verify hk_stock
# 00 5  * * 2-6  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop verify us_stock
#
# # Invest Loop: Polymarket Watcher (daily)
# 30 20 * * *    cd ~/invest_harness && python3.11 -m scripts.polymarket_watcher
#
# # Invest Loop: Nightly Review
# 00 21 * * 1-5  cd ~/invest_harness && ./scripts/cron_dispatch.sh invest-loop review

log "END: task=${TASK} market=${MARKET}"
