"""
Smallest ReAct v2 example.

Use this file as a template when building a conversational assistant:
- set role/description/tags
- set prompt
- declare tool refs
- keep runtime logic in shared `ReActRuntime`
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    ReActAgentDefinition,
    ReActPolicy,
    ToolApprovalPolicy,
    ToolRefRequirement,
)

from .profile_registry import list_react_profiles, profile_options_summary


def _default_react_profile_id() -> str:
    profiles = list_react_profiles()
    if not profiles:
        raise ValueError(
            "No Basic ReAct profiles are available. "
            "Define at least one profile module under basic_react/profiles."
        )
    for preferred_id in ("base_assistant",):
        for profile in profiles:
            if profile.profile_id == preferred_id:
                return profile.profile_id
    return profiles[0].profile_id


DEFAULT_REACT_PROFILE_ID = _default_react_profile_id()


def _basic_react_fields() -> tuple[FieldSpec, ...]:
    """
    Build the author/admin-facing field surface for the generic ReAct agent.

    Why this helper exists:
    - the available profile ids come from the backend profile library
    - the field list should remain a single clear declaration in this file
    - the generic agent stays simple, while profiles provide stronger defaults
    """

    return (
        FieldSpec(
            key="react_profile_id",
            type="select",
            title="Starting profile",
            description=(
                "Choose a backend-defined starting profile. "
                "A profile can prefill the prompt, MCP defaults, and safety policy.\n"
                f"{profile_options_summary()}"
            ),
            required=True,
            default=DEFAULT_REACT_PROFILE_ID,
            enum=[profile.profile_id for profile in list_react_profiles()],
            ui=UIHints(group="Profile", hide=True),
        ),
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="agentTuning.fields.prompts_system.title",
            description="agentTuning.fields.prompts_system.description",
            required=True,
            ui=UIHints(
                group="agentTuning.groups.prompts", multiline=True, markdown=True
            ),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="agentTuning.fields.chat_options_attach_files.title",
            description="agentTuning.fields.chat_options_attach_files.description",
            required=False,
            default=False,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="agentTuning.fields.chat_options_libraries_selection.title",
            description="agentTuning.fields.chat_options_libraries_selection.description",
            required=False,
            default=False,
            ui=UIHints(group="agentTuning.groups.chatOptions"),
        ),
        FieldSpec(
            key="enable_tool_approval",
            type="boolean",
            title="Require approval for mutating tools",
            description=(
                "When enabled, the runtime pauses before tool calls that look "
                "like state-changing actions."
            ),
            required=False,
            default=False,
            ui=UIHints(group="Safety", hide=True),
        ),
        FieldSpec(
            key="approval_required_tools",
            type="array",
            item_type="string",
            title="Always-approve tool names",
            description=(
                "Exact tool names that must always ask for human approval "
                "before execution."
            ),
            required=False,
            default=[],
            ui=UIHints(group="Safety", hide=True),
        ),
    )


class BasicReActDefinition(ReActAgentDefinition):
    """
    Baseline definition for generic ReAct assistants.

    Quick edit guide:
    - `system_prompt_template`: assistant behavior
    - `tool_requirements`: allowed capabilities
    - `fields`: what admins can tune in UI
    - `policy()`: small runtime behavior switches
    """

    agent_id: str = "basic.react.v2"
    role: str = "General assistant with optional tools"
    description: str = (
        "A concise assistant that can answer directly or use explicitly declared "
        "platform tools when they are available."
    )
    tags: tuple[str, ...] = ("assistant", "react")
    # Author/admin-owned: choose the business starting profile.
    # This does not create a new runtime. It selects a backend-defined recipe
    # that can prefill prompt, MCP defaults, and safety policy.
    react_profile_id: str = DEFAULT_REACT_PROFILE_ID
    # Author-owned: business instructions only.
    # Main business instruction for the agent.
    # A developer edits this when they want to change the answer style or core
    # user-facing behavior.
    system_prompt_template: str | None = Field(
        default=None,
        min_length=1,
    )
    # Author-owned: optional human approval for sensitive tool calls.
    # A developer enables this when a generic tool agent should pause before
    # executing mutating actions such as create/update/delete/notify.
    enable_tool_approval: bool = False
    # Author-owned: exact tool names that must always require approval.
    # This lets a developer protect specific business actions even when their
    # name does not match the default mutating-tool heuristics.
    approval_required_tools: tuple[str, ...] = ()
    # Author-owned: explicit operating constraints appended by the runtime.
    # Profiles can set these to enforce grounding/uncertainty style rules.
    guardrails: tuple[GuardrailDefinition, ...] = ()
    # Author-owned: UI tuning surface exposed for this agent.
    # UI-exposed configuration for this agent.
    # A developer adds fields here when users should be able to tune prompts or
    # other business options from the interface.
    fields: tuple[FieldSpec, ...] = _basic_react_fields()
    # Author-owned: declare allowed capabilities, not how tools are executed.
    # Declared business capabilities available to the agent.
    # This basic example starts without tools, but a developer can add them
    # later by listing tool refs here.
    tool_requirements: tuple[ToolRefRequirement, ...] = ()

    def policy(self) -> ReActPolicy:
        """
        Return the runtime policy used by `ReActRuntime`.
        """

        # Author-owned: declare behavior. Framework-owned: execute it.
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            tool_approval=ToolApprovalPolicy(
                enabled=self.enable_tool_approval,
                always_require_tools=tuple(self.approval_required_tools),
            ),
            guardrails=self.guardrails,
        )
