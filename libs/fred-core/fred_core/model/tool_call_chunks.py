# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Narrow compatibility guard for LangChain's eager tool-fragment parsing (#2988)."""

from langchain_core.messages import ai
from langchain_core.utils.json import parse_partial_json


def _parse_object_fragment(s: str, *, strict: bool = False) -> object:
    """Reject impossible object prefixes; delegate repair of object fragments."""
    # AIMessageChunk accepts only dict arguments. Right-trimming/closing the
    # fragment cannot turn a non-object prefix into a dict. Preserve raw chunks
    # and invalid-tool metadata while avoiding quadratic failed parse attempts.
    if not s.lstrip(" \t\r\n").startswith("{"):
        return None
    return parse_partial_json(s, strict=strict)


def install_tool_fragment_guard() -> None:
    """Install once/idempotently from the model factory, never around a request.

    This changes only AIMessageChunk's internal parser reference, not the public
    JSON utility. Remove after an upstream fix and recheck chunk equivalence on
    dependency upgrades: init_tool_calls must continue to accept only objects.
    Object-prefixed fragments still use the upstream parser without a time bound.
    """
    setattr(ai, "parse_partial_json", _parse_object_fragment)
