"""
Authoring helpers for Fred workflow-shaped graph agents.

Why this package exists:
- keep reusable graph authoring helpers close to the graph runtime family
- provide a narrow layer that reduces ceremony without replacing LangGraph

How to use it:
- import only the helpers that remove real duplication in your graph definition

Example:
- `from agentic_backend.core.agents.v2.graph.authoring import typed_node`
"""

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

__all__ = [
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
]
