"""
Generic tool-enabled assistant for the v2 contract.

Why this file exists:
- It is the smallest real authoring example for the new API.
- It shows the intended split: the agent definition expresses the business
  identity of the assistant, while execution lives in the shared ReAct runtime.
- It stays intentionally narrow so Fred can validate the new model without
  carrying over every historical `AgentFlow` concern at once.

 Why a developer should care:
 - it is the clean starting point for assistants that are mainly conversational
 - it keeps the prompt, safety stance, and optional tools easy to reason about
 - it lets a team create several useful business assistants from one runtime
   through profiles, instead of copying agent classes
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    ReActAgentDefinition,
    ReActPolicy,
    ToolApprovalPolicy,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.prompt_resources import (
    load_packaged_markdown,
)
from agentic_backend.core.agents.v2.react_profiles import (
    GENERIC_ASSISTANT_PROFILE_ID,
    list_react_profiles,
    profile_options_summary,
)


DEFAULT_SYSTEM_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=("agents", "v2", "prompts", "basic_react_system_prompt.md"),
)


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
            default=GENERIC_ASSISTANT_PROFILE_ID,
            enum=[profile.profile_id for profile in list_react_profiles()],
            ui=UIHints(group="Profile"),
        ),
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description=(
                "Core behavior instructions for the assistant. This stays on the "
                "definition side so the runtime can remain generic."
            ),
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
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
            ui=UIHints(group="Safety"),
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
            ui=UIHints(group="Safety"),
        ),
    )


class BasicReActV2Definition(ReActAgentDefinition):
    """
    Standard v2 pattern for a general-purpose assistant.

    A developer uses this definition when the business need is simple:
    describe the assistant's role, tone, and permissions, then let Fred handle
    the conversation and tool loop.

    Developer guide:
    - Edit `system_prompt_template` when you want to change how the assistant
      should answer, reason at a high level, or speak to the user.
    - Edit `tool_requirements` when you want this assistant to be allowed to
      call one or more platform tools.
    - Edit `fields` when you want the UI to expose developer-controlled tuning
      options for this agent.
    - Edit `policy()` when you want to summarize the main behavior rules in a
      simple structured way for the shared runtime.
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
    react_profile_id: str = GENERIC_ASSISTANT_PROFILE_ID
    # Author-owned: business instructions only.
    # Main business instruction for the agent.
    # A developer edits this when they want to change the answer style or core
    # user-facing behavior.
    system_prompt_template: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
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
        Plain-English behavior contract for the shared ReAct runtime.

        Developer view:
        - `react_profile_id` selects a backend-defined starting recipe such as
          `generic_assistant` or `custodian`.
        - `system_prompt_template` is the main instruction set for the agent.
        - `policy()` is the clean summary of how the assistant should behave.
        - `tool_approval` tells the shared runtime whether some tool calls must
          pause and wait for a user decision before execution.
        - The framework reads this policy and builds the actual runtime loop.

        This basic agent does not add extra guardrails yet, so the policy is
        just the main prompt.
        """

        # Author-owned: declare behavior. Framework-owned: execute it.
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            tool_approval=ToolApprovalPolicy(
                enabled=self.enable_tool_approval,
                always_require_tools=tuple(self.approval_required_tools),
            ),
        )
