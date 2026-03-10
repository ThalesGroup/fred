from __future__ import annotations

from .models import AgentDefinition, AgentInspection


def inspect_agent(definition: AgentDefinition) -> AgentInspection:
    """
    Canonical non-activating inspection entrypoint for v2 agents.
    """

    return definition.inspect()
