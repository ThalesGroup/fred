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


"""
McpToolkit — build LangChain tools from an MCP client *per turn*.

... [rest of docstring truncated for brevity] ...
"""

from __future__ import annotations

import logging
from functools import partial
from operator import attrgetter
from typing import List

from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool, BaseToolkit
from pydantic import Field, PrivateAttr

from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.common.kf_base_client import KnowledgeFlowAgentContext

logger = logging.getLogger(__name__)


class McpToolkit(BaseToolkit):
    tools: List[BaseTool] = Field(default_factory=list, description="(unused)")
    _client: list[MCPAdapter] = PrivateAttr()
    _agent: KnowledgeFlowAgentContext = PrivateAttr()

    def __init__(self, client: list[MCPAdapter], agent: KnowledgeFlowAgentContext):
        """
        Why: bind one MCP client to a runtime agent context for per-turn tools.
        How: pass the MCP client plus an agent context with runtime+settings data.
        Example:
            >>> toolkit = McpToolkit(client=mcp_client, agent=agent_ctx)
        """
        super().__init__()
        self._client = client
        self._agent = agent
        # 🟢 LOG 1: Initialization success
        logger.info(
            "[MCP] initialized. Client: %s, Agent: %s",
            type(client).__name__,
            type(agent).__name__,
        )

    # -------- internal helpers --------

    def _discover_base_tools(self) -> List[BaseTool]:
        """Return the tools discovered during this runtime's initialization."""
        return self.tools

    # -------- public API --------

    def peek_tool_names_safe(self) -> List[str]:
        """
        Best-effort list of tool names for logging/telemetry dashboards.
        Safe to call even if discovery fails.
        """
        try:
            names = [getattr(t, "name", "") for t in self._discover_base_tools()]
            # 🟢 LOG 3: Peek successful
            logger.info("[MCP] peeked tool names: %s", names)
            return names
        except Exception as e:
            # 🟢 LOG 3 (Failure): Peek failed
            logger.warning("[MCP] peek failed during tool discovery: %s", e)
            return []

    def get_tools(
        self,
    ) -> List[BaseTool]:  # ❌ Removed: cfg: Optional[Mapping[str, Any]] = None
        """
        Build the per-turn toolset: Discover, Filter, and Wrap, using the
        agent's RuntimeContext for context-specific filtering.

        Why: MCP tools must be filtered and wrapped with per-agent context.
        How: use the agent's runtime_context + settings when wrapping tools.
        Example:
            >>> tools = toolkit.get_tools()
        """
        base_tools = self._discover_base_tools()
        context_provider = partial(attrgetter("runtime_context"), self._agent)
        settings_provider = partial(attrgetter("agent_settings"), self._agent)
        wrapped: List[BaseTool] = []
        for tool in base_tools:
            if isinstance(tool, ContextAwareTool):
                wrapped.append(tool)
                continue
            wrapped.append(
                ContextAwareTool(
                    tool, context_provider, settings_provider, agent_context=self._agent
                )
            )
        return wrapped
