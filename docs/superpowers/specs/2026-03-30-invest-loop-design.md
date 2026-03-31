# Invest Loop: Rolling Closed-Loop Investment Research System

**Date:** 2026-03-30
**Status:** Approved Design
**Approach:** Skill-Orchestrated (OpenClaw + ClawClau + Codex/Claude agents)

## 1. Overview

A fully automated, closed-loop investment research system that:
1. **Scans** the knowledge base daily to discover investment opportunities across 4 markets
2. **Grades** opportunities (high/medium/low confidence) with tiered handling
3. **Verifies** hypotheses against post-market actuals
4. **Reviews** results nightly with knowledge base weight adjustments, rule proposals, and lesson extraction
5. **Feeds back** into the knowledge base for next-day improvement

### Markets Covered

| Market | Data Source (Primary) | Data Source (Fallback) |
|--------|----------------------|----------------------|
| A-stock | tushare | akshare |
| HK-stock | yfinance | - |
| US-stock | yfinance | - |
| Polymarket | CLOB API | - |

### Architecture Layers

| Layer | Responsibility | Does NOT do |
|-------|---------------|-------------|
| **Cron** | Time/event trigger, passes phase + market + date + trigger_source | Business logic |
| **OpenClaw invest-loop Skill** | Agent dispatch, fallback, timeout, retry, result routing to Feishu | Scoring, grading, card rules |
| **harness_cli** | All business logic: KB retrieval, LLM analysis, hypothesis generation, verification, review, feedback | Message delivery |

## 2. Trigger Architecture

```
TRIGGER LAYER
  Cron:   invest-loop job --phase scan --market a_stock --date YYYYMMDD
          invest-loop job --phase verify --market hk_stock --date YYYYMMDD
          invest-loop job --phase review --date YYYYMMDD
  Event:  polymarket_watcher (daily check for resolved markets)
  Manual: Feishu /harness scan --market us_stock

OPENCLAW invest-loop SKILL (pure orchestration)
  1. Generate run_id
  2. Dispatch to agent (Codex primary, Claude fallback, mutual)
  3. Timeout / retry / error handling
  4. Route result JSON to Feishu (card format determined by harness_cli)

    Codex Agent ◄──fallback──► Claude Agent
         └──────────┬───────────┘
                    ▼
         harness_cli <command> (all business logic)

HARNESS_CLI (business core)
  scan     → KB incremental + vector retrieval → LLM analysis → grading → hypothesis
  verify   → fetch actuals → 4-dimension scoring → verdict
  review   → aggregate verdicts → review → weight adjust → rule proposals → lessons
  feedback → execute approved rule changes
  watchlist→ add/remove/list tickers

  ┌──────────────────────────────────────────────────┐
  │ RUN STORE (lib/run_store.py)                     │
  │ run_id, batch_id, idempotency_key, phase,        │
  │ market, status, agent_trace, artifacts,           │
  │ deliveries, timestamps                            │
  └──────────────────────────────────────────────────┘

FEISHU DELIVERY
  gomamon:      scan results / review reports / low-confidence log
  gabumon:      medium-confidence approval cards (approve/reject buttons)
  kabuterimon:  error alerts
```

## 3. Cron Schedule (Beijing Time)

| Time | Phase | Market | Note |
|------|-------|--------|------|
| 08:30 | scan | a_stock | Mon-Fri, calendar-gated |
| 09:00 | scan | hk_stock | Mon-Fri |
| 21:30 | scan | us_stock | Mon-Fri |
| 20:00 | scan | polymarket | Daily |
| 20:30 | watcher | polymarket | Daily (check resolved/price spikes) |
| 15:30 | verify | a_stock | Mon-Fri |
| 16:30 | verify | hk_stock | Mon-Fri |
| 05:00 (next day) | verify | us_stock | Tue-Sat (previous day) |
| 21:00 | review | all | Mon-Fri |

