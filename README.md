# Invest Harness

Investment research harness: knowledge pipeline, hypothesis management, monitoring, and orchestration.

## Runtime

- **Unified runtime: Python 3.11** — all scripts, tests, and the polling daemon run on Python 3.11.
- `pyproject.toml` declares `requires-python = ">=3.9"` for broad compatibility, but CI and production use 3.11.

## Plans

| Tag | Scope |
|-----|-------|
| `v0.1.0-foundation` | Core scaffold, config, schemas, SQLite, state machine, adapters |
| `v0.2.0-knowledge` | Knowledge pipeline (dedup, decay, ChromaDB, ingest) |
| `v0.3.0-hypothesis-monitoring` | Hypothesis, alerts, verification, polling |
| `v0.4.0-orchestration` | Rules, review, Feishu, conductor, cron |
