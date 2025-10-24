# app/common/mcp_toolkit.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

"""
McpToolkit — build LangChain tools from an MCP client *per turn*.

... [rest of docstring truncated for brevity] ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field, PrivateAttr

from app.common.mcp_client_wrapper import RefreshableTool

if TYPE_CHECKING:
    from app.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)


class McpToolkit(BaseToolkit):
    """
    Context-aware wrapper over MCP tools.

    ... [rest of docstring truncated for brevity] ...
    """

    # Kept for BaseToolkit compatibility; we don't actually store tools here.
    tools: List[BaseTool] = Field(default_factory=list, description="(unused)")
    _client: MultiServerMCPClient = PrivateAttr()
    _agent: "AgentFlow" = PrivateAttr()

    def __init__(self, client: MultiServerMCPClient, agent: "AgentFlow"):
        super().__init__()
        self._client = client
        self._agent = agent
        # 🟢 LOG 1: Initialization success
        logger.info(
            "McpToolkit initialized. Client: %s, Agent: %s",
            type(client).__name__,
            type(agent).__name__,
        )

    # -------- internal helpers --------

    def _discover_base_tools(self) -> List[BaseTool]:
        """
        Discover raw tools from the MCP client.

        Note: adapter APIs may differ (get_tools vs as_langchain_tools). We try both
        to be resilient across versions.
        """
        if hasattr(self._client, "get_tools"):
            base_tools = self._client.get_tools()  # type: ignore[no-any-return]
            # 🟢 LOG 2: Discovery success
            logger.info(
                "McpToolkit discovered %d base tools via get_tools()",
                len(base_tools),
            )
            return base_tools

        # 🟢 LOG 2 (Failure): Tool discovery failed
        logger.error("MCP client does not expose a tool discovery method.")
        raise RuntimeError("MCP client does not expose a tool discovery method.")

    # -------- public API --------

    def peek_tool_names_safe(self) -> List[str]:
        """
        Best-effort list of tool names for logging/telemetry dashboards.
        Safe to call even if discovery fails.
        """
        try:
            names = [getattr(t, "name", "") for t in self._discover_base_tools()]
            # 🟢 LOG 3: Peek successful
            logger.info("McpToolkit peeked tool names: %s", names)
            return names
        except Exception as e:
            # 🟢 LOG 3 (Failure): Peek failed
            logger.warning("McpToolkit peek failed during tool discovery: %s", e)
            return []

    def get_tools(
        self,
    ) -> List[BaseTool]:  # ❌ Removed: cfg: Optional[Mapping[str, Any]] = None
        """
        Build the per-turn toolset: Discover, Filter, and Wrap, using the
        agent's RuntimeContext for context-specific filtering.
        """
        logger.info("McpToolkit starting per-turn tool building.")

        base_tools = self._discover_base_tools()

        # Example of context-aware filtering:
        # if runtime_context.search_policy == "restricted":
        #    allowed_tools = [t for t in base_tools if "search" not in t.name]
        # else:
        allowed_tools = base_tools

        # 2. WRAP each allowed tool with the RefreshableTool
        wrapped_tools: List[BaseTool] = []
        for tool in allowed_tools:
            # Pass the raw tool and the agent_flow instance
            wrapped_tools.append(
                RefreshableTool(underlying_tool=tool, agent_flow=self._agent)
            )
        wrapped_tool_names = [t.name for t in wrapped_tools if hasattr(t, "name")]
        # 🟢 LOG 6: Final result
        logger.info(
            "McpToolkit returning %d wrapped tools: %s",
            len(wrapped_tools),
            ", ".join(wrapped_tool_names),
        )

        # return wrapped_tools
        return allowed_tools
