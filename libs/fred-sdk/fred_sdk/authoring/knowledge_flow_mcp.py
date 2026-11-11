# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Stable author reference for Tabular's embedded business contribution.

Use MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR) in template/profile
requirements. Control Plane resolves its declared service dependency to the
centrally published and authorized connection. This is not an endpoint catalog.
"""

from typing import Final

from ..contracts.models import MCPServerRef

MCP_SERVER_KNOWLEDGE_FLOW_TABULAR: Final[str] = "mcp-knowledge-flow-mcp-tabular"

__all__ = ["MCPServerRef", "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR"]
