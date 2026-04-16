"""Helpers for accessing the canonical OpenFGA schema."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SCHEMA_JSON_PATH = Path(__file__).with_name("schema.fga.json")


@lru_cache(maxsize=1)
def _load_default_schema_json_source() -> str:
    """Read and cache the JSON form of the OpenFGA schema."""

    return _SCHEMA_JSON_PATH.read_text(encoding="utf-8")


DEFAULT_SCHEMA = _load_default_schema_json_source()
