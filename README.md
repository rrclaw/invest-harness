# Invest Harness

Portable investment research harness: knowledge pipeline, hypothesis lifecycle,
monitoring, review, and configurable message delivery.

This repository is structured to be public-safe by default:

- public defaults live in `config/default/`
- copyable templates live in `config/examples/`
- machine-local state lives in `config/local/` and stays out of git
- the default first-run transport is `noop`, so a fresh clone can run smoke tests
  before OpenClaw or Feishu are configured

## What It Is

Invest Harness keeps the existing P1-P4 workflow contracts while making the
outer runtime portable:

- schemas, state names, and adapter interfaces stay stable
- runtime behavior is configured through layered config, not hard-coded local paths
- outbound notifications route through a transport abstraction
- inbound chat commands can be parsed into the unified Harness CLI

## Quick Start

1. Create a Python 3.11 environment and install the project:

   ```bash
   python3.11 -m venv venv
   . venv/bin/activate
   pip install -e .[dev]
   ```

2. Generate local-only config from the public templates:

   ```bash
   python3.11 -m scripts.init_local_config --project-root .
   ```

3. Run a noop-first smoke test. This does not require OpenClaw, Feishu, or live
   secrets:

   ```bash
   python3.11 -m scripts.harness_cli --project-root . backup --date-override 2026-03-27
   ```

4. Optional: run the test suite:

   ```bash
   python3.11 -m pytest -q
   ```

## Layered Config

| Path | Purpose | Git policy |
|------|---------|------------|
| `config/default/` | public-safe defaults used at runtime | committed |
| `config/examples/` | copy templates and examples only | committed |
| `config/local/` | machine-local overrides, paths, group maps, secrets entrypoints | ignored |

Runtime loading uses `config/default + config/local`. Public examples are never
loaded implicitly at runtime.

## Knowledge Path Model

The public repository keeps `knowledge/` as the Harness-owned canonical pipeline
root. External knowledge sources are connected through config:

- `canonical_pipeline_root`: repo-local writable pipeline root
- `bridge_sources`: upstream external sources that Harness may read from
- `historical_inputs`: legacy input locations used for inventory or controlled ingest
- `read_only_inputs`: paths that must not be mutated by Harness

More detail is in [docs/KNOWLEDGE_PATHS.md](docs/KNOWLEDGE_PATHS.md).

## CLI Surface

The unified CLI entry point lives in `scripts/harness_cli.py` and exposes:

- `ingest`
- `hypothesis`
- `lock`
- `verify`
- `review`
- `rule_update`
- `rule_audit`
- `backup`

For inbound command routing, use `scripts/harness_inbound.py`.

## Transport Modes

- `noop`: default public-safe mode for first-run and smoke tests
- `openclaw`: optional outbound via local OpenClaw CLI
- `direct_feishu`: optional direct Feishu API transport

The transport layer is configured in `runtime.json`, not hard-coded in code.

## Public Repository Docs

- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/OPENCLAW_FEISHU.md](docs/OPENCLAW_FEISHU.md)
- [docs/KNOWLEDGE_PATHS.md](docs/KNOWLEDGE_PATHS.md)
- [docs/PUBLIC_REPO.md](docs/PUBLIC_REPO.md)
- [knowledge/README.md](knowledge/README.md)

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
