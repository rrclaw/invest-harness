"""JSON Schema validation wrapper for invest_harness."""

import json
from pathlib import Path
from jsonschema import validate as _validate
from jsonschema import ValidationError  # re-export

__all__ = ["validate", "ValidationError"]

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_cache: dict[str, dict] = {}


def _load_schema(schema_name: str) -> dict:
    if schema_name in _cache:
        return _cache[schema_name]
    path = _SCHEMA_DIR / f"{schema_name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with open(path) as f:
        schema = json.load(f)
    _cache[schema_name] = schema
    return schema


def validate(instance: dict, schema_name: str) -> None:
    """Validate instance against named schema. Raises ValidationError on failure."""
    schema = _load_schema(schema_name)
    _validate(instance=instance, schema=schema)
