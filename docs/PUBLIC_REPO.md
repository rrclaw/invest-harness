# Public Repository Boundaries

This repository is meant to be publishable without shipping machine-local state.

## Commit These

- source code in `adapters/`, `lib/`, `scripts/`, and `tests/`
- schemas, prompts, and rules
- `config/default/`
- `config/examples/`
- documentation
- empty public scaffolding such as `knowledge/`, `hypotheses/`, and `reviews/`

## Keep Local

- `config/local/`
- `.env` values
- `harness.db` and WAL files
- `backups/`
- `logs/`
- `chroma_storage/`
- generated hypotheses and reviews
- local knowledge contents
- local OpenClaw paths and Feishu mappings

## Publish Checklist

1. `git status --short` should not show runtime artifacts.
2. Public docs should explain first-run setup and optional integrations.
3. `config/examples/` should contain placeholders only.
4. The repository should pass a noop-first smoke test on a clean clone.
5. Live chat integrations should remain optional until local config is filled.
