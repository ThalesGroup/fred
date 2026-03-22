"""
Deep-agent runtime family for Fred v2.

Why this package exists:
- keep the v2 root readable by grouping the deep-agent-specific runtime under
  one explicit folder

How to use it:
- import `DeepAgentRuntime` when wiring or inspecting the deep-agent runtime

Example:
- `from agentic_backend.core.agents.v2.deep import DeepAgentRuntime`
"""

from .runtime import DeepAgentRuntime

__all__ = ["DeepAgentRuntime"]