Polymarket verify is event-driven: watcher detects resolved markets and triggers verify immediately.
Trading day checks are handled by harness_cli's calendar module; non-trading days auto-skip.

## 4. Object Model

### 4.1 RunRecord

```
RunRecord
├── run_id: str (UUID)
├── batch_id: str (YYYYMMDD-{phase}-{market}) — human-readable batch label
├── idempotency_key: str (sha256 of batch_id + watchlist_hash + knowledge_fingerprint))
│   └── batch_id is NOT the dedup key; idempotency_key is
├── phase: enum(scan, verify, review, feedback, watchlist_change)
├── market: enum(a_stock, hk_stock, us_stock, polymarket, global)
├── trigger_source: enum(cron, manual, event)
├── status: enum(pending, running, completed, failed, skipped)
├── agent_trace: list[{agent: codex|claude|local, started_at, ended_at, status}]
├── artifacts: dict (file paths to outputs)
├── created_at / updated_at / completed_at
└── error: str | null
```

### 4.2 DeliveryRecord

```
DeliveryRecord
├── delivery_id: str (UUID)
├── run_id: str → RunRecord
├── target: str (gomamon / gabumon / kabuterimon)
├── message_kind: enum(scan_result, approval, review, alert, rule_proposal)
├── card_template: str
├── requires_action: bool — distinguishes notification from approval
├── status: enum(pending, sent, failed)
├── action_status: enum(null, approved, rejected) — only if requires_action=true
├── idempotency_key: str (run_id + target + message_kind)
└── sent_at / action_at
```

### 4.3 ScanCandidate

```
ScanCandidate
├── candidate_id: str (UUID)
├── run_id: str → RunRecord
├── market: str
├── primary_ticker: str — must be from watchlist
├── related_tickers: list[str] — may extend beyond watchlist
├── direction: enum(long, short, neutral)
├── confidence: enum(high, medium, low)
├── thesis: str (one-sentence thesis)
├── evidence: list[EvidenceRef]
│   ├── fact_id: str
│   ├── source_file: str
│   ├── relevance_score: float
│   └── snippet: str
├── suggested_entry / suggested_exit / stop_loss: float
├── time_horizon: str (1d, 3d, 1w, 1m)
├── risk_factors: list[str]
└── auto_action: enum(auto_lock, await_approval, log_only)
    └── high→auto_lock, medium→await_approval, low→log_only
```

### 4.4 HypothesisRecord

Extends existing hypothesis schema. Created from ScanCandidate when confidence >= medium.

```
HypothesisRecord (extends existing)
├── hypothesis_id: str
├── candidate_id: str → ScanCandidate (provenance)
├── batch_id: str → RunRecord.batch_id
├── run_id: str → RunRecord
├── ... (existing hypothesis fields: market, direction, entry, exit, etc.)
└── status: enum(draft, locked, verified, rejected)
```

### 4.5 FeedbackRecord

```
FeedbackRecord
├── feedback_id: str
├── run_id: str → review RunRecord
├── source_hypothesis_id: str
├── verdict: enum(hit, partial_hit, miss, invalidated)
├── weight_adjustments: list[{fact_id, old_weight, new_weight, reason}]
├── rule_proposals: list[{proposal_id, rule_id?, action: add|modify|deprecate, diff, rationale, status: pending_approval|approved|rejected}]
└── lessons: list[{insight_text, category, tickers}]
    └── written to curated/insights.jsonl
```

## 5. Command Specifications

### 5.1 scan

```
harness_cli scan --market <market> --date <YYYYMMDD> [--watchlist <path>] [--no-notify]
```

**Flow:**

1. **Init** — Generate run_id. Compute knowledge_fingerprint from KB metadata (before retrieval). Compute idempotency_key = sha256(batch_id + watchlist_hash + knowledge_fingerprint). If completed run with same idempotency_key exists → return previous artifacts, status=skipped.

