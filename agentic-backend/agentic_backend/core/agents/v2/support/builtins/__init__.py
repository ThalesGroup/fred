"""
Explicit package for the small native Fred built-in tool catalog.

Why this package exists:
- built-in tools are a tiny fixed catalog and should be visually separated from
  other support files
- this makes it easy to review exactly what Fred ships natively before any
  Python-authored tools or MCP/runtime tools are added

How to use it:
- import the `TOOL_REF_*` constants or the catalog lookup helpers from this
  package

Example:
- `from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH`
"""

from .catalog import (
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_LOGS_QUERY,
    TOOL_REF_RESOURCES_FETCH_TEXT,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
    BuiltinToolBackend,
    BuiltinToolSpec,
    get_builtin_tool_spec,
    list_builtin_tool_specs,
)

__all__ = [
    "TOOL_REF_ARTIFACTS_PUBLISH_TEXT",
    "TOOL_REF_GEO_RENDER_POINTS",
    "TOOL_REF_KNOWLEDGE_SEARCH",
    "TOOL_REF_LOGS_QUERY",
    "TOOL_REF_RESOURCES_FETCH_TEXT",
    "TOOL_REF_TRACES_SUMMARIZE_CONVERSATION",
    "BuiltinToolBackend",
    "BuiltinToolSpec",
    "get_builtin_tool_spec",
    "list_builtin_tool_specs",
]
