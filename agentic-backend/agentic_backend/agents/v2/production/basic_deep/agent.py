"""
Minimal v2 Deep Agent definition.

This definition intentionally stays small:
- one system prompt
- optional declarative guardrails
- explicit declared tool refs
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    DeepAgentDefinition,
    GuardrailDefinition,
    ReActPolicy,
    ToolRefRequirement,
)

from .prompt_loader import load_basic_deep_prompt

DEFAULT_SYSTEM_PROMPT = load_basic_deep_prompt("basic_deep_system_prompt.md")


class BasicDeepAgentDefinition(DeepAgentDefinition):
    agent_id: str = "basic.deep.v2"
    role: str = "Deep research assistant"
    description: str = (
        "A minimal deep-agent style assistant for multi-step tool-assisted research."
    )
    tags: tuple[str, ...] = ("assistant", "deep")
    system_prompt_template: str = Field(default=DEFAULT_SYSTEM_PROMPT, min_length=1)
    guardrails: tuple[GuardrailDefinition, ...] = ()
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System prompt",
            description="Core behavior instructions for the deep assistant.",
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    )
    declared_tool_refs: tuple[ToolRefRequirement, ...] = ()

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            guardrails=self.guardrails,
        )
