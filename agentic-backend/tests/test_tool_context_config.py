"""
Unit tests for ToolContext.config().

These tests stay offline — no LLM or network calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import Field

from agentic_backend.core.agents.v2.authoring import ReActAgent, ToolContext
from agentic_backend.core.agents.v2.authoring.legacy_runtime_bridge import (
    _AuthorRuntime,
)

# ---------------------------------------------------------------------------
# Minimal agent used as the config carrier
# ---------------------------------------------------------------------------


class _SampleAgent(ReActAgent):
    agent_id: str = "test.config.v2"
    role: str = "Test agent"
    description: str = "Used to verify ToolContext.config()"
    system_prompt_template: str = "You are a test agent."
    template_key: str = Field(default="default_tpl")
    threshold: float = Field(default=0.75)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(definition: Any) -> ToolContext:
    """Build a minimal ToolContext whose _runtime.definition is `definition`."""
    runtime = MagicMock(spec=_AuthorRuntime)
    runtime.definition = definition
    return ToolContext(runtime)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_config_returns_declared_field() -> None:
    ctx = _make_ctx(_SampleAgent())
    assert ctx.config("template_key") == "default_tpl"


def test_config_returns_overridden_field() -> None:
    ctx = _make_ctx(_SampleAgent(template_key="custom_tpl"))
    assert ctx.config("template_key") == "custom_tpl"


def test_config_float_field() -> None:
    ctx = _make_ctx(_SampleAgent(threshold=0.9))
    assert ctx.config("threshold") == pytest.approx(0.9)


def test_config_default_returned_when_field_missing() -> None:
    ctx = _make_ctx(_SampleAgent())
    result = ctx.config("nonexistent_field", default="fallback")
    assert result == "fallback"


def test_config_raises_key_error_when_field_missing_and_no_default() -> None:
    ctx = _make_ctx(_SampleAgent())
    with pytest.raises(KeyError, match="nonexistent_field"):
        ctx.config("nonexistent_field")


def test_config_dotted_path() -> None:
    """Dotted path walks attribute chain on the definition."""
    inner = MagicMock()
    inner.value = 42

    definition = MagicMock()
    definition.nested = inner

    ctx = _make_ctx(definition)
    assert ctx.config("nested.value") == 42


def test_config_dotted_path_with_default_when_intermediate_missing() -> None:
    definition = MagicMock(spec=[])  # no attributes
    ctx = _make_ctx(definition)
    assert ctx.config("missing.value", default=99) == 99