2. **Incremental KB retrieval** — Query knowledge/normalized/ for facts updated in last N days (default 3, auto-extend on Monday/post-holiday). Filter by: status=active, decay not expired, related to watchlist tickers/companies/industries.

3. **Vector retrieval** — For each watchlist ticker: ChromaDB query (ticker + company + industry + "investment opportunity risk"), top_k=5 from normalized_facts + curated_insights. Merge-dedup with incremental results by fact_id. Discard relevance_score < 0.3.

4. **Historical performance** — Load last 30 days of verify verdicts per ticker from run_store. Aggregate hit_rate, avg_magnitude_error.

5. **Context budget control** — Per ticker: max 10 facts, max 200 chars per snippet, max 5 insights. Total prompt budget: configurable (default 8000 tokens context).

6. **LLM analysis** — Build prompt (prompts/scan.md) with context_bundle + active rules. Call harness's own LLM API. Parse output into ScanCandidate[].

7. **Validation** — Layer 1 (schema): field completeness, type correctness. Layer 2 (business): evidence must reference valid fact_ids, primary_ticker must be in watchlist, confidence grade consistency.

8. **Auto-lock gate** (for high confidence only) — Must pass: evidence_count >= 2, independent_sources >= 2, not in blacklist, ticker historical miss_rate < 70%. Fail any gate → downgrade to medium (await_approval).

9. **Tiered processing** — high: save HypothesisRecord + auto_lock. medium: save HypothesisRecord(status=draft), await approval. low: save ScanCandidate only.

10. **Output** — JSON with run_id, batch_id, summary, candidates[], hypotheses[], card_data.

**Degradation strategy:**
- Vector retrieval fails → fall back to recent_facts only
- Historical performance missing → mark as "unavailable" in prompt
- LLM parse fails → retry once with stricter prompt; if still fails → RunRecord(status=failed)
- Zero candidates → status=completed (no opportunities is a valid result)

### 5.2 verify

```
harness_cli verify --market <market> --date <YYYYMMDD>
                   [--hypothesis-id <id>] [--batch-id <id>] [--no-notify]
```

**Flow:**

1. **Init** — Generate run_id, idempotency_key. Skip already-verified hypotheses.

2. **Load hypotheses** — Mode A (market+date): all LOCKED hypotheses for market on date. Mode B (hypothesis-id): single. Mode C (batch-id): all from that scan batch. Filter out already verified.

3. **Fetch actuals** — Per market adapter with fallback: a_stock: tushare → akshare. hk/us: yfinance. polymarket: CLOB API. Validate: non-empty, date match, price sanity. All adapters fail → status=failed.

4. **Verify** — Existing VerificationEngine: 4-dimension scoring (direction, magnitude, time_window, cause). Verdict: hit/partial_hit/miss/invalidated/unconfirmed.

5. **Output** — JSON with results[], summary.

### 5.3 review

```
harness_cli review --date <YYYYMMDD>
                   [--review-window <ISO8601_interval>]
                   [--include-pending-us] [--no-notify]
```

**Flow:**

1. **Init** — Generate run_id. Determine review_window: default = last review cutoff → now. Record review_window_start, review_window_end, cutoff_at, included_verify_batch_ids[].

2. **Aggregate** — Load all verify results within review_window. Existing ReviewGenerator categorizes: true_hits, lucky_hits, true_misses, execution_gaps, rule_violations, regime_shifts, unconfirmed. ContrarianChallenger detects blind spots.

3. **Knowledge weight adjustment** — For each verified hypothesis's evidence fact_ids: hit → source_weight *= 1.05 (cap 1.0). miss → source_weight *= 0.90 (floor 0.1). partial_hit → no change. invalidated → fact status = "disputed". Update normalized/ metadata + ChromaDB metadata.

4. **Rule proposals** — LLM analyzes misses + execution_gaps against active rules. Output: [{proposal_id, rule_id?, action, diff, rationale}]. All proposals status=pending_approval. Write to reviews/{date}/rule_proposals.json.

