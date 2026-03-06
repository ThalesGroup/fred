"""
RAG expert preset class declared next to profile definitions.

This class is intentionally thin: profile data remains the single source of
business defaults.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.v2.models import (
    GuardrailDefinition,
    ToolRefRequirement,
)

from ..agent import BasicReActDefinition
from .rag_expert import RAG_EXPERT_PROFILE


class RagExpertV2Definition(BasicReActDefinition):
    """Document-grounded ReAct assistant as a Basic ReAct profile preset."""

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
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        RAG_EXPERT_PROFILE.tool_requirements
    )
    guardrails: tuple[GuardrailDefinition, ...] = RAG_EXPERT_PROFILE.guardrails
