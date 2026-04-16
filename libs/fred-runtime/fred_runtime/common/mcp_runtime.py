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
from collections.abc import Awaitable, Iterable
from typing import Any, Callable, List, Optional, cast

from fred_sdk.contracts.context import RuntimeContext as AgentRuntimeContext
from fred_sdk.contracts.models import (
    AgentTuning,
    MCPServerConfiguration,
)
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode

from fred_runtime.common.kf_base_client import KnowledgeFlowAgentContext
from fred_runtime.common.mcp_interceptors import ExpiredTokenRetryInterceptor
from fred_runtime.common.mcp_toolkit import McpToolkit
from fred_runtime.common.mcp_utils import (
    MCPConnectionError,
    get_connected_mcp_client_for_agent,
)
from fred_runtime.common.tool_node_utils import create_mcp_tool_node
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)

MCP_CONNECT_MAX_ATTEMPTS = 3
MCP_CONNECT_RETRY_BASE_DELAY_SECS = 0.5


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    if not client:
        logger.debug("[MCP] close_quietly: No client instance provided.")
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

    def __init__(self, agent: KnowledgeFlowAgentContext):
        """
        Why: bind MCP lifecycle to one agent's tuning + runtime context.
        How: pass an agent context exposing runtime_context and agent_settings.
        Example:
            >>> runtime = MCPRuntime(agent=agent_ctx)
        """
        tuning = agent.agent_settings.tuning
        if tuning is None:
            raise RuntimeError(
                f"Agent {agent.agent_settings.id!r} has no tuning payload; MCP tools cannot be resolved."
            )
        self.tunings: AgentTuning = tuning
        self.agent_instance = agent
        self._agent_id = agent.agent_settings.id
        self.available_servers: List[MCPServerConfiguration] = []
        self.remote_servers: List[MCPServerConfiguration] = []
        self.inprocess_servers: List[MCPServerConfiguration] = []
        mcp_config = get_runtime_context().get_mcp_configuration()
        if mcp_config is None:
            logger.warning(
                "[MCP][%s] Global MCP configuration not available; no MCP tools will be loaded.",
                self._agent_id,
            )
        else:
            for s in self.tunings.mcp_servers:
                server_configuration = mcp_config.get_server(s.id)
                if not server_configuration:
                    logger.warning(
                        "[MCP][%s] Server '%s' not found or disabled in global MCP configuration. Skipping.",
                        self._agent_id,
                        s.id,
                    )
                    continue
                self.available_servers.append(server_configuration)
                transport = (
                    server_configuration.transport or "streamable_http"
                ).lower()
                if transport == "inprocess":
                    self.inprocess_servers.append(server_configuration)
                else:
                    self.remote_servers.append(server_configuration)

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None
        self._inprocess_toolkits: list[Any] = []

        # Lifecycle orchestration so enter/exit happen in the SAME task
        self._lifecycle_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._lifecycle_error: Optional[BaseException] = None

        logger.info(
            "[MCP]agent=%s mcp_servers=%s remote=%s inprocess=%s (enabled only)",
            self._agent_id,
            [s.id for s in self.available_servers],
            [s.id for s in self.remote_servers],
            [s.id for s in self.inprocess_servers],
        )

    # ---------- lifecycle (Token-aware initialization) ----------

    async def init(self) -> None:
        """
        Builds and connects the MCP client using the token available in the
        transient agent's RuntimeContext.

        NOTE: This should only be called once during the agent's async_init.
        """
        if not self.available_servers:
            logger.info(
                "agent=%s init: No MCP server configuration found in tunings. Skipping MCP client connection.",
                self._agent_id,
            )
            # We allow the agent to run, but without MCP tools.
            return

        try:
            self._init_inprocess_toolkits()
        except Exception:
            await self._aclose_inprocess_toolkits()
            raise

        if not self.remote_servers:
            logger.info(
                "[MCP] agent=%s init: Local inprocess toolkits only; no remote MCP connection required.",
                self._agent_id,
            )
            return

        # If already running, just return
        if self._lifecycle_task and not self._lifecycle_task.done():
            return

        runtime_context: AgentRuntimeContext = self.agent_instance.runtime_context
        last_error: BaseException | None = None

        for attempt in range(1, MCP_CONNECT_MAX_ATTEMPTS + 1):
            self._prepare_lifecycle_attempt(runtime_context)
            ready_event = self._ready_event
            if ready_event is None:
                raise RuntimeError("MCPRuntime lifecycle attempt was not prepared.")
            await ready_event.wait()

            if self._lifecycle_error is None:
                return

            last_error = self._lifecycle_error
            await self._await_lifecycle_attempt_completion()

            if (
                attempt >= MCP_CONNECT_MAX_ATTEMPTS
                or not self._is_retryable_connection_error(last_error)
            ):
                await self._aclose_inprocess_toolkits()
                if last_error is not None:
                    raise last_error
                raise RuntimeError(
                    "MCPRuntime lifecycle failed but no lifecycle error was set."
                )

            delay_secs = MCP_CONNECT_RETRY_BASE_DELAY_SECS * (2 ** (attempt - 1))
            logger.warning(
                "[MCP] agent=%s init attempt %d/%d failed with %s. Retrying in %.1fs.",
                self._agent_id,
                attempt,
                MCP_CONNECT_MAX_ATTEMPTS,
                last_error.__class__.__name__,
                delay_secs,
            )
            await asyncio.sleep(delay_secs)

        await self._aclose_inprocess_toolkits()
        if last_error is not None:
            raise last_error

    def _prepare_lifecycle_attempt(self, runtime_context: AgentRuntimeContext) -> None:
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._lifecycle_error = None
        self._lifecycle_task = asyncio.create_task(
            self._run_lifecycle(runtime_context),
            name=f"mcp[{self._agent_id}]",
        )

    async def _await_lifecycle_attempt_completion(self) -> None:
        if self._lifecycle_task is not None:
            try:
                await asyncio.shield(self._lifecycle_task)
            finally:
                self._lifecycle_task = None
        self._stop_event = None
        self._ready_event = None

    @staticmethod
    def _is_retryable_connection_error(error: BaseException) -> bool:
        return isinstance(error, MCPConnectionError)

    async def _run_lifecycle(self, runtime_context: AgentRuntimeContext) -> None:
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
                agent_id=self._agent_id,
                mcp_servers=self.remote_servers,
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
                    self._agent_id,
                    len(tools),
                )
            except Exception:
                logger.warning(
                    "[MCP] agent=%s init: Failed to prefetch tools; toolkit will attempt best-effort discovery later.",
                    self._agent_id,
                    exc_info=True,
                )
            logger.info(
                "[MCP] agent=%s init: Successfully built and connected client.",
                self._agent_id,
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
                self._agent_id,
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
        remote_tools: list[BaseTool] = []
        if self.toolkit:
            # We assume McpToolkit.get_tools() handles policy/role filtering
            remote_tools = self.toolkit.get_tools()
        elif self.remote_servers:
            logger.warning(
                "[MCP] agent=%s get_tools: Toolkit is None. Returning empty list.",
                self._agent_id,
            )
        local_tools = self._get_inprocess_tools()
        return self._dedupe_tools_by_name([*local_tools, *remote_tools])

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
            self._agent_id,
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
        await self._aclose_inprocess_toolkits()
        logger.info(
            "[MCP] agent=%s aclose: MCP shutdown complete.",
            self._agent_id,
        )

    def _init_inprocess_toolkits(self) -> None:
        """
        Initialize in-process MCP toolkits from the configured factory.

        Why this exists:
        - in-process MCP providers are supplied by the host runtime, not hardcoded here

        How to use it:
        - ensure RuntimeContext provides `inprocess_toolkit_factory`
        """
        if self._inprocess_toolkits:
            return
        factory = get_runtime_context().get_inprocess_toolkit_factory()
        if factory is None:
            logger.info(
                "[MCP] agent=%s no inprocess toolkit factory configured; skipping local toolkits.",
                self._agent_id,
            )
            return
        for server in self.inprocess_servers:
            toolkit = factory(server.provider)
            if toolkit is None:
                logger.warning(
                    "[MCP] agent=%s no toolkit built for provider=%s (server=%s)",
                    self._agent_id,
                    server.provider,
                    server.id,
                )
                continue
            self._inprocess_toolkits.append(toolkit)
            logger.info(
                "[MCP] agent=%s enabled inprocess provider=%s via server=%s",
                self._agent_id,
                server.provider,
                server.id,
            )

    def _get_inprocess_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for toolkit in self._inprocess_toolkits:
            provider = getattr(toolkit, "tools", None)
            if not callable(provider):
                logger.warning(
                    "[MCP] agent=%s local toolkit %s has no tools() method",
                    self._agent_id,
                    toolkit.__class__.__name__,
                )
                continue
            try:
                toolkit_tools = cast(Iterable[BaseTool] | None, provider())
                if toolkit_tools:
                    tools.extend(list(toolkit_tools))
            except Exception:
                logger.warning(
                    "[MCP] agent=%s failed loading inprocess tools from %s",
                    self._agent_id,
                    toolkit.__class__.__name__,
                    exc_info=True,
                )
        return tools

    async def _aclose_inprocess_toolkits(self) -> None:
        for toolkit in self._inprocess_toolkits:
            aclose = getattr(toolkit, "aclose", None)
            if callable(aclose):
                try:
                    aclose_coro = cast(Awaitable[Any], aclose())
                    await aclose_coro
                except Exception:
                    logger.warning(
                        "[MCP] agent=%s failed closing inprocess toolkit %s",
                        self._agent_id,
                        toolkit.__class__.__name__,
                        exc_info=True,
                    )
        self._inprocess_toolkits = []

    @staticmethod
    def _dedupe_tools_by_name(tools: list[BaseTool]) -> list[BaseTool]:
        deduped: list[BaseTool] = []
        seen: set[str] = set()
        for tool in tools:
            name = getattr(tool, "name", None)
            if not isinstance(name, str):
                deduped.append(tool)
                continue
            if name in seen:
                logger.warning("[MCP] Duplicate tool name ignored: %s", name)
                continue
            seen.add(name)
            deduped.append(tool)
        return deduped
