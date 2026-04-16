"""
Authoring helpers for Fred workflow-shaped graph agents.

Why this package exists:
- keep reusable graph authoring helpers close to the graph runtime family
- provide a narrow layer that reduces ceremony without replacing LangGraph

How to use it:
- import only the helpers that remove real duplication in your graph definition
- use ``TeamAgent`` and ``AgentSpec`` when composing multiple specialists into
  a coordinated team without writing explicit nodes and state schemas

SDK extraction note:
- this entire package is part of the public authoring surface
- it does not import Fred platform internals and is safe to publish as a
  standalone SDK package without modification

Example (single graph agent):
- ``from fred_sdk.graph.authoring import typed_node``

Example (multi-agent team):
- ``from fred_sdk.graph.authoring import TeamAgent, AgentSpec``
"""

from ..runtime import AgentInvocationResult
from .api import (
    GraphAgent,
    GraphWorkflow,
    StepResult,
    WorkflowNode,
    choice_step,
    finalize_step,
    intent_router_step,
    model_text_step,
    structured_model_step,
    typed_node,
)
from .team_api import (
    AgentSpec,
    TeamAgent,
    TeamInput,
    TeamMemberResult,
    TeamState,
)

__all__ = [
    # Single-agent graph authoring
    "GraphAgent",
    "GraphWorkflow",
    "StepResult",
    "WorkflowNode",
    "choice_step",
    "finalize_step",
    "intent_router_step",
    "model_text_step",
    "structured_model_step",
    "typed_node",
    # Agent invocation result — the typed output of invoke_agent()
    "AgentInvocationResult",
    # Multi-agent team authoring
    "AgentSpec",
    "TeamAgent",
    "TeamInput",
    "TeamMemberResult",
    "TeamState",
]
