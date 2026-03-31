# Invest Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rolling closed-loop investment research system that daily scans the knowledge base for opportunities, verifies hypotheses against actuals, and feeds results back into the knowledge base.

**Architecture:** OpenClaw invest-loop skill dispatches Codex/Claude agents (with mutual fallback) to execute harness_cli commands. New commands: scan, feedback, watchlist. Extended commands: verify (auto-fetch actuals), review (weight adjustment + rule proposals + lessons). All business logic in harness_cli; OpenClaw skill is pure orchestration.

**Tech Stack:** Python 3.11, SQLite (WAL), ChromaDB, tushare, akshare, yfinance, Polymarket CLOB API, Feishu interactive cards, OpenClaw ClawClau.

**Spec:** `docs/superpowers/specs/2026-03-30-invest-loop-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `lib/run_store.py` | RunRecord, DeliveryRecord, ScanCandidate, FeedbackRecord — SQLite CRUD + idempotency |
| `lib/scanner.py` | scan command core: KB retrieval, LLM analysis, candidate grading, hypothesis generation |
| `lib/feedback_engine.py` | feedback command: weight adjustment execution, rule proposal application |
| `adapters/adapter_akshare.py` | AkshareAdapter — A-stock fallback data source |
| `adapters/adapter_yfinance.py` | YfinanceAdapter — HK/US stock data source |
| `adapters/adapter_polymarket.py` | PolymarketAdapter — prediction market data source |
| `scripts/polymarket_watcher.py` | Daily Polymarket event checker (resolved markets, price spikes) |
| `prompts/scan.md` | LLM prompt template for scan analysis |
| `prompts/rule_proposal.md` | LLM prompt template for rule change proposals |
| `prompts/lesson_extract.md` | LLM prompt template for lesson extraction |
| `schemas/scan_candidate.schema.json` | ScanCandidate JSON schema |
| `schemas/run_record.schema.json` | RunRecord JSON schema |
| `schemas/feedback.schema.json` | FeedbackRecord JSON schema |
| `tests/test_run_store.py` | Run store tests |
| `tests/test_scanner.py` | Scanner tests |
| `tests/test_feedback_engine.py` | Feedback engine tests |
| `tests/test_adapter_akshare.py` | Akshare adapter tests |
| `tests/test_adapter_yfinance.py` | Yfinance adapter tests |
| `tests/test_adapter_polymarket.py` | Polymarket adapter tests |
| `tests/test_watchlist_cmd.py` | Watchlist command tests |
| `tests/test_polymarket_watcher.py` | Polymarket watcher tests |

### Modified Files

| File | Change |
|------|--------|
| `lib/db.py` | Add runs, deliveries, candidates, feedbacks tables to init_db() |
| `scripts/harness_cli.py` | Add scan, feedback, watchlist command handlers |
| `scripts/harness_inbound.py` | Route /harness watchlist commands |
| `lib/verification.py` | Auto-fetch actuals via adapter fallback |
| `lib/review.py` | Add weight adjustment, rule proposal, lesson sections |
| `lib/knowledge.py` | Add update_source_weight() method |
| `lib/chroma_client.py` | Add update_fact_metadata() if missing |
| `lib/notifications.py` | Add card_data output methods |
| `adapters/market_data.py` | Register new adapters in factory |
| `config/default/runtime.json` | Add adapters config, scan config |
| `scripts/cron_dispatch.sh` | Add invest-loop job dispatch |

---

## Task Dependency Graph

```
Task 1 (DB schema) ──► Task 2 (Run Store) ──► Task 5 (Scanner)
                                             ▲
Task 3 (Akshare Adapter) ──────────────────►│
Task 4 (Yfinance Adapter) ─────────────────►│
                                             │
Task 3+4 ──► Task 6 (Verify auto-actuals)   │
                                             │
Task 2+6 ──► Task 7 (Review extensions)      │
Task 7 ──► Task 8 (Feedback command)         │
Task 2 ──► Task 9 (Watchlist command)        │
Task 5+6+7+8+9 ──► Task 10 (CLI wiring)     │
Task 10 ──► Task 11 (Polymarket watcher)     │
Task 10 ──► Task 12 (OpenClaw skill)         │
Task 12 ──► Task 13 (Cron setup)             │
Task 13 ──► Task 14 (Integration test)       │
```

---

### Task 1: Database Schema Extensions

**Files:**
- Modify: `lib/db.py`
- Test: `tests/test_run_store.py` (schema portion)

- [ ] **Step 1: Write failing test for new tables**

```python
# tests/test_run_store.py
import sqlite3
import pytest
from lib.db import get_connection, init_db


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "harness.db"
    conn = get_connection(str(db_path))
    init_db(conn)
    return conn


def test_runs_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
    )
    assert cursor.fetchone() is not None


def test_deliveries_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='deliveries'"
    )
    assert cursor.fetchone() is not None


def test_candidates_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidates'"
    )
    assert cursor.fetchone() is not None


def test_feedbacks_table_exists(db):
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='feedbacks'"
    )
    assert cursor.fetchone() is not None


