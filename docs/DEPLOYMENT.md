# Deployment

This repository is designed to move cleanly to a new Mac Mini or another local
machine without changing workflow contracts.

## Portable Deployment Checklist

1. Clone the repository.
2. Create a Python 3.11 environment.
3. Install with `pip install -e .[dev]`.
4. Run `python3.11 -m scripts.init_local_config --project-root .`.
5. Fill only the local settings you need in `config/local/`.
6. Run a noop smoke test before enabling transports.

## New Machine Workflow

On a new Mac Mini:

```bash
git clone <your-repo-url>
cd invest_harness
python3.11 -m venv venv
. venv/bin/activate
pip install -e .[dev]
python3.11 -m scripts.init_local_config --project-root .
python3.11 -m scripts.harness_cli --project-root . backup --date-override 2026-03-27
```

## Local-Only Material

Do not move these into the public repository:

- `config/local/`
- local `.env` values
- local OpenClaw workspace paths
- Feishu group IDs
- generated hypotheses, reviews, logs, backups, and knowledge artifacts

## Optional Integration Layers

After the noop smoke test passes, you can opt into:

- `openclaw` transport for outbound delivery
- `direct_feishu` transport for direct API delivery
- inbound command routing via `scripts/harness_inbound.py`

Those steps are documented in [OPENCLAW_FEISHU.md](OPENCLAW_FEISHU.md).