5. **Lesson extraction** — LLM distills reusable lessons from review + 30-day trend. Dedup against existing curated/insights.jsonl. Append new insights. Index in ChromaDB.

6. **Generate report** — Existing markdown + new sections: weight adjustments, rule proposals, lessons.

7. **Output** — JSON with review_window, summary, feedback (weight_adjustments count, rule_proposals count, lessons count), card_data.

### 5.4 feedback

```
harness_cli feedback --approve-rule <proposal_id> [--no-notify]
harness_cli feedback --reject-rule <proposal_id> [--reason <text>] [--no-notify]
```

Executes approved rule changes via RuleEngine. Updates proposal status in rule_proposals.json. Triggered by Feishu card button callbacks.

### 5.5 watchlist

```
harness_cli watchlist add --ticker <ticker> --market <market>
harness_cli watchlist remove --ticker <ticker> --market <market>
harness_cli watchlist list [--market <market>]
```

Auto-detects market from ticker suffix (.SZ/.SH → a_stock, .HK → hk_stock, pure alpha → us_stock). Records changes to run_store for audit. Feishu trigger: `/harness watchlist add 300750.SZ`.

## 6. Idempotency & Recovery

| Scenario | Behavior |
|----------|----------|
| scan duplicate trigger (same idempotency_key) | status=skipped, return previous artifacts |
| scan failed, re-triggered | New run_id, same batch_id, re-execute |
| verify: some hypotheses already verified | Only verify unverified ones |
| verify: non-trading day | status=skipped, reason="non_trading_day" |
| review: US verify later than review | Next day review auto-includes previous day US results via review_window |
| review: duplicate trigger | Append incremental new verify results, don't overwrite |
| agent fallback | Same run_id continues, agent_trace updated |
| delivery failed | DeliveryRecord status=failed, retried on next trigger |
| watchlist add existing ticker | noop |

## 7. Closed-Loop Data Flow

```
Day 1 08:30              Day 1 15:30          Day 1 21:00
    scan                    verify               review
     │                       │                    │
     ▼                       ▼                    ▼
 knowledge ──→ candidates ──→ hypotheses ──→ verdicts ──→ feedback
 (read)        (write)       (write)        (write)      │  │  │
                                                         │  │  │
                                         weight_adjust ◄─┘  │  │
                                         (knowledge write)   │  │
                                                             │  │
                                         rule_proposals ◄────┘  │
                                         (pending_approval)     │
                                              │                 │
                                         human approval         │
                                              │                 │
                                         feedback --approve     │
                                         (rules write)          │
                                                                │
                                         lessons ◄──────────────┘
                                         (curated/insights write)
                                              │
Day 2 08:30                                   ▼
    scan ◄──── reads updated knowledge: weights adjusted,
               lessons deposited, rules updated
     │
     ▼
  More accurate screening (loop closed)
```

## 8. OpenClaw invest-loop Skill

### 8.1 File Structure

```
~/.openclaw/workspace/skills/invest-loop/
├── SKILL.md
├── scripts/
│   ├── dispatch.sh
│   └── fallback.sh
└── templates/
    ├── scan_card.json
    ├── approval_card.json
    ├── review_card.json
    └── rule_proposal_card.json
```

### 8.2 Skill Behavior

- Triggers: cron, manual (`/invest scan a_stock`), callback (`/invest approve H123`)
- Dispatches via ClawClau: Codex primary, Claude fallback, mutual fallback
- Timeouts: scan 600s, verify 300s, review 900s, feedback 60s
- Parses harness_cli JSON output, extracts card_data, routes to Feishu groups
- Delivery failures logged, retried on next trigger

### 8.3 Feishu Card Interactions

**Scan result card** → gomamon: Shows high (auto-locked) / medium (with approve/reject buttons) / low (summary). Includes run metadata.

