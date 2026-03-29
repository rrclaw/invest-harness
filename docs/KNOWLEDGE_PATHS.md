# Knowledge Paths

Invest Harness separates repository-owned pipeline storage from external or
historical source locations.

## Path Roles

| Field | Meaning | Write policy |
|------|---------|--------------|
| `canonical_pipeline_root` | Harness-owned pipeline root inside the repository | writable |
| `bridge_sources` | upstream external knowledge sources | read-first, bridge-specific |
| `historical_inputs` | legacy paths used for inventory and controlled ingest | read-only by default |
| `read_only_inputs` | locations that must never be modified by Harness | read-only |

## Public Default

The public default keeps the canonical pipeline inside the repository:

- `knowledge/raw/`
- `knowledge/normalized/`
- `knowledge/curated/`

These directories are scaffolded publicly, while local data inside them stays
out of git.

## Migration Principles

- do not move, delete, or overwrite historical knowledge files without confirmation
- prefer scanning and inventory before migration
- keep external knowledge roots configurable through `config/local/runtime.json`
- do not make the public repository depend on `~/.openclaw/...` paths

## Practical Rule

Use the repository for the Harness pipeline itself. Treat external knowledge
directories as explicit inputs, not hidden runtime dependencies.
