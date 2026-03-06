"""
Profile model for Basic ReAct starting profiles.

Profiles are business defaults for one agent family. They are intentionally
stored next to the agent implementation, not in runtime core.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_spec import MCPServerRef
from agentic_backend.core.agents.v2.models import (
    GuardrailDefinition,
    ToolRefRequirement,
)

PROFILE_MANAGED_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        "react_profile_id",
        "role",
        "description",
        "tags",
        "system_prompt_template",
        "enable_tool_approval",
        "approval_required_tools",
        "guardrails",
    }
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ReActProfile(FrozenModel):
    """
    Typed profile payload consumed by catalog/settings compatibility helpers.

    A profile is a reusable business preset: prompt, safety posture, tool
    allow-list, guardrails, and chat affordances.
    """

    profile_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    agent_description: str = Field(..., min_length=1)
    tags: tuple[str, ...] = ()
    system_prompt_template: str = Field(..., min_length=1)
    enable_tool_approval: bool = False
    approval_required_tools: tuple[str, ...] = ()
    guardrails: tuple[GuardrailDefinition, ...] = ()
    mcp_servers: tuple[MCPServerRef, ...] = ()
    tool_requirements: tuple[ToolRefRequirement, ...] = ()
    chat_options: AgentChatOptions = Field(default_factory=AgentChatOptions)
