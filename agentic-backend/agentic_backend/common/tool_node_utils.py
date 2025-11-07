# Copyright Thales 2025
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

from __future__ import annotations

import logging
from typing import Sequence

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)


def friendly_mcp_tool_error_handler(e: Exception) -> str:
    """
    Convert low-level tool exceptions into concise, human-friendly errors.

    Focuses on MCP transport/connectivity failures so users understand that
    the MCP server is down/unreachable instead of seeing a stack trace.
    """
    # Try to detect common httpx/httpcore connection failures without hard dependency
    httpx = None
    httpcore = None
    try:  # pragma: no cover - best-effort import
        import httpx as _httpx  # type: ignore

        httpx = _httpx
    except Exception:  # noqa: BLE001
        logger.exception("Failed to import httpx")
        pass
    try:  # pragma: no cover - best-effort import
        import httpcore as _httpcore  # type: ignore

        httpcore = _httpcore
    except Exception:  # noqa: BLE001
        logger.exception("Failed to import httpcore")
        pass

    conn_like: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)
    if httpx is not None:
        conn_like = conn_like + (
            getattr(httpx, "ConnectError", Exception),
            getattr(httpx, "ReadTimeout", Exception),
            getattr(httpx, "WriteTimeout", Exception),
            getattr(httpx, "PoolTimeout", Exception),
        )
    if httpcore is not None:
        conn_like = conn_like + (getattr(httpcore, "ConnectError", Exception),)

    if isinstance(e, conn_like):
        return (
            "The MCP server appears unreachable. Please ensure it is running "
            "and accessible, then try again."
        )

    return (
        "A tool error occurred while using the MCP integration. "
        "Please try again or contact support if it persists."
    )


def create_mcp_tool_node(tools: Sequence[BaseTool]) -> ToolNode:
    """
    Factory for ToolNode with standardized MCP-friendly error handling.
    This ensures consistent user experience across all MCP-based agents.
    Typically if a MCP server is down or unreachable, users see a clear message
    instead of a raw stack trace.
    """
    return ToolNode(tools=tools, handle_tool_errors=friendly_mcp_tool_error_handler)
