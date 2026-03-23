# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Profile model for Basic ReAct starting profiles.

Profiles are business defaults for one agent family. They are intentionally
stored next to the agent implementation, not in runtime core.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    MCPServerRef,
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
    The configuration recipe for a specific business assistant.
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
    declared_tool_refs: tuple[ToolRefRequirement, ...] = ()
    chat_options: AgentChatOptions = Field(default_factory=AgentChatOptions)
