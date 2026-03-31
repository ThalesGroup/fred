"""
Shared support files for v2 agent runtimes.

Why this package exists:
- keep cross-cutting v2 support concerns out of the main runtime folders
- group the files that define built-in tools, Python-authored toolsets, approval
  policies, and filesystem browsing context

How to use:
- import from these submodules when working on shared v2 support behavior rather
  than one specific runtime family

Example:
- `from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH`
"""
