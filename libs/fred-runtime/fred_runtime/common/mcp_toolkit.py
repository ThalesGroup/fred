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

import asyncio
import inspect
import logging
from functools import partial
from operator import attrgetter
from typing import Any, Coroutine, List, cast

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field, PrivateAttr

from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.common.kf_base_client import KnowledgeFlowAgentContext

logger = logging.getLogger(__name__)


def mcp_tool_display_name(tool: BaseTool) -> str | None:
    """Return the human-readable title an MCP server declared for a tool, if any.

    MCP tools can carry a human title in their ``annotations`` (e.g.
    ``annotations.title = "Web Search"``). The LangChain MCP adapter preserves tool
    annotations into ``tool.metadata``, so the title survives the conversion and
    reaches us here. We surface it explicitly so the chat trace can show the
    authored label instead of regex-guessing the raw ``mcp__server__web_search``
    name — the title is captured at the MCP boundary, not thrown away.

    Note: the adapter currently drops MCP's newer top-level ``Tool.title`` field and
    only keeps ``annotations.title``; servers that set the annotation title are
    surfaced today, and a future change can also list raw tools for the top-level
    field.
    """
    metadata = getattr(tool, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


class McpToolkit(BaseToolkit):
    tools: List[BaseTool] = Field(default_factory=list, description="(unused)")
    _client: MultiServerMCPClient = PrivateAttr()
    _agent: KnowledgeFlowAgentContext = PrivateAttr()

    def __init__(self, client: MultiServerMCPClient, agent: KnowledgeFlowAgentContext):
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
        """
        Discover raw tools from the MCP client.

        Note: adapter APIs may differ (get_tools vs as_langchain_tools). We try both
        to be resilient across versions.
        """
        # If tools were prefetched and cached by MCPRuntime, use them.
        if self.tools:
            return self.tools

        if hasattr(self._client, "get_tools"):
            try:
                result = self._client.get_tools()  # likely coroutine in new adapters
                if inspect.isawaitable(result):
                    # If we're not in a running loop, we can run it synchronously
                    try:
                        asyncio.get_running_loop()
                        # Running inside event loop; cannot block safely here.
                        logger.warning(
                            "[MCP] _discover_base_tools called inside event loop without prefetched tools; returning empty list."
                        )
                        return []
                    except RuntimeError:
                        # No running loop: safe to run
                        base_tools = asyncio.run(cast(Coroutine[Any, Any, Any], result))
                else:
                    base_tools = result

                if base_tools:
                    logger.info(
                        "[MCP] discovered %d base tools via get_tools()",
                        len(base_tools),
                    )
                return base_tools
            except Exception as e:
                logger.warning("[MCP] tool discovery via get_tools failed: %s", e)

        # LOG 2 (Failure): Tool discovery failed
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
            wrapped.append(ContextAwareTool(tool, context_provider, settings_provider))
        return wrapped
