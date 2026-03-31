"""
ReAct runtime implementation package for v2 agents.

Why this package exists:
- group the reviewed ReAct runtime files under one obvious scope
- keep the ReAct execution surface separate from contracts, graph, and deep files

How to use:
- import concrete helpers from the submodules in this package when working on the
  ReAct runtime internals

Example:
- `from agentic_backend.core.agents.v2.react.react_runtime import ReActRuntime`
"""
