"""
Small shared helpers for v2 ReAct tool binding.

Why this module exists:
- keep generic payload and naming rules out of `react_tool_binding.py`
- make the reusable non-binding rules explicit and easy to test

How to use:
- import these helpers when turning Fred tool refs or tool payloads into the
  normalized shapes expected by LangChain tools and Fred ports

Example:
- `tool_name = sanitize_tool_name("artifacts.publish_text")`
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel


def normalize_payload(value: object) -> object:
    """
    Convert pydantic-rich tool payloads to plain JSON-compatible values.

    Why this exists:
    - LangChain tools can receive nested `BaseModel`, tuple, list, and dict values
    - Fred tool ports should receive one normalized JSON-like payload shape

    How to use:
    - pass the raw payload before sending it to a Fred tool port

    Example:
    - `payload = normalize_payload(dict(payload))`
    """

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(key): cast(object, normalize_payload(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [cast(object, normalize_payload(item)) for item in value]
    if isinstance(value, tuple):
        return [cast(object, normalize_payload(item)) for item in value]
    return value


def sanitize_tool_name(tool_ref: str) -> str:
    """
    Convert one Fred tool reference to a LangChain-safe tool name.

    Why this exists:
    - Fred tool refs can contain punctuation such as `.` that does not fit
      LangChain tool naming rules
    - the runtime needs one stable sanitization rule across declared and
      runtime-provider tools

    How to use:
    - pass any tool ref or runtime-provided tool name before exposing it to the model

    Example:
    - `sanitize_tool_name("artifacts.publish_text")`
    """

    cleaned = "".join(ch if ch.isalnum() else "_" for ch in tool_ref.strip().lower())
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = "tool"
    if cleaned[0].isdigit():
        cleaned = f"tool_{cleaned}"
    return cleaned
