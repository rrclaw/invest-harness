# Getting Started

This guide is for the public, portable version of Invest Harness.

## Prerequisites

- Python 3.11
- macOS or Linux shell environment
- optional: OpenClaw and/or Feishu credentials if you want chat transport later

## Install

```bash
python3.11 -m venv venv
. venv/bin/activate
pip install -e .[dev]
```

## Initialize Local Config

Generate machine-local config from the public templates:

```bash
python3.11 -m scripts.init_local_config --project-root .
```

This writes:

- `config/local/runtime.json`
- `config/local/watchlist.json`
- `config/local/portfolio_snapshot.json`
- `config/local/.env`

The generated config is noop-first, so the repository can run without OpenClaw,
Feishu, or real provider secrets.

## First Smoke Test

Run a local command that exercises config loading, database init, and the unified
CLI without sending any chat messages:

```bash
python3.11 -m scripts.harness_cli --project-root . backup --date-override 2026-03-27
```

Expected result:

- command exits successfully
- a JSON result is printed
- transport returns a noop result unless you explicitly enabled a real transport

## Optional Validation

```bash
python3.11 -m pytest -q
```

## Next Steps

- Edit `config/local/runtime.json` to enable markets, rule files, and local paths.
- Edit `config/local/.env` only for the adapters or providers you actually use.
- Keep `config/local/` out of git.
- Enable OpenClaw or Feishu only after the noop smoke test is clean.
