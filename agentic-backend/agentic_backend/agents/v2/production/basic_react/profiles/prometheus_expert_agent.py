"""
Prometheus expert preset declared next to the profile definition.

This class stays intentionally thin so the profile remains the source of truth
for business defaults.
"""

from __future__ import annotations

from pydantic import Field

from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.v2.contracts.models import (
    GuardrailDefinition,
    ToolRefRequirement,
)

from ..agent import BasicReActDefinition
from .prometheus import PROMETHEUS_PROFILE


class PrometheusExpertV2Definition(BasicReActDefinition):
    """Prometheus-grounded ReAct assistant as a Basic ReAct profile preset."""

    agent_id: str = "prometheus.expert.v2"
    react_profile_id: str = PROMETHEUS_PROFILE.profile_id
    role: str = PROMETHEUS_PROFILE.role
    description: str = PROMETHEUS_PROFILE.agent_description
    tags: tuple[str, ...] = PROMETHEUS_PROFILE.tags
    system_prompt_template: str = Field(
        default=PROMETHEUS_PROFILE.system_prompt_template,
        min_length=1,
    )
    fields: tuple[FieldSpec, ...] = tuple(
        field.model_copy(update={"default": PROMETHEUS_PROFILE.profile_id})
        if field.key == "react_profile_id"
        else field.model_copy(deep=True)
        for field in BasicReActDefinition().fields
    )
    declared_tool_refs: tuple[ToolRefRequirement, ...] = (
        PROMETHEUS_PROFILE.declared_tool_refs
    )
    guardrails: tuple[GuardrailDefinition, ...] = PROMETHEUS_PROFILE.guardrails
