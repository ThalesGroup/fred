"""Helpers for accessing the canonical SpiceDB schema."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.zed")


@lru_cache(maxsize=1)
def load_default_schema() -> str:
    """Read and cache the version-controlled SpiceDB schema."""

    return _SCHEMA_PATH.read_text(encoding="utf-8")


DEFAULT_SCHEMA = load_default_schema()
