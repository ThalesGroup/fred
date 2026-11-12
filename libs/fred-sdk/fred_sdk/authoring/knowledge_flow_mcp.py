# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Stable native Tabular capability reference.

Use MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR) in template/profile
requirements. Control Plane admits the internal Knowledge Flow destination under
the ordinary capability policy. This is not an endpoint catalogue.
"""

from typing import Final

from ..contracts.models import MCPServerRef

MCP_SERVER_KNOWLEDGE_FLOW_TABULAR: Final[str] = "mcp-knowledge-flow-mcp-tabular"

__all__ = ["MCPServerRef", "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR"]