**Approval card** → gabumon: Per-hypothesis detail with thesis, evidence, parameters, risk factors. Buttons: approve (→ `/invest approve H_id`) / reject (→ `/invest reject H_id`).

**Review card** → gomamon: Daily summary with hit/miss stats, trend, weight adjustments, rule proposals (with approve/reject buttons), lessons learned.

**Rule proposal card** → gomamon: Per-proposal detail with diff, rationale. Buttons: approve / reject.

## 9. Polymarket Event-Driven Model

Unlike stock markets (time-triggered scan/verify), Polymarket uses:
- **Daily scan** (20:00): Full KB + CLOB API analysis for pricing inefficiencies
- **Daily watcher** (20:30): Check for resolved markets, price spikes (>10% daily), expiring (<24h). Resolved → trigger verify immediately. Price spike / expiring → L1/L2 alert.

Polymarket verify dimensions simplified: direction (correct outcome?) + magnitude (price differential profit).

## 10. Data Adapter Configuration

```json
{
  "adapters": {
    "a_stock": { "primary": "tushare", "fallback": "akshare" },
    "hk_stock": { "primary": "yfinance", "fallback": null },
    "us_stock": { "primary": "yfinance", "fallback": null },
    "polymarket": { "primary": "clob_api", "fallback": null }
  }
}
```

Credentials stored in config/local/.env:
- TUSHARE_TOKEN, TUSHARE_API_URL
- POLYMARKET_API_KEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE, POLYMARKET_PRIVATE_KEY

## 11. New & Modified Files

### New Files

| File | Purpose |
|------|---------|
| `lib/run_store.py` | RunRecord, DeliveryRecord, ScanCandidate, FeedbackRecord CRUD (SQLite) |
| `lib/scanner.py` | scan command core logic |
| `lib/feedback_engine.py` | feedback command (weight adjust, rule execution) |
| `lib/adapters/akshare_adapter.py` | akshare data adapter |
| `lib/adapters/yfinance_adapter.py` | yfinance data adapter |
| `scripts/polymarket_watcher.py` | Daily Polymarket event checker |
| `prompts/scan.md` | Scan analysis LLM prompt |
| `prompts/rule_proposal.md` | Rule proposal LLM prompt |
| `prompts/lesson_extract.md` | Lesson extraction LLM prompt |
| `schemas/scan_candidate.schema.json` | ScanCandidate JSON schema |
| `schemas/run_record.schema.json` | RunRecord JSON schema |
| `schemas/feedback.schema.json` | FeedbackRecord JSON schema |
| `~/.openclaw/workspace/skills/invest-loop/` | OpenClaw skill (SKILL.md, scripts, templates) |

### Modified Files

| File | Change |
|------|--------|
| `scripts/harness_cli.py` | Add scan, feedback, watchlist command entries |
| `scripts/harness_inbound.py` | Route /harness watchlist, /invest commands |
| `scripts/cron_dispatch.sh` | De-businessify: unified job dispatch |
| `lib/review.py` | Add weight adjustment, lesson extraction sections |
| `lib/verification.py` | Auto-fetch actuals with adapter fallback |
| `lib/hypothesis.py` | Lock/reject by id (Feishu callback support) |
| `lib/knowledge.py` | source_weight adjustment methods |
| `lib/chroma_client.py` | metadata.source_weight update |
| `lib/notifications.py` | card_data structured output |
| `config/default/runtime.json` | Add adapters config, scan config |
| `config/local/watchlist.json` | Extended structure with metadata |
| `schemas/hypothesis.schema.json` | Add batch_id, run_id, candidate_id refs |

## 12. Future Enhancements (Not in MVP)

- Historical performance granularity: ticker x thesis_type (avoid cross-contamination)
- Multi-model ensemble for scan (run 2+ LLMs, cross-validate)
- Feishu interactive charts (price charts in cards)
- Portfolio-level risk aggregation across markets
- Automated position sizing based on confidence + historical performance
