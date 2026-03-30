# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Agent-author-facing v2 authoring surface.

Why this package exists:
- keep the v2 package root focused on the public facade instead of loose files
- group the helpers that an agent author reads directly: Python tool authoring,
  inspection entrypoints, and named MCP server references

Who this package is for:
- `agent author` means an SDK consumer who defines a new Fred agent, profile,
  or small Python-authored toolset
- `Fred developer` means a maintainer of the SDK/runtime itself
- this package is primarily for the `agent author`
- Fred developers may read it too, but they should treat it as the public
  authoring surface, not as the place for runtime internals

How to use it:
- import `ReActAgent`, `tool`, and related helper types from this package when
  authoring small v2 agents in Python
- define tool inputs with normal Python type annotations; `@tool(...)` will
  usually infer the Pydantic input schema for you from the function signature
- import `inspect_agent` for non-activating inspection
- import `MCPServerRef` and `MCP_SERVER_KNOWLEDGE_FLOW_*` constants for
  author-facing default MCP server declarations
- if you intentionally want optional Fred-specific shortcuts, access them
  through `context.helpers` inside a tool

Example:
- `from agentic_backend.core.agents.v2.authoring import ReActAgent, tool`
"""

from .api import (
    ArtifactPublicationError,
    ModelInvocationError,
    ReActAgent,
    ResourceFetchError,
    ResourceNotFoundError,
    ToolContext,
    ToolInvocationError,
    ToolOutput,
    UIHints,
    prompt_md,
    tool,
    ui_field,
)
from .inspection import inspect_agent
from .knowledge_flow_mcp import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS,
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCPServerRef,
)

__all__ = [
    "ArtifactPublicationError",
    "MCPServerRef",
    "ModelInvocationError",
    "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS",
    "MCP_SERVER_KNOWLEDGE_FLOW_FS",
    "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS",
    "MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS",
    "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR",
    "ReActAgent",
    "ResourceFetchError",
    "ResourceNotFoundError",
    "ToolContext",
    "ToolInvocationError",
    "ToolOutput",
    "UIHints",
    "inspect_agent",
    "prompt_md",
    "tool",
    "ui_field",
]
