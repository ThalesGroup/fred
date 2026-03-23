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
RAG expert preset — a catalog-registered agent with a fixed agent_id.

A *preset* is a subclass of BasicReActDefinition that pins one profile as its
permanent default and registers itself under a stable agent_id. Use a preset
when you need a named entry in the Fred agent catalog (e.g. "rag.expert.v2"),
not just an option in the profile dropdown.

If you only need a new assistant variant selectable from the UI, add a profile
in profiles/ instead — no preset class is required.

See AUTHORING.md for the full decision guide.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.v2 import (
    GuardrailDefinition,
    ToolRefRequirement,
)

from .agent import BasicReActDefinition
from .profiles.rag_expert import RAG_EXPERT_PROFILE


class RagExpertV2Definition(BasicReActDefinition):
    """
    Document-grounded ReAct assistant, catalog-registered as "rag.expert.v2".

    All business defaults come from RAG_EXPERT_PROFILE. This class exists
    solely to give the agent a stable catalog identity.
    """

    agent_id: str = "rag.expert.v2"
    react_profile_id: str = RAG_EXPERT_PROFILE.profile_id
    role: str = RAG_EXPERT_PROFILE.role
    description: str = RAG_EXPERT_PROFILE.agent_description
    tags: tuple[str, ...] = RAG_EXPERT_PROFILE.tags
    system_prompt_template: str = Field(
        default=RAG_EXPERT_PROFILE.system_prompt_template,
        min_length=1,
    )
    fields: tuple[FieldSpec, ...] = tuple(
        field.model_copy(update={"default": RAG_EXPERT_PROFILE.profile_id})
        if field.key == "react_profile_id"
        else field.model_copy(deep=True)
        for field in BasicReActDefinition().fields
    )
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        RAG_EXPERT_PROFILE.declared_tool_refs
    )
    guardrails: tuple[GuardrailDefinition, ...] = RAG_EXPERT_PROFILE.guardrails
