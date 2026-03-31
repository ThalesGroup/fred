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
Official Knowledge Flow MCP server references for v2 agent authors.

Why this file exists:
- built-in Fred tools already use named constants such as `TOOL_REF_KNOWLEDGE_SEARCH`
- agent authors should not repeat raw MCP server ids such as
  `"mcp-knowledge-flow-fs"` directly inside profiles
- this file exposes the official non-demo Knowledge Flow MCP server ids that
  Fred intentionally supports for agent authors

How to use:
- import `MCPServerRef` and the named constants from
  `agentic_backend.core.agents.v2`
- build profile `mcp_servers` or agent `default_mcp_servers` with those
  constants
- add a new constant here only when Fred core intentionally supports another
  official Knowledge Flow MCP server for authors
- do not treat this file as the full global MCP catalog; it only covers the
  official Knowledge Flow author-facing constants

Example:
- `mcp_servers=(MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_FS),)`

Current official Knowledge Flow MCP servers:
- `MCP_SERVER_KNOWLEDGE_FLOW_FS`: workspace and file operations
- `MCP_SERVER_KNOWLEDGE_FLOW_CORPUS`: corpus administration operations
- `MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS`: OpenSearch monitoring operations
- `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR`: tabular analysis operations
- `MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS`: statistics analysis operations
"""

from __future__ import annotations

from typing import Final

from agentic_backend.core.agents.agent_spec import MCPServerRef

MCP_SERVER_KNOWLEDGE_FLOW_FS: Final[str] = "mcp-knowledge-flow-fs"
"""Filesystem MCP server id used by Custodian-style agents."""

MCP_SERVER_KNOWLEDGE_FLOW_CORPUS: Final[str] = "mcp-knowledge-flow-corpus"
"""Corpus-management MCP server id used by Custodian-style agents."""

MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS: Final[str] = (
    "mcp-knowledge-flow-opensearch-ops"
)
"""OpenSearch operations MCP server id used by Sentinel-style agents."""

MCP_SERVER_KNOWLEDGE_FLOW_TABULAR: Final[str] = "mcp-knowledge-flow-mcp-tabular"
"""Tabular analysis MCP server id used by Tabular-style agents."""

MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS: Final[str] = "mcp-knowledge-flow-statistics"
"""Statistics analysis MCP server id used by Statistics-style agents."""

__all__ = [
    "MCPServerRef",
    "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS",
    "MCP_SERVER_KNOWLEDGE_FLOW_FS",
    "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS",
    "MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS",
    "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR",
]
