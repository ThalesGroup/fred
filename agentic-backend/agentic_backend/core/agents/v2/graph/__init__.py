"""
Graph-agent runtime family for Fred v2.

Why this package exists:
- keep graph runtime types and the graph executor under one explicit folder
- make it clear that graph agents are a separate runtime family from ReAct

How to use it:
- import `GraphRuntime` and related graph runtime result types from here

Example:
- `from agentic_backend.core.agents.v2.graph import GraphRuntime`
"""

from .runtime import (
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeHandler,
    GraphNodeResult,
    GraphRuntime,
)

__all__ = [
    "GraphExecutionOutput",
    "GraphNodeContext",
    "GraphNodeHandler",
    "GraphNodeResult",
    "GraphRuntime",
]
