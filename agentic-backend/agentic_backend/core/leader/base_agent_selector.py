# app/core/agents/leader_router_protocol.py

from __future__ import annotations

from typing import Any, Dict, Protocol

from pydantic import BaseModel, Field

from agentic_backend.core.agents.agent_flow import AgentFlow


class RoutingDecision(BaseModel):
    """The complete decision structure returned by the LLM, combining expert selection and task rephrasing."""

    expert_name: str = Field(
        description="The name of the single, best-suited expert to execute the task. Must be one of the available expert names."
    )
    task: str = Field(
        description="A clear, concise, rephrased instruction/question tailored specifically for the selected expert. This is the exact content the expert will receive (e.g., 'what is an odd number')."
    )
    rationale: str = Field(
        description="A brief explanation of why this expert was chosen for the objective."
    )


class BaseAgentSelector(Protocol):
    """
    Protocol for a minimalist router that selects the expert and rephrases the task
    in a single atomic operation.
    """

    async def choose_and_rephrase(
        self,
        *,
        objective: str | list[Any],
        experts: Dict[str, AgentFlow],
    ) -> RoutingDecision:
        """
        Selects the best expert and generates a clean, focused task for them.
        """
        ...
