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

# agentic_backend/common/mcp_runtime.py

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List, Optional, cast

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode

from agentic_backend.application_context import get_mcp_configuration
from agentic_backend.common.mcp_interceptors import ExpiredTokenRetryInterceptor
from agentic_backend.common.mcp_toolkit import McpToolkit
from agentic_backend.common.mcp_utils import get_connected_mcp_client_for_agent
from agentic_backend.common.tool_node_utils import create_mcp_tool_node
from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerConfiguration
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    if not client:
        logger.warning("[MCP] close_quietly: No client instance provided.")
        return

    client_id = f"0x{id(client):x}"
    logger.info("[MCP] client_id=%s close_quietly", client_id)

    # Newer MultiServerMCPClient does not maintain persistent resources; sessions are
    # opened/closed per call. Nothing to close at the client level.
    logger.debug(
        "[MCP] client_id=%s close_quietly: nothing to close on client.", client_id
    )


class MCPRuntime:
    """
    This class manages the lifecycle of an MCP client and toolkit for your agent.
    Agents are expected to instantiate one MCPRuntime during their async_init(),
    call its init() method to connect the client, and aclose() during shutdown.
    """

    def __init__(self, agent: Any):
        # WHY: AgentFlow is the source of truth for settings + context access.
        self.tunings: AgentTuning = agent.get_agent_tunings()
        self.agent_instance = agent
        self.available_servers: List[MCPServerConfiguration] = []
        for s in self.tunings.mcp_servers:
            server_configuration = get_mcp_configuration().get_server(s.id)
            if not server_configuration:
                logger.warning(
                    "[MCP][%s] Server '%s' not found or disabled in global MCP configuration. Skipping.",
                    self.agent_instance.get_id(),
                    s.id,
                )
                continue
            self.available_servers.append(server_configuration)

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None

        # Lifecycle orchestration so enter/exit happen in the SAME task
        self._lifecycle_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._lifecycle_error: Optional[BaseException] = None

        logger.info(
            "[MCP]agent=%s mcp_servers=%s (enabled only)",
            self.agent_instance.get_id(),
            [s.id for s in self.available_servers],
        )

    # ---------- lifecycle (Token-aware initialization) ----------

    async def init(self) -> None:
        """
        Builds and connects the MCP client using the token available in the
        transient agent's RuntimeContext.

        NOTE: This should only be called once during the agent's async_init.
        """
        if not self.available_servers or len(self.available_servers) == 0:
            logger.info(
                "agent=%s init: No MCP server configuration found in tunings. Skipping MCP client connection.",
                self.agent_instance.get_id(),
            )
            # We allow the agent to run, but without MCP tools.
            return

        # If already running, just return
        if self._lifecycle_task and not self._lifecycle_task.done():
            return

        # 1) Prepare lifecycle signals
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._lifecycle_error = None

        # 2) Launch lifecycle task that opens and later closes in the same task
        runtime_context: RuntimeContext = self.agent_instance.runtime_context
        self._lifecycle_task = asyncio.create_task(
            self._run_lifecycle(runtime_context),
            name=f"mcp[{self.agent_instance.get_id()}]",
        )

        # 3) Wait until connected or error
        await self._ready_event.wait()
        if self._lifecycle_error:
            raise self._lifecycle_error

    async def _run_lifecycle(self, runtime_context: RuntimeContext) -> None:
        """
        Create and connect the MultiServerMCPClient in THIS task and close it
        from the same task on stop signal to avoid AnyIO cancel-scope mismatches.
        """
        try:
            interceptors = []
            refresh_cb_attr = getattr(
                self.agent_instance, "refresh_user_access_token", None
            )
            refresh_cb: Callable[[], str] | None = (
                cast(Callable[[], str], refresh_cb_attr)
                if callable(refresh_cb_attr)
                else None
            )
            if refresh_cb:
                interceptors.append(ExpiredTokenRetryInterceptor(refresh_cb))

            new_client = await get_connected_mcp_client_for_agent(
                agent_id=self.agent_instance.get_id(),
                mcp_servers=self.available_servers,
                runtime_context=runtime_context,
                tool_interceptors=interceptors,
            )
            self.mcp_client = new_client
            self.toolkit = McpToolkit(client=new_client, agent=self.agent_instance)
            try:
                # Pre-fetch tools once (async) and cache in toolkit for sync callers
                tools = await new_client.get_tools()
                self.toolkit.tools = tools
                logger.info(
                    "[MCP] agent=%s init: Prefetched and cached %d tools.",
                    self.agent_instance.get_id(),
                    len(tools),
                )
            except Exception:
                logger.warning(
                    "[MCP] agent=%s init: Failed to prefetch tools; toolkit will attempt best-effort discovery later.",
                    self.agent_instance.get_id(),
                    exc_info=True,
                )
            logger.info(
                "[MCP] agent=%s init: Successfully built and connected client.",
                self.agent_instance.get_id(),
            )
            # Signal readiness
            if self._ready_event:
                self._ready_event.set()

            # Wait for stop
            assert self._stop_event is not None
            await self._stop_event.wait()

        except BaseException as e:
            # Propagate init error to caller
            self._lifecycle_error = e
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            logger.exception(
                "[MCP] agent=%s lifecycle error during init.",
                self.agent_instance.get_id(),
            )
        finally:
            # Close client in the SAME task that opened it
            try:
                await _close_mcp_client_quietly(self.mcp_client)
            finally:
                self.mcp_client = None
                self.toolkit = None

    def get_tools(self) -> List[BaseTool]:
        """
        Returns the list of tools from the toolkit.
        NOTE: The filtering logic now runs inside the toolkit, not here.
        """
        if not self.toolkit:
            logger.warning(
                "[MCP] agent=%s get_tools: Toolkit is None. Returning empty list.",
                self.agent_instance.get_id(),
            )
            return []

        # We assume McpToolkit.get_tools() handles policy/role filtering
        return self.toolkit.get_tools()

    def get_tool_nodes(self) -> ToolNode:
        """
        Returns a ToolNode wrapping the MCP tools for use in a StateGraph.
        This API uses the shared factory with standardized MCP-friendly error handling.
        The benefit is to make your agent's tool node send clear, human-friendly
        error messages to the end user if the MCP server is down or unreachable instead of
        raw stack traces.
        """
        tools = self.get_tools()
        return create_mcp_tool_node(tools)

    async def aclose(self) -> None:
        """
        Shuts down the MCP client associated with this transient runtime.
        """
        logger.debug(
            "[MCP] agent=%s aclose: Shutting down MCPRuntime and closing client.",
            self.agent_instance.get_id(),
        )
        # If lifecycle task exists, signal and await it to close contexts safely
        if self._lifecycle_task:
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()
            try:
                await asyncio.shield(self._lifecycle_task)
            finally:
                self._lifecycle_task = None
                self._stop_event = None
                self._ready_event = None
                self._lifecycle_error = None
        else:
            # Fallback (shouldn’t normally happen): close inline
            await _close_mcp_client_quietly(self.mcp_client)
            self.mcp_client = None
            self.toolkit = None
        logger.info(
            "[MCP] agent=%s aclose: MCP shutdown complete.",
            self.agent_instance.get_id(),
        )