def test_runs_idempotency_key_unique(db):
    db.execute(
        "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
        "VALUES ('r1', 'b1', 'key1', 'scan', 'a_stock', 'cron', 'pending', '[]', '{}', '2026-03-30T08:30:00', '2026-03-30T08:30:00')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
            "VALUES ('r2', 'b1', 'key1', 'scan', 'a_stock', 'cron', 'pending', '[]', '{}', '2026-03-30T08:31:00', '2026-03-30T08:31:00')"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_run_store.py::test_runs_table_exists -v`
Expected: FAIL — table "runs" does not exist

- [ ] **Step 3: Add table definitions to init_db()**

Read `lib/db.py` first. Then add to the `init_db()` function:

```python
# In lib/db.py init_db() — append after existing CREATE TABLE statements

conn.executescript("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        phase TEXT NOT NULL CHECK(phase IN ('scan','verify','review','feedback','watchlist_change')),
        market TEXT NOT NULL,
        trigger_source TEXT NOT NULL CHECK(trigger_source IN ('cron','manual','event')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','completed','failed','skipped')),
        agent_trace TEXT NOT NULL DEFAULT '[]',
        artifacts TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_runs_batch ON runs(batch_id);
    CREATE INDEX IF NOT EXISTS idx_runs_phase_market ON runs(phase, market);
    CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

    CREATE TABLE IF NOT EXISTS deliveries (
        delivery_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        target TEXT NOT NULL,
        message_kind TEXT NOT NULL,
        card_template TEXT,
        requires_action INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
        action_status TEXT CHECK(action_status IN (NULL,'approved','rejected')),
        idempotency_key TEXT NOT NULL UNIQUE,
        sent_at TEXT,
        action_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_deliveries_run ON deliveries(run_id);

    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        market TEXT NOT NULL,
        primary_ticker TEXT NOT NULL,
        related_tickers TEXT NOT NULL DEFAULT '[]',
        direction TEXT NOT NULL CHECK(direction IN ('long','short','neutral')),
        confidence TEXT NOT NULL CHECK(confidence IN ('high','medium','low')),
        thesis TEXT NOT NULL,
        evidence TEXT NOT NULL DEFAULT '[]',
        suggested_entry REAL,
        suggested_exit REAL,
        stop_loss REAL,
        time_horizon TEXT,
        risk_factors TEXT NOT NULL DEFAULT '[]',
        auto_action TEXT NOT NULL CHECK(auto_action IN ('auto_lock','await_approval','log_only')),
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
    CREATE INDEX IF NOT EXISTS idx_candidates_ticker ON candidates(primary_ticker);

    CREATE TABLE IF NOT EXISTS feedbacks (
        feedback_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        source_hypothesis_id TEXT,
        verdict TEXT,
        weight_adjustments TEXT NOT NULL DEFAULT '[]',
        rule_proposals TEXT NOT NULL DEFAULT '[]',
        lessons TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_feedbacks_run ON feedbacks(run_id);
""")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_run_store.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/invest_harness
git add lib/db.py tests/test_run_store.py
git commit -m "feat: add runs, deliveries, candidates, feedbacks tables to DB schema"
```

---

### Task 2: Run Store CRUD

**Files:**
- Create: `lib/run_store.py`
- Test: `tests/test_run_store.py` (extend)

- [ ] **Step 1: Write failing tests for RunStore**

Append to `tests/test_run_store.py`:

```python
from lib.run_store import RunStore
import json


@pytest.fixture
def store(db):
    return RunStore(db)


def test_create_run(store):
    run = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run["run_id"]
    assert run["batch_id"].endswith("-scan-a_stock")
    assert run["status"] == "pending"
    assert run["idempotency_key"]


def test_idempotent_run_skips(store):
    run1 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    store.update_status(run1["run_id"], "completed")

    run2 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run2["status"] == "skipped"
    assert run2["run_id"] == run1["run_id"]


def test_failed_run_allows_retry(store):
    run1 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    store.update_status(run1["run_id"], "failed", error="timeout")

    run2 = store.create_run(
        phase="scan",
        market="a_stock",
        trigger_source="cron",
        watchlist_hash="abc123",
        knowledge_fingerprint="def456",
    )
    assert run2["status"] == "pending"
    assert run2["run_id"] != run1["run_id"]


def test_update_agent_trace(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.append_agent_trace(run["run_id"], agent="codex", status="started")
    store.append_agent_trace(run["run_id"], agent="codex", status="completed")
    result = store.get_run(run["run_id"])
    trace = json.loads(result["agent_trace"])
    assert len(trace) == 2
    assert trace[0]["agent"] == "codex"


def test_save_candidate(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    cand = store.save_candidate(
        run_id=run["run_id"],
        market="a_stock",
        primary_ticker="600519.SH",
        direction="long",
        confidence="high",
        thesis="Strong Q1 earnings",
        evidence=[{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
        auto_action="auto_lock",
    )
    assert cand["candidate_id"]
    candidates = store.list_candidates(run["run_id"])
    assert len(candidates) == 1


def test_save_delivery(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    dlv = store.save_delivery(
        run_id=run["run_id"],
        target="gomamon",
        message_kind="scan_result",
        requires_action=False,
    )
    assert dlv["delivery_id"]
    assert dlv["status"] == "pending"


def test_save_feedback(store):
    run = store.create_run(
        phase="review", market="global", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    fb = store.save_feedback(
        run_id=run["run_id"],
        source_hypothesis_id="H1",
        verdict="hit",
        weight_adjustments=[{"fact_id": "f1", "old_weight": 0.7, "new_weight": 0.735}],
        rule_proposals=[],
        lessons=[{"insight_text": "lesson1", "category": "timing"}],
    )
    assert fb["feedback_id"]


def test_get_pending_deliveries(store):
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.save_delivery(run["run_id"], "gomamon", "scan_result", False)
    store.save_delivery(run["run_id"], "gabumon", "approval", True)
    pending = store.get_pending_deliveries()
    assert len(pending) == 2


def test_get_verify_history(store):
    # Create a completed verify run
    run = store.create_run(
        phase="verify", market="a_stock", trigger_source="cron",
        watchlist_hash="a", knowledge_fingerprint="b",
    )
    store.update_status(run["run_id"], "completed")
    history = store.get_runs_by_phase_and_window(
        phase="verify", start="2026-03-01T00:00:00", end="2026-04-01T00:00:00"
    )
    assert len(history) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_run_store.py::test_create_run -v`
Expected: FAIL — ModuleNotFoundError: No module named 'lib.run_store'

- [ ] **Step 3: Implement RunStore**

```python
# lib/run_store.py
"""Run Store — execution tracking, idempotency, and artifact management."""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _uuid() -> str:
    return str(uuid.uuid4())


class RunStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ── Runs ──

    def create_run(
        self,
        *,
        phase: str,
        market: str,
        trigger_source: str,
        watchlist_hash: str,
        knowledge_fingerprint: str,
        date: str | None = None,
    ) -> dict:
        date = date or datetime.now(timezone.utc).strftime("%Y%m%d")
        batch_id = f"{date}-{phase}-{market}"
        idempotency_key = hashlib.sha256(
            f"{batch_id}:{watchlist_hash}:{knowledge_fingerprint}".encode()
        ).hexdigest()

        # Check existing run with same idempotency_key
        existing = self._conn.execute(
            "SELECT run_id, status, artifacts FROM runs WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
            (idempotency_key,),
        ).fetchone()

        if existing:
            if existing["status"] == "completed":
                return {
                    "run_id": existing["run_id"],
                    "batch_id": batch_id,
                    "idempotency_key": idempotency_key,
                    "status": "skipped",
                    "artifacts": json.loads(existing["artifacts"]),
                }
            elif existing["status"] == "failed":
                # Delete old failed run so new one can use fresh idempotency_key
                self._conn.execute("DELETE FROM runs WHERE run_id = ?", (existing["run_id"],))
                self._conn.commit()
            elif existing["status"] in ("pending", "running"):
                return {
                    "run_id": existing["run_id"],
                    "batch_id": batch_id,
                    "idempotency_key": idempotency_key,
                    "status": existing["status"],
                }

        run_id = _uuid()
        now = _now()
        self._conn.execute(
            "INSERT INTO runs (run_id, batch_id, idempotency_key, phase, market, trigger_source, status, agent_trace, artifacts, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', '[]', '{}', ?, ?)",
            (run_id, batch_id, idempotency_key, phase, market, trigger_source, now, now),
        )
        self._conn.commit()
        return {
            "run_id": run_id,
            "batch_id": batch_id,
            "idempotency_key": idempotency_key,
            "status": "pending",
        }

    def get_run(self, run_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def update_status(self, run_id: str, status: str, *, error: str | None = None, artifacts: dict | None = None) -> None:
        now = _now()
        sets = ["status = ?", "updated_at = ?"]
        vals: list = [status, now]
        if error is not None:
            sets.append("error = ?")
            vals.append(error)
        if artifacts is not None:
            sets.append("artifacts = ?")
            vals.append(json.dumps(artifacts))
        if status == "completed":
            sets.append("completed_at = ?")
            vals.append(now)
        vals.append(run_id)
        self._conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", vals)
        self._conn.commit()

    def append_agent_trace(self, run_id: str, *, agent: str, status: str) -> None:
        row = self._conn.execute("SELECT agent_trace FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        trace = json.loads(row["agent_trace"]) if row else []
        trace.append({"agent": agent, "status": status, "at": _now()})
        self._conn.execute(
            "UPDATE runs SET agent_trace = ?, updated_at = ? WHERE run_id = ?",
            (json.dumps(trace), _now(), run_id),
        )
        self._conn.commit()

    def get_runs_by_phase_and_window(self, *, phase: str, start: str, end: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE phase = ? AND created_at >= ? AND created_at <= ? ORDER BY created_at",
            (phase, start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Candidates ──

    def save_candidate(self, *, run_id: str, market: str, primary_ticker: str,
                       direction: str, confidence: str, thesis: str,
                       evidence: list, auto_action: str,
                       related_tickers: list | None = None,
                       suggested_entry: float | None = None,
                       suggested_exit: float | None = None,
                       stop_loss: float | None = None,
                       time_horizon: str | None = None,
                       risk_factors: list | None = None) -> dict:
        candidate_id = _uuid()
        self._conn.execute(
            "INSERT INTO candidates (candidate_id, run_id, market, primary_ticker, related_tickers, "
            "direction, confidence, thesis, evidence, suggested_entry, suggested_exit, stop_loss, "
            "time_horizon, risk_factors, auto_action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, run_id, market, primary_ticker,
             json.dumps(related_tickers or []), direction, confidence, thesis,
             json.dumps(evidence), suggested_entry, suggested_exit, stop_loss,
             time_horizon, json.dumps(risk_factors or []), auto_action, _now()),
        )
        self._conn.commit()
        return {"candidate_id": candidate_id}

    def list_candidates(self, run_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM candidates WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_candidates_by_ticker(self, ticker: str, *, days: int = 30) -> list[dict]:
        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff_str = (cutoff - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self._conn.execute(
            "SELECT * FROM candidates WHERE primary_ticker = ? AND created_at >= ? ORDER BY created_at DESC",
            (ticker, cutoff_str),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Deliveries ──

    def save_delivery(self, run_id: str, target: str, message_kind: str,
                      requires_action: bool, *, card_template: str | None = None) -> dict:
        delivery_id = _uuid()
        idem_key = hashlib.sha256(f"{run_id}:{target}:{message_kind}".encode()).hexdigest()
        # Skip if already exists
        existing = self._conn.execute(
            "SELECT delivery_id, status FROM deliveries WHERE idempotency_key = ?", (idem_key,)
        ).fetchone()
        if existing:
            return dict(existing)
        self._conn.execute(
            "INSERT INTO deliveries (delivery_id, run_id, target, message_kind, card_template, "
            "requires_action, status, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (delivery_id, run_id, target, message_kind, card_template, int(requires_action), idem_key),
        )
        self._conn.commit()
        return {"delivery_id": delivery_id, "status": "pending"}

    def mark_delivered(self, delivery_id: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET status = 'sent', sent_at = ? WHERE delivery_id = ?",
            (_now(), delivery_id),
        )
        self._conn.commit()

    def mark_delivery_failed(self, delivery_id: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET status = 'failed' WHERE delivery_id = ?", (delivery_id,)
        )
        self._conn.commit()

    def update_action_status(self, delivery_id: str, action_status: str) -> None:
        self._conn.execute(
            "UPDATE deliveries SET action_status = ?, action_at = ? WHERE delivery_id = ?",
            (action_status, _now(), delivery_id),
        )
        self._conn.commit()

    def get_pending_deliveries(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM deliveries WHERE status = 'pending' ORDER BY rowid"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Feedbacks ──

    def save_feedback(self, *, run_id: str, source_hypothesis_id: str | None = None,
                      verdict: str | None = None, weight_adjustments: list | None = None,
                      rule_proposals: list | None = None, lessons: list | None = None) -> dict:
        feedback_id = _uuid()
        self._conn.execute(
            "INSERT INTO feedbacks (feedback_id, run_id, source_hypothesis_id, verdict, "
            "weight_adjustments, rule_proposals, lessons, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (feedback_id, run_id, source_hypothesis_id, verdict,
             json.dumps(weight_adjustments or []), json.dumps(rule_proposals or []),
             json.dumps(lessons or []), _now()),
        )
        self._conn.commit()
        return {"feedback_id": feedback_id}

    def get_feedbacks_for_run(self, run_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM feedbacks WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run all tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_run_store.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/invest_harness
git add lib/run_store.py tests/test_run_store.py
git commit -m "feat: add RunStore with idempotency, candidates, deliveries, feedbacks"
```

---

### Task 3: Akshare Adapter

**Files:**
- Create: `adapters/adapter_akshare.py`
- Test: `tests/test_adapter_akshare.py`
- Modify: `adapters/market_data.py` (register in factory)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adapter_akshare.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from adapters.adapter_akshare import AkshareAdapter
from adapters.market_data import Quote, OHLCBar


@pytest.fixture
def mock_ak():
    with patch("adapters.adapter_akshare.ak") as mock:
        yield mock


@pytest.fixture
def adapter(mock_ak):
    return AkshareAdapter()


def test_get_quote(adapter, mock_ak):
    mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({
        "代码": ["000001"],
        "名称": ["平安银行"],
        "最新价": [10.99],
        "涨跌幅": [-0.27],
        "成交量": [330000],
    })
    quote = adapter.get_quote("000001.SZ")
    assert isinstance(quote, Quote)
    assert quote.ticker == "000001.SZ"
    assert quote.price == 10.99
    assert quote.change_pct == -0.27


def test_get_daily_bars(adapter, mock_ak):
    mock_ak.stock_zh_a_hist.return_value = pd.DataFrame({
        "日期": ["2026-03-30"],
        "开盘": [10.98],
        "收盘": [10.99],
        "最高": [11.02],
        "最低": [10.95],
        "成交量": [330000],
    })
    bars = adapter.get_daily_bars("000001.SZ", "20260330", "20260330")
    assert len(bars) == 1
    assert isinstance(bars[0], OHLCBar)
    assert bars[0].close == 10.99
    assert bars[0].date == "2026-03-30"


def test_health_check(adapter, mock_ak):
    mock_ak.stock_zh_a_hist.return_value = pd.DataFrame({"日期": ["2026-03-30"], "开盘": [1], "收盘": [1], "最高": [1], "最低": [1], "成交量": [1]})
    assert adapter.health_check() is True


def test_health_check_failure(adapter, mock_ak):
    mock_ak.stock_zh_a_hist.side_effect = Exception("network error")
    assert adapter.health_check() is False


def test_ticker_normalization(adapter, mock_ak):
    """000001.SZ should query akshare with just '000001'."""
    mock_ak.stock_zh_a_hist.return_value = pd.DataFrame({
        "日期": [], "开盘": [], "收盘": [], "最高": [], "最低": [], "成交量": [],
    })
    adapter.get_daily_bars("000001.SZ", "20260330", "20260330")
    call_args = mock_ak.stock_zh_a_hist.call_args
    assert call_args[1]["symbol"] == "000001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_adapter_akshare.py::test_get_quote -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement AkshareAdapter**

```python
# adapters/adapter_akshare.py
"""Akshare adapter for A-stock market data (fallback for tushare)."""

import akshare as ak
from adapters.market_data import MarketDataAdapter, Quote, OHLCBar
from datetime import datetime


def _strip_suffix(ticker: str) -> str:
    """Remove .SZ/.SH suffix for akshare API."""
    return ticker.split(".")[0]


class AkshareAdapter(MarketDataAdapter):
    def get_quote(self, ticker: str) -> Quote:
        code = _strip_suffix(ticker)
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            raise ValueError(f"Ticker {ticker} not found in akshare spot data")
        r = row.iloc[0]
        return Quote(
            ticker=ticker,
            price=float(r["最新价"]),
            change_pct=float(r["涨跌幅"]),
            volume=int(r.get("成交量", 0)),
            timestamp=datetime.now(),
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        codes = {_strip_suffix(t): t for t in tickers}
        df = ak.stock_zh_a_spot_em()
        results = []
        for _, r in df[df["代码"].isin(codes.keys())].iterrows():
            full_ticker = codes[r["代码"]]
            results.append(Quote(
                ticker=full_ticker,
                price=float(r["最新价"]),
                change_pct=float(r["涨跌幅"]),
                volume=int(r.get("成交量", 0)),
                timestamp=datetime.now(),
            ))
        return results

    def get_daily_bars(self, ticker: str, start_date: str, end_date: str) -> list[OHLCBar]:
        code = _strip_suffix(ticker)
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start_date, end_date=end_date, adjust="qfq",
        )
        bars = []
        for _, r in df.iterrows():
            bars.append(OHLCBar(
                ticker=ticker,
                open=float(r["开盘"]),
                high=float(r["最高"]),
                low=float(r["最低"]),
                close=float(r["收盘"]),
                volume=int(r["成交量"]),
                date=str(r["日期"]),
            ))
        return bars

    def health_check(self) -> bool:
        try:
            df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                                    start_date="20260101", end_date="20260101", adjust="qfq")
            return df is not None
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_adapter_akshare.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Register in adapter factory**

Read `adapters/market_data.py`, then add AkshareAdapter to the `get_adapter()` factory function. Add `"akshare"` as a valid adapter name that returns `AkshareAdapter()`.

- [ ] **Step 6: Commit**

```bash
cd ~/invest_harness
git add adapters/adapter_akshare.py tests/test_adapter_akshare.py adapters/market_data.py
git commit -m "feat: add AkshareAdapter for A-stock data (tushare fallback)"
```

---

### Task 4: Yfinance Adapter

**Files:**
- Create: `adapters/adapter_yfinance.py`
- Test: `tests/test_adapter_yfinance.py`
- Modify: `adapters/market_data.py` (register in factory)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adapter_yfinance.py
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
from adapters.adapter_yfinance import YfinanceAdapter
from adapters.market_data import Quote, OHLCBar


@pytest.fixture
def mock_yf():
    with patch("adapters.adapter_yfinance.yf") as mock:
        yield mock


@pytest.fixture
def adapter(mock_yf):
    return YfinanceAdapter()


def test_get_quote_us(adapter, mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 356.77, "regularMarketChangePercent": -2.51,
                        "regularMarketVolume": 37763600}
    mock_yf.Ticker.return_value = mock_ticker
    quote = adapter.get_quote("MSFT")
    assert isinstance(quote, Quote)
    assert quote.ticker == "MSFT"
    assert quote.price == 356.77


def test_get_quote_hk(adapter, mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 481.60, "regularMarketChangePercent": -2.39,
                        "regularMarketVolume": 28413768}
    mock_yf.Ticker.return_value = mock_ticker
    quote = adapter.get_quote("0700.HK")
    assert quote.ticker == "0700.HK"


def test_get_daily_bars(adapter, mock_yf):
    mock_ticker = MagicMock()
    hist_df = pd.DataFrame({
        "Open": [383.0], "High": [390.0], "Low": [380.0],
        "Close": [356.77], "Volume": [37763600],
    }, index=pd.to_datetime(["2026-03-27"]))
    mock_ticker.history.return_value = hist_df
    mock_yf.Ticker.return_value = mock_ticker
    bars = adapter.get_daily_bars("MSFT", "20260327", "20260327")
    assert len(bars) == 1
    assert bars[0].close == 356.77
    assert bars[0].date == "2026-03-27"


def test_health_check(adapter, mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-03-27"]))
    mock_yf.Ticker.return_value = mock_ticker
    assert adapter.health_check() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_adapter_yfinance.py::test_get_quote_us -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement YfinanceAdapter**

```python
# adapters/adapter_yfinance.py
"""Yfinance adapter for HK and US stock market data."""

import yfinance as yf
from adapters.market_data import MarketDataAdapter, Quote, OHLCBar
from datetime import datetime


class YfinanceAdapter(MarketDataAdapter):
    def get_quote(self, ticker: str) -> Quote:
        t = yf.Ticker(ticker)
        info = t.info
        return Quote(
            ticker=ticker,
            price=float(info.get("regularMarketPrice", 0)),
            change_pct=float(info.get("regularMarketChangePercent", 0)),
            volume=int(info.get("regularMarketVolume", 0)),
            timestamp=datetime.now(),
        )

    def get_quotes(self, tickers: list[str]) -> list[Quote]:
        return [self.get_quote(t) for t in tickers]

    def get_daily_bars(self, ticker: str, start_date: str, end_date: str) -> list[OHLCBar]:
        t = yf.Ticker(ticker)
        # yfinance expects YYYY-MM-DD format
        start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        df = t.history(start=start, end=end)
        bars = []
        for date_idx, r in df.iterrows():
            bars.append(OHLCBar(
                ticker=ticker,
                open=float(r["Open"]),
                high=float(r["High"]),
                low=float(r["Low"]),
                close=float(r["Close"]),
                volume=int(r["Volume"]),
                date=date_idx.strftime("%Y-%m-%d"),
            ))
        return bars

    def health_check(self) -> bool:
        try:
            t = yf.Ticker("AAPL")
            df = t.history(period="1d")
            return len(df) > 0
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_adapter_yfinance.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Register in adapter factory**

Add `"yfinance"` to `get_adapter()` in `adapters/market_data.py`, returning `YfinanceAdapter()`.

- [ ] **Step 6: Commit**

```bash
cd ~/invest_harness
git add adapters/adapter_yfinance.py tests/test_adapter_yfinance.py adapters/market_data.py
git commit -m "feat: add YfinanceAdapter for HK/US stock data"
```

---

### Task 5: Scanner Core

**Files:**
- Create: `lib/scanner.py`
- Create: `prompts/scan.md`
- Create: `schemas/scan_candidate.schema.json`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Create scan prompt template**

```markdown
# prompts/scan.md

# Role
You are a rigorous investment analyst. Based on the provided knowledge base facts,
historical performance, and active rules, evaluate whether any watchlist tickers
present actionable investment opportunities.

# Grading Criteria
- high: Multiple independent sources cross-verify, complete logical chain, historical hit rate > 60%
- medium: Reasonable basis but incomplete information, or historical hit rate 50-60%
- low: Single source only or weak logic, record but do not act

# Constraints
- Only base analysis on provided facts — do not fabricate information
- Each opportunity MUST reference at least 1 fact_id as evidence
- If a ticker's recent 30-day miss_rate > 70%, automatically downgrade confidence by one level
- Output MUST strictly follow the JSON schema below

# Context
{context_bundle}

# Active Rules
{rules}

# Output Format
Return a JSON array of candidates. Each candidate:
```json
{
  "primary_ticker": "string",
  "related_tickers": ["string"],
  "direction": "long|short|neutral",
  "confidence": "high|medium|low",
  "thesis": "one sentence thesis",
  "evidence": [{"fact_id": "string", "relevance_score": 0.0, "snippet": "string"}],
  "suggested_entry": 0.0,
  "suggested_exit": 0.0,
  "stop_loss": 0.0,
  "time_horizon": "1d|3d|1w|1m",
  "risk_factors": ["string"]
}
```

If no opportunities found, return an empty array: []
```

- [ ] **Step 2: Create scan_candidate schema**

```json
// schemas/scan_candidate.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["primary_ticker", "direction", "confidence", "thesis", "evidence"],
  "properties": {
    "primary_ticker": {"type": "string"},
    "related_tickers": {"type": "array", "items": {"type": "string"}, "default": []},
    "direction": {"enum": ["long", "short", "neutral"]},
    "confidence": {"enum": ["high", "medium", "low"]},
    "thesis": {"type": "string", "minLength": 5},
    "evidence": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["fact_id", "relevance_score", "snippet"],
        "properties": {
          "fact_id": {"type": "string"},
          "relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
          "snippet": {"type": "string"}
        }
      }
    },
    "suggested_entry": {"type": ["number", "null"]},
    "suggested_exit": {"type": ["number", "null"]},
    "stop_loss": {"type": ["number", "null"]},
    "time_horizon": {"enum": ["1d", "3d", "1w", "1m", null]},
    "risk_factors": {"type": "array", "items": {"type": "string"}, "default": []}
  }
}
```

- [ ] **Step 3: Write failing tests**

```python
# tests/test_scanner.py
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from lib.scanner import Scanner, ScanConfig


@pytest.fixture
def scan_config():
    return ScanConfig(
        lookback_days=3,
        vector_top_k=5,
        max_facts_per_ticker=10,
        max_snippet_chars=200,
        max_insights_per_ticker=5,
        min_relevance_score=0.3,
        auto_lock_min_evidence=2,
        auto_lock_min_sources=2,
        auto_lock_max_miss_rate=0.7,
    )


@pytest.fixture
def mock_knowledge():
    kp = MagicMock()
    kp.get_recent_facts.return_value = [
        {"fact_id": "f1", "company": "贵州茅台", "tickers": ["600519.SH"],
         "topic": "earnings", "status": "active", "text": "Q1 revenue up 15%",
         "source_type": "company_research", "updated_at": "2026-03-29"},
        {"fact_id": "f2", "company": "贵州茅台", "tickers": ["600519.SH"],
         "topic": "channel", "status": "active", "text": "Channel inventory low",
         "source_type": "sell_side", "updated_at": "2026-03-28"},
    ]
    return kp


@pytest.fixture
def mock_chroma():
    cm = MagicMock()
    cm.search_facts.return_value = [
        {"id": "f3", "document": "Industry outlook positive", "metadata": {"source_type": "industry_data"}, "distance": 0.2},
    ]
    cm.search_insights.return_value = []
    return cm


@pytest.fixture
def mock_run_store():
    rs = MagicMock()
    rs.get_candidates_by_ticker.return_value = []
    return rs


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.return_value = json.dumps([{
        "primary_ticker": "600519.SH",
        "related_tickers": [],
        "direction": "long",
        "confidence": "high",
        "thesis": "Strong Q1 with low channel inventory",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "Q1 revenue up 15%"}],
        "suggested_entry": 1680.0,
        "suggested_exit": 1780.0,
        "stop_loss": 1640.0,
        "time_horizon": "1w",
        "risk_factors": ["Macro headwinds"],
    }])
    return llm


def test_build_context_bundle(scan_config, mock_knowledge, mock_chroma, mock_run_store):
    scanner = Scanner(
        knowledge=mock_knowledge, chroma=mock_chroma,
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    bundle = scanner._build_context_bundle(
        ticker="600519.SH", date="20260330",
        recent_facts=[{"fact_id": "f1", "tickers": ["600519.SH"], "text": "Q1 up"}],
    )
    assert "recent_facts" in bundle
    assert "vector_results" in bundle
    assert "historical_performance" in bundle


def test_validate_candidate_schema(scan_config):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=MagicMock(), llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    valid = {
        "primary_ticker": "600519.SH", "direction": "long",
        "confidence": "high", "thesis": "Strong earnings",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
    }
    assert scanner._validate_candidate(valid, watchlist_tickers=["600519.SH"]) is True


def test_validate_candidate_rejects_non_watchlist(scan_config):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=MagicMock(), llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    invalid = {
        "primary_ticker": "999999.SZ", "direction": "long",
        "confidence": "high", "thesis": "Not in watchlist",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "..."}],
    }
    assert scanner._validate_candidate(invalid, watchlist_tickers=["600519.SH"]) is False


def test_auto_lock_gate_passes(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidate = {
        "primary_ticker": "600519.SH", "confidence": "high",
        "evidence": [
            {"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"},
            {"fact_id": "f2", "relevance_score": 0.8, "snippet": "b"},
        ],
    }
    # No historical misses
    assert scanner._check_auto_lock_gate(candidate) is True


def test_auto_lock_gate_insufficient_evidence(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidate = {
        "primary_ticker": "600519.SH", "confidence": "high",
        "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"}],
    }
    assert scanner._check_auto_lock_gate(candidate) is False


def test_grade_candidates(scan_config, mock_run_store):
    scanner = Scanner(
        knowledge=MagicMock(), chroma=MagicMock(),
        run_store=mock_run_store, llm_call=MagicMock(),
        rules=[], config=scan_config,
    )
    candidates = [
        {"primary_ticker": "600519.SH", "confidence": "high",
         "evidence": [{"fact_id": "f1", "relevance_score": 0.9, "snippet": "a"},
                      {"fact_id": "f2", "relevance_score": 0.8, "snippet": "b"}],
         "direction": "long", "thesis": "test"},
        {"primary_ticker": "300750.SZ", "confidence": "medium",
         "evidence": [{"fact_id": "f3", "relevance_score": 0.7, "snippet": "c"}],
         "direction": "long", "thesis": "test2"},
        {"primary_ticker": "000001.SZ", "confidence": "low",
         "evidence": [{"fact_id": "f4", "relevance_score": 0.5, "snippet": "d"}],
         "direction": "long", "thesis": "test3"},
    ]
    graded = scanner._assign_actions(candidates)
    assert graded[0]["auto_action"] == "auto_lock"
    assert graded[1]["auto_action"] == "await_approval"
    assert graded[2]["auto_action"] == "log_only"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_scanner.py::test_build_context_bundle -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 5: Implement Scanner**

```python
# lib/scanner.py
"""Scanner — knowledge base opportunity screening with LLM analysis."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "scan_candidate.schema.json"


@dataclass
class ScanConfig:
    lookback_days: int = 3
    vector_top_k: int = 5
    max_facts_per_ticker: int = 10
    max_snippet_chars: int = 200
    max_insights_per_ticker: int = 5
    min_relevance_score: float = 0.3
    auto_lock_min_evidence: int = 2
    auto_lock_min_sources: int = 2
    auto_lock_max_miss_rate: float = 0.7
    blacklist: list = field(default_factory=list)


class Scanner:
    def __init__(self, *, knowledge, chroma, run_store, llm_call, rules, config: ScanConfig):
        self._knowledge = knowledge
        self._chroma = chroma
        self._run_store = run_store
        self._llm_call = llm_call
        self._rules = rules
        self._config = config
        self._schema = None
        if SCHEMA_PATH.exists():
            self._schema = json.loads(SCHEMA_PATH.read_text())

    def scan(self, *, market: str, date: str, watchlist_tickers: list[str]) -> dict:
        """Run full scan pipeline. Returns dict with candidates and grading."""
        # Step 1: Incremental KB retrieval
        recent_facts = self._get_recent_facts(market, date, watchlist_tickers)

        # Step 2: Per-ticker context bundles
        ticker_bundles = {}
        for ticker in watchlist_tickers:
            ticker_facts = [f for f in recent_facts
                           if ticker in f.get("tickers", [])]
            bundle = self._build_context_bundle(ticker, date, ticker_facts)
            if bundle["recent_facts"] or bundle["vector_results"]:
                ticker_bundles[ticker] = bundle

        if not ticker_bundles:
            return {"candidates": [], "summary": {"high": 0, "medium": 0, "low": 0}}

        # Step 3: LLM analysis
        prompt = self._build_prompt(ticker_bundles)
        raw_output = self._llm_call(prompt)
        candidates = self._parse_and_validate(raw_output, watchlist_tickers)

        # Step 4: Assign actions
        graded = self._assign_actions(candidates)

        summary = {
            "high": sum(1 for c in graded if c["confidence"] == "high"),
            "medium": sum(1 for c in graded if c["confidence"] == "medium"),
            "low": sum(1 for c in graded if c["confidence"] == "low"),
        }

        return {"candidates": graded, "summary": summary}

    def _get_recent_facts(self, market, date, tickers):
        try:
            return self._knowledge.get_recent_facts(
                days=self._config.lookback_days,
                tickers=tickers,
                status="active",
            )
        except Exception:
            logger.warning("Failed to get recent facts, returning empty")
            return []

    def _build_context_bundle(self, ticker, date, recent_facts):
        # Vector retrieval
        vector_results = []
        try:
            raw_results = self._chroma.search_facts(
                query=f"{ticker} investment opportunity risk",
                n_results=self._config.vector_top_k,
            )
            vector_results = [
                r for r in raw_results
                if r.get("distance", 1.0) <= (1 - self._config.min_relevance_score)
            ]
        except Exception:
            logger.warning(f"Vector retrieval failed for {ticker}, degrading")

        # Merge dedup by fact_id
        seen_ids = {f["fact_id"] for f in recent_facts}
        for vr in vector_results:
            if vr["id"] not in seen_ids:
                recent_facts.append({
                    "fact_id": vr["id"],
                    "text": vr.get("document", ""),
                    "source_type": vr.get("metadata", {}).get("source_type", "unknown"),
                })
                seen_ids.add(vr["id"])

        # Budget control
        recent_facts = recent_facts[:self._config.max_facts_per_ticker]
        for f in recent_facts:
            if "text" in f:
                f["text"] = f["text"][:self._config.max_snippet_chars]

        # Historical performance
        historical = {"available": False, "hit_rate": None, "miss_rate": None}
        try:
            past = self._run_store.get_candidates_by_ticker(ticker, days=30)
            if past:
                # Simple hit/miss from feedbacks would be ideal,
                # but for MVP count candidates that became hypotheses
                historical["available"] = True
                historical["total"] = len(past)
        except Exception:
            pass

        # Insights
        insights = []
        try:
            raw_insights = self._chroma.search_insights(
                query=ticker, n_results=self._config.max_insights_per_ticker,
            )
            insights = raw_insights
        except Exception:
            pass

        return {
            "recent_facts": recent_facts,
            "vector_results": vector_results,
            "historical_performance": historical,
            "insights": insights,
        }

    def _build_prompt(self, ticker_bundles: dict) -> str:
        prompt_template = ""
        prompt_path = Path(__file__).parent.parent / "prompts" / "scan.md"
        if prompt_path.exists():
            prompt_template = prompt_path.read_text()

        context_str = json.dumps(ticker_bundles, ensure_ascii=False, default=str)
        rules_str = json.dumps(
            [{"rule_id": r.rule_id, "title": r.title, "body": r.body}
             for r in self._rules] if self._rules else [],
            ensure_ascii=False,
        )

        return prompt_template.replace("{context_bundle}", context_str).replace("{rules}", rules_str)

    def _parse_and_validate(self, raw_output: str, watchlist_tickers: list[str]) -> list[dict]:
        # Extract JSON from LLM output
        try:
            # Try to find JSON array in output
            start = raw_output.find("[")
            end = raw_output.rfind("]") + 1
            if start >= 0 and end > start:
                candidates = json.loads(raw_output[start:end])
            else:
                candidates = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.error("LLM output is not valid JSON")
            return []

        if not isinstance(candidates, list):
            return []

        valid = []
        for c in candidates:
            if self._validate_candidate(c, watchlist_tickers):
                valid.append(c)
            else:
                logger.warning(f"Candidate failed validation: {c.get('primary_ticker', '?')}")

        return valid

    def _validate_candidate(self, candidate: dict, watchlist_tickers: list[str]) -> bool:
        # Layer 1: Schema validation
        if self._schema:
            try:
                jsonschema.validate(instance=candidate, schema=self._schema)
            except jsonschema.ValidationError as e:
                logger.warning(f"Schema validation failed: {e.message}")
                return False

        # Layer 2: Business validation
        if candidate.get("primary_ticker") not in watchlist_tickers:
            logger.warning(f"primary_ticker {candidate.get('primary_ticker')} not in watchlist")
            return False

        evidence = candidate.get("evidence", [])
        if not evidence:
            return False

        return True

    def _check_auto_lock_gate(self, candidate: dict) -> bool:
        """Check if high-confidence candidate passes risk gates for auto-lock."""
        evidence = candidate.get("evidence", [])

        # Gate 1: Minimum evidence count
        if len(evidence) < self._config.auto_lock_min_evidence:
            return False

        # Gate 2: Blacklist
        if candidate.get("primary_ticker") in self._config.blacklist:
            return False

        # Gate 3: Historical miss rate
        try:
            past = self._run_store.get_candidates_by_ticker(
                candidate["primary_ticker"], days=30
            )
            if past:
                # Check feedbacks for this ticker's verdicts
                # For MVP, if we have enough history, check
                pass  # Will be refined when feedback data accumulates
        except Exception:
            pass

        return True

    def _assign_actions(self, candidates: list[dict]) -> list[dict]:
        """Assign auto_action based on confidence + risk gates."""
        for c in candidates:
            conf = c.get("confidence", "low")
            if conf == "high" and self._check_auto_lock_gate(c):
                c["auto_action"] = "auto_lock"
            elif conf == "high":
                # Downgrade: failed risk gate
                c["auto_action"] = "await_approval"
            elif conf == "medium":
                c["auto_action"] = "await_approval"
            else:
                c["auto_action"] = "log_only"
        return candidates
```

- [ ] **Step 6: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_scanner.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
cd ~/invest_harness
git add lib/scanner.py prompts/scan.md schemas/scan_candidate.schema.json tests/test_scanner.py
git commit -m "feat: add Scanner with KB retrieval, LLM analysis, candidate grading"
```

---

### Task 6: Verify Auto-Fetch Actuals

**Files:**
- Modify: `lib/verification.py`
- Modify: `adapters/market_data.py`
- Test: `tests/test_verify_auto_actuals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_verify_auto_actuals.py
import pytest
from unittest.mock import MagicMock, patch
from adapters.market_data import OHLCBar, get_adapter


def test_fetch_actuals_a_stock_primary():
    """tushare primary, akshare fallback for a_stock."""
    tushare = MagicMock()
    tushare.get_daily_bars.return_value = [
        OHLCBar("000001.SZ", 10.98, 11.02, 10.95, 10.99, 330000, "2026-03-30")
    ]

    from lib.verification import fetch_actuals
    result = fetch_actuals(
        ticker="000001.SZ", market="a_stock", date="20260330",
        adapters={"primary": tushare, "fallback": None},
    )
    assert result is not None
    assert result["close"] == 10.99
    assert result["source"] == "primary"


def test_fetch_actuals_fallback():
    """When primary fails, fallback adapter is used."""
    tushare = MagicMock()
    tushare.get_daily_bars.side_effect = Exception("502 Bad Gateway")
    akshare = MagicMock()
    akshare.get_daily_bars.return_value = [
        OHLCBar("000001.SZ", 10.98, 11.02, 10.95, 10.99, 330000, "2026-03-30")
    ]

    from lib.verification import fetch_actuals
    result = fetch_actuals(
        ticker="000001.SZ", market="a_stock", date="20260330",
        adapters={"primary": tushare, "fallback": akshare},
    )
    assert result is not None
    assert result["close"] == 10.99
    assert result["source"] == "fallback"


def test_fetch_actuals_all_fail():
    """When all adapters fail, returns None."""
    tushare = MagicMock()
    tushare.get_daily_bars.side_effect = Exception("fail")

    from lib.verification import fetch_actuals
    result = fetch_actuals(
        ticker="000001.SZ", market="a_stock", date="20260330",
        adapters={"primary": tushare, "fallback": None},
    )
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_verify_auto_actuals.py::test_fetch_actuals_a_stock_primary -v`
Expected: FAIL — cannot import fetch_actuals

- [ ] **Step 3: Add fetch_actuals to verification.py**

Read `lib/verification.py` first. Add the following function:

```python
# Add to lib/verification.py

def fetch_actuals(*, ticker: str, market: str, date: str,
                  adapters: dict) -> dict | None:
    """Fetch post-market actuals for a ticker using adapter with fallback.

    Args:
        ticker: Ticker symbol (e.g. "000001.SZ")
        market: Market name (a_stock, hk_stock, us_stock, polymarket)
        date: Date string YYYYMMDD
        adapters: {"primary": adapter, "fallback": adapter|None}

    Returns:
        dict with open, high, low, close, volume, date, source or None if all fail.
    """
    for label in ("primary", "fallback"):
        adapter = adapters.get(label)
        if adapter is None:
            continue
        try:
            bars = adapter.get_daily_bars(ticker, date, date)
            if bars:
                bar = bars[0]
                return {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "date": bar.date,
                    "source": label,
                }
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"{label} adapter failed for {ticker}: {e}"
            )
            continue
    return None
```

- [ ] **Step 4: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_verify_auto_actuals.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/invest_harness
git add lib/verification.py tests/test_verify_auto_actuals.py
git commit -m "feat: add fetch_actuals with adapter fallback to verification"
```

---

### Task 7: Review Extensions (Weight Adjustment + Rule Proposals + Lessons)

**Files:**
- Modify: `lib/review.py`
- Modify: `lib/knowledge.py`
- Create: `lib/feedback_engine.py`
- Create: `prompts/rule_proposal.md`
- Create: `prompts/lesson_extract.md`
- Test: `tests/test_feedback_engine.py`

- [ ] **Step 1: Add update_source_weight to KnowledgePipeline**

Read `lib/knowledge.py` first. Add method:

```python
# Add to KnowledgePipeline class in lib/knowledge.py

def update_source_weight(self, fact_id: str, new_weight: float) -> bool:
    """Update source_weight for a normalized fact.

    Finds the fact in normalized/ JSONL files and updates its source_weight.
    Also updates ChromaDB metadata.

    Args:
        fact_id: The fact identifier
        new_weight: New weight value, clamped to [0.1, 1.0]

    Returns:
        True if fact found and updated, False otherwise.
    """
    new_weight = max(0.1, min(1.0, new_weight))
    # Scan normalized JSONL files for this fact_id
    normalized_dir = self._knowledge_dir / "normalized"
    for jsonl_file in normalized_dir.rglob("*.jsonl"):
        lines = jsonl_file.read_text().strip().split("\n")
        updated = False
        new_lines = []
        for line in lines:
            if not line.strip():
                continue
            fact = json.loads(line)
            if fact.get("fact_id") == fact_id:
                fact["source_weight"] = new_weight
                updated = True
            new_lines.append(json.dumps(fact, ensure_ascii=False))
        if updated:
            jsonl_file.write_text("\n".join(new_lines) + "\n")
            # Update ChromaDB
            try:
                self._chroma.update_fact_metadata(fact_id, {"source_weight": new_weight})
            except Exception:
                pass
            return True
    return False
```

- [ ] **Step 2: Create prompt templates**

```markdown
# prompts/rule_proposal.md

# Role
You are an investment rules auditor. Based on the verification results showing
misses and execution gaps, analyze root causes and propose rule modifications.

# Input
- Misses and execution gaps from today's verification
- Current active rules

# Output Format
Return a JSON array of proposals:
```json
[{
  "action": "add|modify|deprecate",
  "rule_id": "existing_rule_id or null for new rules",
  "title": "Rule title",
  "diff": "What specifically changes",
  "rationale": "Why this change is needed based on evidence"
}]
```

# Misses
{misses}

# Active Rules
{rules}
```

```markdown
# prompts/lesson_extract.md

# Role
You are an investment research meta-analyst. Extract reusable lessons from
today's review that can improve future screening accuracy.

# Input
- Today's complete review (hits, misses, categories)
- 30-day review trend summary

# Constraints
- Each lesson must be actionable and specific
- Avoid generic platitudes ("do more research")
- Reference specific tickers or patterns as examples
- Check existing insights to avoid duplicates

# Output Format
```json
[{
  "insight_text": "Specific, actionable lesson",
  "category": "timing|sector|sentiment|methodology|risk",
  "tickers": ["relevant tickers"]
}]
```

# Today's Review
{review}

# 30-Day Trend
{trend}

# Existing Insights (avoid duplicates)
{existing_insights}
```

- [ ] **Step 3: Write failing tests for FeedbackEngine**

```python
# tests/test_feedback_engine.py
import json
import pytest
from unittest.mock import MagicMock
from lib.feedback_engine import FeedbackEngine


@pytest.fixture
def mock_knowledge():
    kp = MagicMock()
    kp.update_source_weight.return_value = True
    kp.add_curated_insight.return_value = {"insight_id": "i1"}
    return kp


@pytest.fixture
def mock_chroma():
    cm = MagicMock()
    cm.search_insights.return_value = []
    return cm


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def engine(mock_knowledge, mock_chroma, mock_llm):
    return FeedbackEngine(
        knowledge=mock_knowledge,
        chroma=mock_chroma,
        llm_call=mock_llm,
        rules=[],
    )


def test_adjust_weights_hit(engine, mock_knowledge):
    verify_result = {
        "verdict": "hit",
        "hypothesis_ref": "H1",
        "evidence_fact_ids": ["f1", "f2"],
    }
    adjustments = engine.adjust_weights([verify_result])
    assert len(adjustments) == 2
    # hit → weight *= 1.05
    for adj in adjustments:
        assert adj["new_weight"] > adj["old_weight"]
    assert mock_knowledge.update_source_weight.call_count == 2


def test_adjust_weights_miss(engine, mock_knowledge):
    verify_result = {
        "verdict": "miss",
        "hypothesis_ref": "H2",
        "evidence_fact_ids": ["f3"],
    }
    adjustments = engine.adjust_weights([verify_result])
    assert len(adjustments) == 1
    assert adjustments[0]["new_weight"] < adjustments[0]["old_weight"]


def test_adjust_weights_partial_hit_no_change(engine, mock_knowledge):
    verify_result = {
        "verdict": "partial_hit",
        "hypothesis_ref": "H3",
        "evidence_fact_ids": ["f4"],
    }
    adjustments = engine.adjust_weights([verify_result])
    assert len(adjustments) == 0
    mock_knowledge.update_source_weight.assert_not_called()


def test_generate_rule_proposals(engine, mock_llm):
    mock_llm.return_value = json.dumps([{
        "action": "add",
        "rule_id": None,
        "title": "Sentiment divergence downgrade",
        "diff": "New rule: downgrade confidence when sentiment diverges",
        "rationale": "2 recent misses caused by sentiment shifts",
    }])
    misses = [{"verdict": "miss", "hypothesis_ref": "H2"}]
    proposals = engine.generate_rule_proposals(misses)
    assert len(proposals) == 1
    assert proposals[0]["status"] == "pending_approval"
    assert proposals[0]["proposal_id"]


def test_extract_lessons(engine, mock_llm):
    mock_llm.return_value = json.dumps([{
        "insight_text": "Single catalyst opportunities need sentiment cross-check",
        "category": "sentiment",
        "tickers": ["300750.SZ"],
    }])
    lessons = engine.extract_lessons(
        review_summary={"hits": 3, "misses": 1},
        trend_summary={"7d_hit_rate": 0.65},
    )
    assert len(lessons) == 1
    assert lessons[0]["category"] == "sentiment"


def test_apply_rule_proposal_approve(engine):
    proposal = {
        "proposal_id": "P1",
        "action": "add",
        "rule_id": None,
        "title": "New rule",
        "diff": "Add rule body here",
        "rationale": "Needed",
        "status": "pending_approval",
    }
    result = engine.apply_rule_proposal(proposal, approved=True)
    assert result["status"] == "approved"


def test_apply_rule_proposal_reject(engine):
    proposal = {
        "proposal_id": "P1",
        "action": "add",
        "status": "pending_approval",
    }
    result = engine.apply_rule_proposal(proposal, approved=False, reason="Not needed")
    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "Not needed"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_feedback_engine.py::test_adjust_weights_hit -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 5: Implement FeedbackEngine**

```python
# lib/feedback_engine.py
"""Feedback Engine — closed-loop weight adjustment, rule proposals, lesson extraction."""

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Default source weights (used when fact doesn't have explicit weight)
DEFAULT_SOURCE_WEIGHT = 0.7
HIT_MULTIPLIER = 1.05
MISS_MULTIPLIER = 0.90
WEIGHT_CAP = 1.0
WEIGHT_FLOOR = 0.1


class FeedbackEngine:
    def __init__(self, *, knowledge, chroma, llm_call, rules):
        self._knowledge = knowledge
        self._chroma = chroma
        self._llm_call = llm_call
        self._rules = rules

    def adjust_weights(self, verify_results: list[dict]) -> list[dict]:
        """Adjust knowledge source weights based on verification verdicts.

        hit → weight *= 1.05 (cap 1.0)
        miss → weight *= 0.90 (floor 0.1)
        partial_hit / invalidated → no change
        """
        adjustments = []
        for vr in verify_results:
            verdict = vr.get("verdict")
            if verdict not in ("hit", "miss"):
                continue
            multiplier = HIT_MULTIPLIER if verdict == "hit" else MISS_MULTIPLIER
            for fact_id in vr.get("evidence_fact_ids", []):
                old_weight = DEFAULT_SOURCE_WEIGHT
                new_weight = max(WEIGHT_FLOOR, min(WEIGHT_CAP, old_weight * multiplier))
                success = self._knowledge.update_source_weight(fact_id, new_weight)
                if success:
                    adjustments.append({
                        "fact_id": fact_id,
                        "old_weight": old_weight,
                        "new_weight": new_weight,
                        "reason": verdict,
                        "hypothesis_ref": vr.get("hypothesis_ref"),
                    })
        return adjustments

    def generate_rule_proposals(self, misses: list[dict]) -> list[dict]:
        """Use LLM to propose rule changes based on misses."""
        if not misses:
            return []

        prompt_path = Path(__file__).parent.parent / "prompts" / "rule_proposal.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""
        prompt = prompt.replace("{misses}", json.dumps(misses, ensure_ascii=False, default=str))
        prompt = prompt.replace("{rules}", json.dumps(
            [{"rule_id": r.rule_id, "title": r.title, "body": r.body}
             for r in self._rules] if self._rules else [],
            ensure_ascii=False,
        ))

        try:
            raw = self._llm_call(prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            proposals = json.loads(raw[start:end]) if start >= 0 else []
        except Exception:
            logger.error("Failed to parse rule proposals from LLM")
            return []

        for p in proposals:
            p["proposal_id"] = str(uuid.uuid4())
            p["status"] = "pending_approval"

        return proposals

    def extract_lessons(self, *, review_summary: dict, trend_summary: dict) -> list[dict]:
        """Use LLM to extract reusable lessons from review."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "lesson_extract.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""
        prompt = prompt.replace("{review}", json.dumps(review_summary, ensure_ascii=False, default=str))
        prompt = prompt.replace("{trend}", json.dumps(trend_summary, ensure_ascii=False, default=str))

        existing = []
        try:
            insights_path = Path(self._knowledge._knowledge_dir) / "curated" / "insights.jsonl"
            if insights_path.exists():
                existing = [json.loads(l) for l in insights_path.read_text().strip().split("\n") if l.strip()]
        except Exception:
            pass
        prompt = prompt.replace("{existing_insights}", json.dumps(existing[-20:], ensure_ascii=False, default=str))

        try:
            raw = self._llm_call(prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            lessons = json.loads(raw[start:end]) if start >= 0 else []
        except Exception:
            logger.error("Failed to parse lessons from LLM")
            return []

        # Write to curated/insights.jsonl
        for lesson in lessons:
            try:
                self._knowledge.add_curated_insight(lesson)
            except Exception:
                logger.warning(f"Failed to save insight: {lesson.get('insight_text', '?')[:50]}")

        return lessons

    def apply_rule_proposal(self, proposal: dict, *, approved: bool,
                            reason: str | None = None) -> dict:
        """Apply or reject a rule proposal."""
        if approved:
            proposal["status"] = "approved"
            # Actual rule file modification would be done by RuleEngine
            # This method just updates the proposal status
        else:
            proposal["status"] = "rejected"
            proposal["rejection_reason"] = reason
        return proposal
```

- [ ] **Step 6: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_feedback_engine.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
cd ~/invest_harness
git add lib/feedback_engine.py lib/knowledge.py prompts/rule_proposal.md prompts/lesson_extract.md tests/test_feedback_engine.py
git commit -m "feat: add FeedbackEngine with weight adjustment, rule proposals, lesson extraction"
```

---

### Task 8: Feedback CLI Command

**Files:**
- Create: `schemas/feedback.schema.json`
- Test: `tests/test_feedback_cmd.py`

This task creates the schema. The CLI wiring happens in Task 10.

- [ ] **Step 1: Create feedback schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["feedback_id", "run_id"],
  "properties": {
    "feedback_id": {"type": "string"},
    "run_id": {"type": "string"},
    "source_hypothesis_id": {"type": ["string", "null"]},
    "verdict": {"enum": ["hit", "partial_hit", "miss", "invalidated", null]},
    "weight_adjustments": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["fact_id", "old_weight", "new_weight", "reason"],
        "properties": {
          "fact_id": {"type": "string"},
          "old_weight": {"type": "number"},
          "new_weight": {"type": "number"},
          "reason": {"type": "string"}
        }
      }
    },
    "rule_proposals": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["proposal_id", "action", "status"],
        "properties": {
          "proposal_id": {"type": "string"},
          "action": {"enum": ["add", "modify", "deprecate"]},
          "rule_id": {"type": ["string", "null"]},
          "title": {"type": "string"},
          "diff": {"type": "string"},
          "rationale": {"type": "string"},
          "status": {"enum": ["pending_approval", "approved", "rejected"]}
        }
      }
    },
    "lessons": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["insight_text", "category"],
        "properties": {
          "insight_text": {"type": "string"},
          "category": {"enum": ["timing", "sector", "sentiment", "methodology", "risk"]},
          "tickers": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd ~/invest_harness
git add schemas/feedback.schema.json
git commit -m "feat: add feedback JSON schema"
```

---

### Task 9: Watchlist Command

**Files:**
- Test: `tests/test_watchlist_cmd.py`

This task tests the watchlist logic. CLI wiring in Task 10.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_watchlist_cmd.py
import json
import pytest
from pathlib import Path


def _load_watchlist(path):
    return json.loads(path.read_text())


def _save_watchlist(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


@pytest.fixture
def watchlist_file(tmp_path):
    wl = {
        "a_stock": [{"ticker": "600519.SH", "name": "贵州茅台", "added_at": "2026-03-28", "added_by": "user"}],
        "hk_stock": [],
        "us_stock": [],
        "polymarket": [],
    }
    path = tmp_path / "watchlist.json"
    _save_watchlist(path, wl)
    return path


def test_detect_market_from_ticker():
    from lib.watchlist import detect_market
    assert detect_market("000001.SZ") == "a_stock"
    assert detect_market("600519.SH") == "a_stock"
    assert detect_market("0700.HK") == "hk_stock"
    assert detect_market("MSFT") == "us_stock"
    assert detect_market("AAPL") == "us_stock"


def test_add_ticker(watchlist_file):
    from lib.watchlist import add_ticker
    result = add_ticker(watchlist_file, ticker="300750.SZ", market="a_stock", added_by="user")
    assert result["added"] is True
    wl = _load_watchlist(watchlist_file)
    tickers = [e["ticker"] for e in wl["a_stock"]]
    assert "300750.SZ" in tickers


def test_add_duplicate_noop(watchlist_file):
    from lib.watchlist import add_ticker
    result = add_ticker(watchlist_file, ticker="600519.SH", market="a_stock", added_by="user")
    assert result["added"] is False


def test_remove_ticker(watchlist_file):
    from lib.watchlist import remove_ticker
    result = remove_ticker(watchlist_file, ticker="600519.SH", market="a_stock")
    assert result["removed"] is True
    wl = _load_watchlist(watchlist_file)
    assert len(wl["a_stock"]) == 0


def test_list_tickers(watchlist_file):
    from lib.watchlist import list_tickers
    result = list_tickers(watchlist_file, market="a_stock")
    assert len(result) == 1
    assert result[0]["ticker"] == "600519.SH"


def test_list_all(watchlist_file):
    from lib.watchlist import list_tickers
    result = list_tickers(watchlist_file, market=None)
    assert isinstance(result, dict)
    assert "a_stock" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_watchlist_cmd.py::test_detect_market_from_ticker -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement watchlist module**

```python
# lib/watchlist.py
"""Watchlist management — add, remove, list tickers with market auto-detection."""

import json
from datetime import datetime, timezone
from pathlib import Path


def detect_market(ticker: str) -> str:
    """Auto-detect market from ticker suffix."""
    if ticker.endswith(".SZ") or ticker.endswith(".SH"):
        return "a_stock"
    elif ticker.endswith(".HK"):
        return "hk_stock"
    else:
        return "us_stock"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def add_ticker(watchlist_path: Path, *, ticker: str, market: str,
               added_by: str = "user", name: str | None = None) -> dict:
    wl = _load(watchlist_path)
    if market not in wl:
        wl[market] = []

    existing = [e["ticker"] for e in wl[market]]
    if ticker in existing:
        return {"added": False, "reason": "already_exists"}

    wl[market].append({
        "ticker": ticker,
        "name": name or ticker,
        "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "added_by": added_by,
    })
    _save(watchlist_path, wl)
    return {"added": True, "ticker": ticker, "market": market}


def remove_ticker(watchlist_path: Path, *, ticker: str, market: str) -> dict:
    wl = _load(watchlist_path)
    if market not in wl:
        return {"removed": False, "reason": "market_not_found"}

    before = len(wl[market])
    wl[market] = [e for e in wl[market] if e["ticker"] != ticker]
    if len(wl[market]) == before:
        return {"removed": False, "reason": "ticker_not_found"}

    _save(watchlist_path, wl)
    return {"removed": True, "ticker": ticker, "market": market}


def list_tickers(watchlist_path: Path, *, market: str | None = None) -> list | dict:
    wl = _load(watchlist_path)
    if market:
        return wl.get(market, [])
    return wl
```

- [ ] **Step 4: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_watchlist_cmd.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/invest_harness
git add lib/watchlist.py tests/test_watchlist_cmd.py
git commit -m "feat: add watchlist module with add/remove/list and market auto-detection"
```

---

### Task 10: CLI Wiring (scan, feedback, watchlist commands)

**Files:**
- Modify: `scripts/harness_cli.py`
- Modify: `scripts/harness_inbound.py`

- [ ] **Step 1: Read existing CLI code**

Read: `scripts/harness_cli.py` — understand the COMMAND_HANDLERS dict, argument parsing, HarnessContext.

- [ ] **Step 2: Add scan command handler**

Add to `scripts/harness_cli.py`:

```python
# Add argument parser for scan
def _add_scan_parser(subparsers):
    p = subparsers.add_parser("scan", help="Scan knowledge base for investment opportunities")
    p.add_argument("--market", required=True, choices=["a_stock", "hk_stock", "us_stock", "polymarket"])
    p.add_argument("--date", required=True, help="Date YYYYMMDD")
    p.add_argument("--watchlist", help="Override watchlist file path")
    p.add_argument("--no-notify", action="store_true")


def cmd_scan(args, ctx: HarnessContext) -> dict:
    from lib.run_store import RunStore
    from lib.scanner import Scanner, ScanConfig
    from lib.watchlist import list_tickers
    import hashlib, json

    store = RunStore(ctx.conn)

    # Load watchlist
    wl_path = Path(args.watchlist) if args.watchlist else ctx.paths.config_dir / "local" / "watchlist.json"
    tickers_data = list_tickers(wl_path, market=args.market)
    tickers = [e["ticker"] for e in tickers_data] if isinstance(tickers_data, list) else []

    if not tickers:
        return {"status": "skipped", "reason": "empty_watchlist"}

    watchlist_hash = hashlib.sha256(json.dumps(sorted(tickers)).encode()).hexdigest()[:16]

    # Knowledge fingerprint (max updated_at from normalized facts)
    knowledge_fingerprint = "static"  # Will be refined when knowledge has versioning
    try:
        normalized_dir = ctx.paths.knowledge_dir / "normalized"
        if normalized_dir.exists():
            mtimes = [f.stat().st_mtime for f in normalized_dir.rglob("*.jsonl")]
            if mtimes:
                knowledge_fingerprint = str(max(mtimes))
    except Exception:
        pass

    # Create run (idempotency check)
    run = store.create_run(
        phase="scan", market=args.market, trigger_source="cron",
        watchlist_hash=watchlist_hash, knowledge_fingerprint=knowledge_fingerprint,
        date=args.date,
    )
    if run["status"] == "skipped":
        return run

    store.update_status(run["run_id"], "running")

    try:
        # Build scanner dependencies
        from lib.knowledge import KnowledgePipeline
        from lib.chroma_client import ChromaManager
        from lib.rules import RuleEngine

        chroma = ChromaManager(str(ctx.paths.root / "chroma_storage"))
        knowledge = KnowledgePipeline(
            ctx.paths.knowledge_dir, chroma,
            str(ctx.paths.knowledge_dir / "raw" / "seen_hashes.json"),
        )
        rules = RuleEngine(ctx.paths.root / "rules").load_for_market(args.market)

        scan_config = ScanConfig()  # Uses defaults; can be overridden from runtime.json
        runtime = ctx.config.runtime
        if "scan" in runtime:
            for k, v in runtime["scan"].items():
                if hasattr(scan_config, k):
                    setattr(scan_config, k, v)

        # LLM call function
        def llm_call(prompt):
            from lib.llm import call_llm
            return call_llm(prompt, config=ctx.config)

        scanner = Scanner(
            knowledge=knowledge, chroma=chroma, run_store=store,
            llm_call=llm_call, rules=rules, config=scan_config,
        )

        result = scanner.scan(market=args.market, date=args.date, watchlist_tickers=tickers)

        # Save candidates to run_store
        for c in result["candidates"]:
            store.save_candidate(
                run_id=run["run_id"], market=args.market,
                primary_ticker=c["primary_ticker"],
                related_tickers=c.get("related_tickers", []),
                direction=c["direction"], confidence=c["confidence"],
                thesis=c["thesis"], evidence=c.get("evidence", []),
                auto_action=c["auto_action"],
                suggested_entry=c.get("suggested_entry"),
                suggested_exit=c.get("suggested_exit"),
                stop_loss=c.get("stop_loss"),
                time_horizon=c.get("time_horizon"),
                risk_factors=c.get("risk_factors", []),
            )

        # Handle auto-lock hypotheses
        from lib.hypothesis import HypothesisManager
        hyp_mgr = HypothesisManager(ctx.paths.root / "hypotheses")
        hypotheses = []
        for c in result["candidates"]:
            if c["auto_action"] in ("auto_lock", "await_approval"):
                hyp = _candidate_to_hypothesis(c, args.market, args.date)
                hyp_mgr.save_draft(hyp, args.date)
                if c["auto_action"] == "auto_lock":
                    hyp_mgr.lock(args.date, args.market, approved_by="system_auto_lock")
                hypotheses.append(hyp)

        # Save artifacts
        artifacts_dir = ctx.paths.root / "scans" / args.date / run["batch_id"]
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "candidates.json").write_text(
            json.dumps(result["candidates"], ensure_ascii=False, indent=2)
        )

        store.update_status(run["run_id"], "completed", artifacts={
            "candidates_path": str(artifacts_dir / "candidates.json"),
            "candidate_count": len(result["candidates"]),
        })

        return {
            "run_id": run["run_id"],
            "batch_id": run["batch_id"],
            "status": "completed",
            "summary": result["summary"],
            "candidates": result["candidates"],
            "hypotheses_created": len(hypotheses),
        }

    except Exception as e:
        store.update_status(run["run_id"], "failed", error=str(e))
        return {"run_id": run["run_id"], "status": "failed", "error": str(e)}


def _candidate_to_hypothesis(candidate, market, date):
    """Convert ScanCandidate to hypothesis dict matching existing schema."""
    return {
        "market": market,
        "ticker": candidate["primary_ticker"],
        "direction": candidate["direction"],
        "thesis": candidate["thesis"],
        "entry_price": candidate.get("suggested_entry"),
        "target_price": candidate.get("suggested_exit"),
        "stop_loss": candidate.get("stop_loss"),
        "time_horizon": candidate.get("time_horizon", "1w"),
        "confidence": candidate["confidence"],
        "evidence_refs": [e["fact_id"] for e in candidate.get("evidence", [])],
        "risk_factors": candidate.get("risk_factors", []),
        "source": "scan_auto",
    }
```

- [ ] **Step 3: Add feedback command handler**

```python
# Add to scripts/harness_cli.py

def _add_feedback_parser(subparsers):
    p = subparsers.add_parser("feedback", help="Apply or reject rule proposals")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve-rule", help="Approve a rule proposal by ID")
    group.add_argument("--reject-rule", help="Reject a rule proposal by ID")
    p.add_argument("--reason", help="Rejection reason")
    p.add_argument("--date", help="Review date to find proposals")
    p.add_argument("--no-notify", action="store_true")


def cmd_feedback(args, ctx: HarnessContext) -> dict:
    import json
    proposal_id = args.approve_rule or args.reject_rule
    approved = args.approve_rule is not None

    # Find rule_proposals.json
    date = args.date or datetime.now().strftime("%Y%m%d")
    proposals_path = ctx.paths.root / "reviews" / date / "rule_proposals.json"
    if not proposals_path.exists():
        return {"status": "error", "error": f"No rule proposals found for {date}"}

    proposals = json.loads(proposals_path.read_text())
    target = None
    for p in proposals:
        if p.get("proposal_id") == proposal_id:
            target = p
            break

    if not target:
        return {"status": "error", "error": f"Proposal {proposal_id} not found"}

    from lib.feedback_engine import FeedbackEngine
    engine = FeedbackEngine(
        knowledge=None, chroma=None, llm_call=None,
        rules=RuleEngine(ctx.paths.root / "rules").load_active(),
    )
    result = engine.apply_rule_proposal(target, approved=approved, reason=args.reason)

    # If approved, apply rule change via RuleEngine
    if approved and target.get("action") == "deprecate" and target.get("rule_id"):
        from lib.rules import RuleEngine
        re = RuleEngine(ctx.paths.root / "rules")
        rules = re.load_all()
        for r in rules:
            if r.rule_id == target["rule_id"]:
                re.update_status(r.rule_id, "deprecated", r.source_file, target.get("rationale"))
                break

    # Update proposals file
    proposals_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2))

    return {"status": "completed", "proposal_id": proposal_id, "action": "approved" if approved else "rejected"}
```

- [ ] **Step 4: Add watchlist command handler**

```python
# Add to scripts/harness_cli.py

def _add_watchlist_parser(subparsers):
    p = subparsers.add_parser("watchlist", help="Manage watchlist tickers")
    sub = p.add_subparsers(dest="watchlist_action")
    add_p = sub.add_parser("add")
    add_p.add_argument("--ticker", required=True)
    add_p.add_argument("--market", help="Auto-detected if not provided")
    add_p.add_argument("--name", help="Display name")
    rem_p = sub.add_parser("remove")
    rem_p.add_argument("--ticker", required=True)
    rem_p.add_argument("--market", help="Auto-detected if not provided")
    sub.add_parser("list").add_argument("--market", help="Filter by market")
    p.add_argument("--no-notify", action="store_true")


def cmd_watchlist(args, ctx: HarnessContext) -> dict:
    from lib.watchlist import add_ticker, remove_ticker, list_tickers, detect_market

    wl_path = ctx.paths.config_dir / "local" / "watchlist.json"

    if args.watchlist_action == "add":
        market = args.market or detect_market(args.ticker)
        return add_ticker(wl_path, ticker=args.ticker, market=market, name=args.name)
    elif args.watchlist_action == "remove":
        market = args.market or detect_market(args.ticker)
        return remove_ticker(wl_path, ticker=args.ticker, market=market)
    elif args.watchlist_action == "list":
        result = list_tickers(wl_path, market=args.market)
        return {"watchlist": result}
    else:
        return {"error": "Unknown watchlist action. Use: add, remove, list"}
```

- [ ] **Step 5: Register commands in COMMAND_HANDLERS**

Add to the COMMAND_HANDLERS dict and parser setup in `harness_cli.py`:

```python
# In COMMAND_HANDLERS dict:
"scan": cmd_scan,
"feedback": cmd_feedback,
"watchlist": cmd_watchlist,

# In argument parser setup, call:
_add_scan_parser(subparsers)
_add_feedback_parser(subparsers)
_add_watchlist_parser(subparsers)
```

- [ ] **Step 6: Update harness_inbound.py to route watchlist**

Read `scripts/harness_inbound.py`. The existing routing should already handle new commands since it parses `/harness <command> <args>` generically. Verify that `watchlist add --ticker X` parses correctly. If the inbound router has a whitelist of commands, add `"watchlist"` and `"scan"` and `"feedback"` to it.

- [ ] **Step 7: Run existing test suite to verify no regressions**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/ -v --timeout=60`
Expected: All existing tests PASS + new tests PASS

- [ ] **Step 8: Commit**

```bash
cd ~/invest_harness
git add scripts/harness_cli.py scripts/harness_inbound.py
git commit -m "feat: wire scan, feedback, watchlist commands into CLI"
```

---

### Task 11: Polymarket Watcher

**Files:**
- Create: `scripts/polymarket_watcher.py`
- Test: `tests/test_polymarket_watcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_polymarket_watcher.py
import pytest
from unittest.mock import MagicMock, patch
from scripts.polymarket_watcher import PolymarketWatcher


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    return adapter


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_runs_by_phase_and_window.return_value = []
    return store


@pytest.fixture
def watcher(mock_adapter, mock_store):
    return PolymarketWatcher(
        adapter=mock_adapter,
        run_store=mock_store,
        watchlist=["cid_1", "cid_2"],
    )


def test_detect_resolved(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_1",
        "resolved": True,
        "outcome": "yes",
        "final_price": 1.0,
    }
    events = watcher.check_market("cid_1")
    assert any(e["type"] == "resolved" for e in events)


def test_detect_price_spike(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.85,
        "price_change_24h": 0.15,
        "hours_to_expiry": 72,
    }
    events = watcher.check_market("cid_2")
    assert any(e["type"] == "price_spike" for e in events)


def test_detect_expiring_soon(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.60,
        "price_change_24h": 0.02,
        "hours_to_expiry": 12,
    }
    events = watcher.check_market("cid_2")
    assert any(e["type"] == "expiring_soon" for e in events)


def test_no_events(watcher, mock_adapter):
    mock_adapter.get_market.return_value = {
        "condition_id": "cid_2",
        "resolved": False,
        "yes_price": 0.50,
        "price_change_24h": 0.01,
        "hours_to_expiry": 168,
    }
    events = watcher.check_market("cid_2")
    assert len(events) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_polymarket_watcher.py::test_detect_resolved -v`
Expected: FAIL

- [ ] **Step 3: Implement PolymarketWatcher**

```python
# scripts/polymarket_watcher.py
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
            return events  # No need to check other events if resolved

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

        # Trigger verify for resolved markets
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

    # Build adapter
    from adapters.market_data import get_adapter
    adapter = get_adapter("polymarket")

    watcher = PolymarketWatcher(adapter=adapter, run_store=store, watchlist=condition_ids)
    result = watcher.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run tests**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_polymarket_watcher.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/invest_harness
git add scripts/polymarket_watcher.py tests/test_polymarket_watcher.py
git commit -m "feat: add PolymarketWatcher for daily event checking"
```

---

### Task 12: OpenClaw invest-loop Skill

**Files:**
- Create: `~/.openclaw/workspace/skills/invest-loop/SKILL.md`
- Create: `~/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh`

- [ ] **Step 1: Create skill directory**

```bash
mkdir -p ~/.openclaw/workspace/skills/invest-loop/scripts
mkdir -p ~/.openclaw/workspace/skills/invest-loop/templates
```

- [ ] **Step 2: Write SKILL.md**

```markdown
# ~/.openclaw/workspace/skills/invest-loop/SKILL.md

---
name: invest-loop
description: 投资研究闭环编排。纯编排层，不含业务逻辑。通过 ClawClau 派发 Codex/Claude agent 执行 harness_cli 命令。
trigger:
  - /invest
  - invest-loop job
---

# invest-loop

投资研究闭环编排 skill。

## 触发方式

- cron: `invest-loop job --phase <scan|verify|review> --market <market> --date <date>`
- 手动: 飞书群发 `/invest scan a_stock` 或 `/invest review`
- 回调: 飞书卡片按钮 → `/invest approve <id>` 或 `/invest reject <id>`

## 编排流程

1. 解析 phase + market + date + trigger_source
2. 通过 ClawClau dispatch 到 agent (Codex 优先, Claude fallback)
3. Agent 执行 `cd ~/invest_harness && python3.11 -m scripts.harness_cli <command> --no-notify`
4. 解析 harness_cli JSON 输出
5. 按 card_data 投递到对应飞书群

## 命令映射

| 触发 | harness_cli 命令 |
|------|-----------------|
| `/invest scan a_stock` | `scan --market a_stock --date TODAY` |
| `/invest verify hk_stock` | `verify --market hk_stock --date TODAY` |
| `/invest review` | `review --date TODAY` |
| `/invest approve H123` | `feedback --approve-rule H123 --date TODAY` |
| `/invest reject H123` | `feedback --reject-rule H123 --date TODAY` |
| `/invest watchlist add 300750.SZ` | `watchlist add --ticker 300750.SZ` |
| `/invest watchlist list` | `watchlist list` |

## 超时配置

| Phase | Timeout |
|-------|---------|
| scan | 600s |
| verify | 300s |
| review | 900s |
| feedback | 60s |
| watchlist | 30s |

## Agent 调度

- 优先: Codex (gpt-5.3-codex)
- 备用: Claude (claude-sonnet-4-6)
- 互为 fallback: 当一方失败/超时/无额度时自动切换
- 同一 run_id 下续跑, agent_trace 记录切换

## 结果路由

- 筛选结果 → 哥玛兽 (gomamon) oc_e3bf797d93e4a3365fc0cdd9b99b429b
- 审批请求 → 加布兽 (gabumon) oc_cd1a764eb1ac0b024462119e0d402210
- 复盘报告 → 哥玛兽 (gomamon)
- 异常告警 → 甲虫兽 (kabuterimon) oc_5c9ae741c8b54919b3d87b832493d6b5
```

- [ ] **Step 3: Write dispatch.sh**

```bash
#!/bin/bash
# ~/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh
# Usage: dispatch.sh --phase <phase> --market <market> --date <date>
#
# Pure orchestration: dispatches harness_cli via ClawClau to Codex/Claude agent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAWCLAU_DIR="$HOME/.openclaw/workspace/skills/clawclau/scripts"
WORKDIR="$HOME/invest_harness"

# Parse args
PHASE=""
MARKET=""
DATE=$(date +%Y%m%d)
TRIGGER="cron"

while [[ $# -gt 0 ]]; do
  case $1 in
    --phase) PHASE="$2"; shift 2 ;;
    --market) MARKET="$2"; shift 2 ;;
    --date) DATE="$2"; shift 2 ;;
    --trigger) TRIGGER="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$PHASE" ]]; then
  echo '{"error": "Missing --phase"}' >&2
  exit 1
fi

# Map phase to harness_cli command and timeout
case $PHASE in
  scan)
    CMD="scan --market $MARKET --date $DATE --no-notify"
    TIMEOUT=600
    ;;
  verify)
    CMD="verify --market $MARKET --date $DATE --no-notify"
    TIMEOUT=300
    ;;
  review)
    CMD="review --date $DATE --no-notify"
    TIMEOUT=900
    ;;
  approve)
    CMD="feedback --approve-rule $MARKET --date $DATE --no-notify"
    TIMEOUT=60
    ;;
  reject)
    CMD="feedback --reject-rule $MARKET --date $DATE --no-notify"
    TIMEOUT=60
    ;;
  watchlist-*)
    # e.g. watchlist-add, watchlist-remove, watchlist-list
    ACTION="${PHASE#watchlist-}"
    CMD="watchlist $ACTION --ticker $MARKET --no-notify"
    TIMEOUT=30
    ;;
  *)
    echo "{\"error\": \"Unknown phase: $PHASE\"}" >&2
    exit 1
    ;;
esac

TASK_ID="invest-${PHASE}-${MARKET:-global}-${DATE}-$(date +%s)"
PROMPT="cd $WORKDIR && python3.11 -m scripts.harness_cli $CMD"

# Dispatch via ClawClau: codex first, claude fallback
if [[ -x "$CLAWCLAU_DIR/claude-spawn.sh" ]]; then
  "$CLAWCLAU_DIR/claude-spawn.sh" \
    --timeout "$TIMEOUT" \
    --replyTo "chat:oc_e3bf797d93e4a3365fc0cdd9b99b429b" \
    "$TASK_ID" \
    "$PROMPT"
else
  # Fallback: run directly without ClawClau
  echo "ClawClau not available, running directly..."
  cd "$WORKDIR"
  python3.11 -m scripts.harness_cli $CMD
fi
```

- [ ] **Step 4: Make dispatch.sh executable**

```bash
chmod +x ~/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh
```

- [ ] **Step 5: Test skill invocation manually**

```bash
# Dry run — should parse and show the command it would execute
~/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh --phase scan --market a_stock --date 20260330
```

- [ ] **Step 6: Commit invest_harness changes**

```bash
cd ~/invest_harness
git add -A
git commit -m "feat: add OpenClaw invest-loop skill for closed-loop orchestration"
```

---

### Task 13: Cron Setup

**Files:**
- Modify: `scripts/cron_dispatch.sh`

- [ ] **Step 1: Read existing cron_dispatch.sh**

Read `scripts/cron_dispatch.sh` to understand the current task routing.

- [ ] **Step 2: Add invest-loop job routing**

Add to `cron_dispatch.sh`:

```bash
# Add to the case statement in cron_dispatch.sh

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
```

- [ ] **Step 3: Document crontab entries**

Create a reference file with the actual crontab lines. These need to be installed manually by the user via `crontab -e`:

```bash
# Add to the bottom of scripts/cron_dispatch.sh as comments:

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
```

- [ ] **Step 4: Commit**

```bash
cd ~/invest_harness
git add scripts/cron_dispatch.sh
git commit -m "feat: add invest-loop job routing to cron_dispatch.sh"
```

---

### Task 14: Integration Test

**Files:**
- Create: `tests/test_integration_scan.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_scan.py
"""Integration test: scan → verify → review → feedback full loop."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def harness_env(tmp_path):
    """Set up a minimal harness environment for integration testing."""
    # Create directory structure
    (tmp_path / "config" / "default").mkdir(parents=True)
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "knowledge" / "raw").mkdir(parents=True)
    (tmp_path / "knowledge" / "normalized").mkdir(parents=True)
    (tmp_path / "knowledge" / "curated").mkdir(parents=True)
    (tmp_path / "hypotheses").mkdir()
    (tmp_path / "reviews").mkdir()
    (tmp_path / "rules").mkdir()
    (tmp_path / "chroma_storage").mkdir()
    (tmp_path / "scans").mkdir()
    (tmp_path / "prompts").mkdir()

    # Write scan prompt
    (tmp_path / "prompts" / "scan.md").write_text("Analyze: {context_bundle}\nRules: {rules}")

    # Write minimal config
    runtime = {
        "llm": {"provider": "test"},
        "transport": {"type": "noop"},
        "knowledge": {"canonical_pipeline_root": str(tmp_path / "knowledge")},
        "markets": {"enabled": ["a_stock"]},
    }
    (tmp_path / "config" / "default" / "runtime.json").write_text(json.dumps(runtime))

    # Write watchlist
    watchlist = {
        "a_stock": [{"ticker": "600519.SH", "name": "贵州茅台", "added_at": "2026-03-28", "added_by": "test"}],
        "hk_stock": [], "us_stock": [], "polymarket": [],
    }
    (tmp_path / "config" / "local" / "watchlist.json").write_text(json.dumps(watchlist))

    # Write a normalized fact
    fact = {"fact_id": "f1", "company": "贵州茅台", "tickers": ["600519.SH"],
            "topic": "earnings", "status": "active", "text": "Q1 revenue up 15%",
            "source_type": "company_research", "source_weight": 0.9,
            "updated_at": "2026-03-29"}
    (tmp_path / "knowledge" / "normalized" / "facts.jsonl").write_text(json.dumps(fact) + "\n")

    # Initialize DB
    from lib.db import get_connection, init_db
    conn = get_connection(str(tmp_path / "harness.db"))
    init_db(conn)

    return tmp_path, conn


def test_scan_creates_candidates(harness_env):
    """Verify scan command produces candidates from knowledge base."""
    tmp_path, conn = harness_env
    from lib.run_store import RunStore
    store = RunStore(conn)

    # Create a run
    run = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="test", knowledge_fingerprint="test",
        date="20260330",
    )
    assert run["status"] == "pending"

    # Save a mock candidate (simulating what scanner would produce)
    cand = store.save_candidate(
        run_id=run["run_id"], market="a_stock",
        primary_ticker="600519.SH", direction="long",
        confidence="high", thesis="Strong Q1",
        evidence=[{"fact_id": "f1", "relevance_score": 0.9, "snippet": "Q1 up 15%"}],
        auto_action="auto_lock",
    )
    assert cand["candidate_id"]

    # Verify candidates are retrievable
    candidates = store.list_candidates(run["run_id"])
    assert len(candidates) == 1
    assert candidates[0]["primary_ticker"] == "600519.SH"

    # Complete run
    store.update_status(run["run_id"], "completed")

    # Verify idempotency — same run returns skipped
    run2 = store.create_run(
        phase="scan", market="a_stock", trigger_source="cron",
        watchlist_hash="test", knowledge_fingerprint="test",
        date="20260330",
    )
    assert run2["status"] == "skipped"


def test_feedback_weight_adjustment(harness_env):
    """Verify feedback engine adjusts knowledge weights."""
    tmp_path, conn = harness_env
    from lib.feedback_engine import FeedbackEngine

    mock_knowledge = MagicMock()
    mock_knowledge.update_source_weight.return_value = True

    engine = FeedbackEngine(
        knowledge=mock_knowledge, chroma=MagicMock(),
        llm_call=MagicMock(), rules=[],
    )

    # Hit → upgrade weight
    adjustments = engine.adjust_weights([{
        "verdict": "hit",
        "hypothesis_ref": "H1",
        "evidence_fact_ids": ["f1"],
    }])
    assert len(adjustments) == 1
    assert adjustments[0]["new_weight"] > adjustments[0]["old_weight"]

    # Miss → downgrade weight
    adjustments = engine.adjust_weights([{
        "verdict": "miss",
        "hypothesis_ref": "H2",
        "evidence_fact_ids": ["f2"],
    }])
    assert len(adjustments) == 1
    assert adjustments[0]["new_weight"] < adjustments[0]["old_weight"]
```

- [ ] **Step 2: Run integration test**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/test_integration_scan.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd ~/invest_harness && python3.11 -m pytest tests/ -v --timeout=60`
Expected: All tests PASS (existing 282 + new ~40 tests)

- [ ] **Step 4: Commit**

```bash
cd ~/invest_harness
git add tests/test_integration_scan.py
git commit -m "test: add integration tests for scan → feedback loop"
```

---

### Task 15: Config & Environment Setup

**Files:**
- Modify: `config/default/runtime.json`
- Modify: `config/local/.env`
- Create: `schemas/run_record.schema.json`

- [ ] **Step 1: Add adapter and scan config to runtime.json**

Read `config/default/runtime.json`. Add the following sections:

```json
{
  "adapters": {
    "a_stock": {"primary": "tushare", "fallback": "akshare"},
    "hk_stock": {"primary": "yfinance", "fallback": null},
    "us_stock": {"primary": "yfinance", "fallback": null},
    "polymarket": {"primary": "clob_api", "fallback": null}
  },
  "scan": {
    "lookback_days": 3,
    "vector_top_k": 5,
    "max_facts_per_ticker": 10,
    "max_snippet_chars": 200,
    "max_insights_per_ticker": 5,
    "min_relevance_score": 0.3,
    "auto_lock_min_evidence": 2,
    "auto_lock_min_sources": 2,
    "auto_lock_max_miss_rate": 0.7
  }
}
```

- [ ] **Step 2: Add environment variables to .env**

Read `config/local/.env`. Add:

```bash
TUSHARE_TOKEN=bzJTKpWoBoXswHkwRmyOpOxWQmxDmBWcRwmaSMxbkYBlmjZGAWyxpyFoCiQdlpBc
TUSHARE_API_URL=http://118.89.66.41:8010/
POLYMARKET_API_KEY=019ce152-42d4-7c8f-bed4-724cddd238d6
POLYMARKET_SECRET=obzdbM8MqYC5TxC8EPplTTYJJkMT3I8CpAez7juXRI0=
POLYMARKET_PASSPHRASE=a246d20c583daf41d7178740bc2e74804a1253161415d6c8249afdba0dadbe57
```

- [ ] **Step 3: Create run_record schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["run_id", "batch_id", "phase", "market", "status"],
  "properties": {
    "run_id": {"type": "string"},
    "batch_id": {"type": "string"},
    "idempotency_key": {"type": "string"},
    "phase": {"enum": ["scan", "verify", "review", "feedback", "watchlist_change"]},
    "market": {"type": "string"},
    "trigger_source": {"enum": ["cron", "manual", "event"]},
    "status": {"enum": ["pending", "running", "completed", "failed", "skipped"]},
    "agent_trace": {"type": "array"},
    "artifacts": {"type": "object"},
    "error": {"type": ["string", "null"]},
    "created_at": {"type": "string"},
    "updated_at": {"type": "string"},
    "completed_at": {"type": ["string", "null"]}
  }
}
```

- [ ] **Step 4: Commit**

```bash
cd ~/invest_harness
git add config/default/runtime.json schemas/run_record.schema.json
git commit -m "feat: add adapter config, scan config, and run_record schema"
```

Note: Do NOT commit `config/local/.env` (it's gitignored and contains secrets).

---

## Post-Implementation Checklist

After all tasks are complete:

- [ ] Run full test suite: `python3.11 -m pytest tests/ -v`
- [ ] Manual smoke test: `python3.11 -m scripts.harness_cli scan --market a_stock --date $(date +%Y%m%d) --no-notify`
- [ ] Manual smoke test: `python3.11 -m scripts.harness_cli watchlist list`
- [ ] Verify OpenClaw skill: `~/.openclaw/workspace/skills/invest-loop/scripts/dispatch.sh --phase scan --market a_stock`
- [ ] Install cron jobs via `crontab -e`
- [ ] Monitor first automated scan run in 哥玛兽 group
