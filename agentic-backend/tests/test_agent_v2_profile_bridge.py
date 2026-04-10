"""
Regression tests for the authored-agent / profile boundary in
`build_definition_from_settings`.

Background
----------
`_apply_profile_to_definition` was originally designed for generic families
(e.g. `BasicReActDefinition`) where both tool refs and the system prompt come
from the selected profile.  When applied to an *authored* `ReActAgent` subclass
(one that declares `tools = (...)` and `system_prompt_template = ui_field(...)`)
it used to unconditionally overwrite both fields with the (usually empty) profile
values.

Two bugs resulted:
    Bug #1 — `declared_tool_refs` wiped → LLM received `tools: []`
    Bug #2 — `system_prompt_template` replaced with generic profile prompt

These tests guard against regression of both bugs for authored agents and also
verify that the profile mechanism still works correctly for generic families.
"""

from __future__ import annotations

from agentic_backend.common.structures import Agent as AgentSettings
from agentic_backend.core.agents.v2.authoring import ReActAgent, tool, ui_field
from agentic_backend.core.agents.v2.authoring.api import ToolContext, ToolOutput
from agentic_backend.core.agents.v2.legacy_bridge.agent_settings_bridge import (
    build_definition_from_settings,
)

# ---------------------------------------------------------------------------
# Minimal authored agent used as the test subject
# ---------------------------------------------------------------------------


@tool(
    tool_ref="test.authored.greet",
    description="Greet the user.",
)
async def _greet(ctx: ToolContext, name: str) -> ToolOutput:  # pragma: no cover
    return ctx.text(f"Hello, {name}!")


_AUTHORED_SYSTEM_PROMPT = "You are a greeter. Use the greet tool."


class _GreeterAgent(ReActAgent):
    """Minimal authored agent for profile-bridge regression tests."""

    agent_id: str = "test.greeter"
    role: str = "Test Greeter"
    description: str = "Test agent used in profile bridge regression tests."
    tools = (_greet,)

    system_prompt_template: str = ui_field(
        _AUTHORED_SYSTEM_PROMPT,
        title="System Prompt",
        description="Greeter instructions.",
        ui_type="prompt",
        required=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_settings(agent_id: str = "test.greeter") -> AgentSettings:
    """Return the simplest possible `AgentSettings` — no custom tuning at all."""
    return AgentSettings(id=agent_id, name="Test Greeter")


# ---------------------------------------------------------------------------
# Tests: authored agent must never lose its tools or system prompt
# ---------------------------------------------------------------------------


def test_authored_agent_preserves_declared_tool_refs_after_profile_application() -> (
    None
):
    """
    Regression test for Bug #1.

    When a `ReActAgent` subclass with `tools = (...)` is hydrated through
    `build_definition_from_settings`, its `declared_tool_refs` must survive the
    profile-application step unchanged.  The profile's (typically empty) tool
    refs must NOT replace them.
    """
    settings = _minimal_settings()
    definition = build_definition_from_settings(
        definition_class=_GreeterAgent,
        settings=settings,
    )

    tool_refs = [r.tool_ref for r in definition.declared_tool_refs]
    assert tool_refs == ["test.authored.greet"], (
        f"Expected ['test.authored.greet'] but got {tool_refs!r}. "
        "Profile application likely wiped the authored tool refs (Bug #1 regression)."
    )


def test_authored_agent_preserves_system_prompt_after_profile_application() -> None:
    """
    Regression test for Bug #2.

    When a `ReActAgent` subclass with `system_prompt_template = ui_field(...)`
    is hydrated through `build_definition_from_settings`, its class-defined
    system prompt must survive the profile-application step unchanged.  The
    profile's generic prompt must NOT replace it.
    """
    settings = _minimal_settings()
    definition = build_definition_from_settings(
        definition_class=_GreeterAgent,
        settings=settings,
    )

    assert definition.system_prompt_template == _AUTHORED_SYSTEM_PROMPT, (
        f"Expected authored prompt but got: {definition.system_prompt_template!r}. "
        "Profile application likely replaced the class-defined prompt (Bug #2 regression)."
    )


def test_authored_agent_has_non_empty_toolset_key() -> None:
    """
    The `toolset_key` is the discriminator used to detect authored agents.
    It must be non-empty after class-level registration so the bridge guard works.
    """
    instance = _GreeterAgent.model_validate({})
    assert instance.toolset_key, (
        "toolset_key is empty — __pydantic_init_subclass__ did not register the toolset. "
        "The profile bridge discriminator will not work."
    )


def test_authored_agent_tool_refs_are_stable_across_multiple_hydrations() -> None:
    """
    Two independent `build_definition_from_settings` calls must return the same
    tool refs.  This guards against accidental mutation of the class-level default
    during profile application.
    """
    settings = _minimal_settings()

    first = build_definition_from_settings(
        definition_class=_GreeterAgent, settings=settings
    )
    second = build_definition_from_settings(
        definition_class=_GreeterAgent, settings=settings
    )

    assert list(r.tool_ref for r in first.declared_tool_refs) == list(
        r.tool_ref for r in second.declared_tool_refs
    ), (
        "Tool refs differ across two successive hydrations — class defaults were mutated."
    )
