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
from functools import partial
from typing import List, Optional, cast

import anyio
from fred_sdk.contracts.context import RuntimeContext as AgentRuntimeContext
from fred_sdk.contracts.models import (
    MCPServerConfiguration,
)
from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from fred_runtime.common.kf_base_client import KnowledgeFlowAgentContext
from fred_runtime.common.mcp_toolkit import McpToolkit
from fred_runtime.common.mcp_utils import (
    MCPConnectionError,
    get_connected_mcp_client_for_agent,
)
from fred_runtime.common.outbound_credentials import (
    delegation_enabled,
    resolve_credential_provider,
)
from fred_runtime.common.structures import TokenRefreshCallback
from fred_runtime.common.tool_node_utils import create_mcp_tool_node
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support.authority import RunStopError

logger = logging.getLogger(__name__)

MCP_CONNECT_MAX_ATTEMPTS = 3
MCP_CONNECT_RETRY_BASE_DELAY_SECS = 0.5


async def _context_token(runtime_context: AgentRuntimeContext) -> str | None:
    return runtime_context.access_token


async def _get_or_connect_mcp_client(
    *,
    agent_id: str,
    mcp_servers: List[MCPServerConfiguration],
    runtime_context: AgentRuntimeContext,
    credentials,
    refresh_token_cb: TokenRefreshCallback | None,
    refresh_owner: object,
) -> tuple[list[MCPAdapter], list[BaseTool]]:
    # The adapter's callable tools retain their client's authentication object.
    # A cross-run tool cache would retain a previous run's credential provider.
    return await get_connected_mcp_client_for_agent(
        agent_id=agent_id,
        mcp_servers=mcp_servers,
        runtime_context=runtime_context,
        credentials=credentials,
        refresh_token_cb=refresh_token_cb,
        refresh_owner=refresh_owner,
    )


async def _close_mcp_client_quietly(client: Optional[list[MCPAdapter]]) -> None:
    if not client:
        logger.debug("[MCP] event=connection_close outcome=skipped reason=no_client")
        return

    logger.info("[MCP] event=connection_close outcome=started")

    # MCPAdapter opens a client per listing or invocation; no context remains open.
    logger.debug("[MCP] event=connection_close outcome=succeeded")


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
        # The active MCP server refs come from the settings, not from the tuning
        # payload: the MCP tuning trio (`mcp_servers` / `selected_mcp_server_ids`
        # / `mcp_config_values`) was retired at Tier 1 (#1978). Agent assembly
        # derives `active_mcp_servers` from the agent's selected `mcp:<id>`
        # capabilities (see `fred_runtime.app.agent_app`).
        active_servers = getattr(agent.agent_settings, "active_mcp_servers", ())
        self.agent_instance = agent
        self._agent_id = agent.agent_settings.id
        self._confined_logs = delegation_enabled()
        self.available_servers: List[MCPServerConfiguration] = []
        mcp_config = get_runtime_context().get_mcp_configuration()
        if mcp_config is None:
            if self._confined_logs:
                logger.warning(
                    "[MCP] event=runtime_init outcome=skipped "
                    "reason=missing_configuration"
                )
            else:
                logger.warning(
                    "[MCP][%s] Global MCP configuration not available; no MCP "
                    "tools will be loaded.",
                    self._agent_id,
                )
        else:
            for s in active_servers:
                server_configuration = mcp_config.get_server(s.id)
                if not server_configuration:
                    if self._confined_logs:
                        logger.warning(
                            "[MCP] event=server_activation outcome=skipped "
                            "reason=unavailable"
                        )
                    else:
                        logger.warning(
                            "[MCP][%s] Server '%s' not found or disabled in global "
                            "MCP configuration. Skipping.",
                            self._agent_id,
                            s.id,
                        )
                    continue
                self.available_servers.append(server_configuration)

        self.mcp_client: Optional[list[MCPAdapter]] = None
        self.toolkit: Optional[McpToolkit] = None

        # Lifecycle orchestration so enter/exit happen in the SAME task
        self._lifecycle_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._lifecycle_error: Optional[BaseException] = None
        self._close_task: asyncio.Task[None] | None = None

        if self._confined_logs:
            logger.info("[MCP] event=server_activation outcome=resolved")
        else:
            logger.info(
                "[MCP]agent=%s mcp_servers=%s (enabled only)",
                self._agent_id,
                [s.id for s in self.available_servers],
            )

    # ---------- lifecycle (Token-aware initialization) ----------

    async def init(self) -> None:
        """
        Builds and connects the MCP client using the token available in the
        transient agent's RuntimeContext.

        NOTE: This should only be called once during the agent's async_init.
        """
        if not self.available_servers:
            if self._confined_logs:
                logger.info(
                    "[MCP] event=runtime_init outcome=skipped reason=no_servers"
                )
            else:
                logger.info(
                    "agent=%s init: No MCP server configuration found in tunings. "
                    "Skipping MCP client connection.",
                    self._agent_id,
                )
            # We allow the agent to run, but without MCP tools.
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

            last_error = self._lifecycle_error
            if last_error is None:
                return

            await self._await_lifecycle_attempt_completion()

            if isinstance(last_error, RunStopError):
                # The platform ended this run. Asking again is asking for what
                # was just refused, under the platform's own identity.
                raise last_error

            if (
                attempt >= MCP_CONNECT_MAX_ATTEMPTS
                or not self._is_retryable_connection_error(last_error)
            ):
                raise last_error

            delay_secs = MCP_CONNECT_RETRY_BASE_DELAY_SECS * (2 ** (attempt - 1))
            if self._confined_logs:
                logger.warning(
                    "[MCP] event=runtime_init outcome=retrying reason=connection_error"
                )
            else:
                logger.warning(
                    "[MCP] agent=%s init attempt %d/%d failed with %s. "
                    "Retrying in %.1fs.",
                    self._agent_id,
                    attempt,
                    MCP_CONNECT_MAX_ATTEMPTS,
                    last_error.__class__.__name__,
                    delay_secs,
                )
            await asyncio.sleep(delay_secs)

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
            await asyncio.shield(self._lifecycle_task)
            self._lifecycle_task = None
        self._stop_event = None
        self._ready_event = None

    @staticmethod
    def _is_retryable_connection_error(error: BaseException) -> bool:
        return isinstance(error, MCPConnectionError)

    async def _run_lifecycle(self, runtime_context: AgentRuntimeContext) -> None:
        """
        Discover tools through MCPAdapter for this run's credential provider.
        """
        try:
            refresh_cb_attr = getattr(
                self.agent_instance, "refresh_user_access_token", None
            )
            refresh_cb: TokenRefreshCallback | None = (
                cast(TokenRefreshCallback, refresh_cb_attr)
                if callable(refresh_cb_attr)
                else None
            )
            provider = resolve_credential_provider(
                holder=self.agent_instance,
                person_token_getter=partial(_context_token, runtime_context),
            )
            new_client, tools = await _get_or_connect_mcp_client(
                agent_id=self._agent_id,
                mcp_servers=self.available_servers,
                runtime_context=runtime_context,
                credentials=provider,
                refresh_token_cb=refresh_cb,
                refresh_owner=self.agent_instance,
            )
            self.mcp_client = new_client
            # `tools` were already fetched (per server) while connecting/validating
            # above — reuse them instead of paying for a second get_tools() round
            # trip against every server on every single turn.
            self.toolkit = McpToolkit(client=new_client, agent=self.agent_instance)
            self.toolkit.tools = tools
            if self._confined_logs:
                logger.info("[MCP] event=runtime_init outcome=connected")
                logger.info("[MCP] event=runtime_init outcome=succeeded")
            else:
                logger.info(
                    "[MCP] agent=%s init: Connected and cached %d tools.",
                    self._agent_id,
                    len(tools),
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

        except RunStopError as stop:
            # The reason is what an operator can act on; the chained traceback
            # would carry the refused endpoint, grant and all.
            self._lifecycle_error = stop
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            logger.warning(
                "[MCP] event=runtime_init outcome=stopped reason=%s",
                stop.reason,
            )
        except Exception as e:
            # Propagate init error to caller
            self._lifecycle_error = e
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            if self._confined_logs:
                logger.error(
                    "[MCP] event=runtime_init outcome=failed reason=unexpected_error"
                )
            else:
                logger.exception(
                    "[MCP] agent=%s lifecycle error during init.", self._agent_id
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
        elif self.available_servers:
            logger.warning(
                "[MCP] event=tool_loading outcome=skipped reason=runtime_unavailable"
            )
        return self._dedupe_tools_by_name(remote_tools)

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
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_owned())
        close_task = self._close_task
        interrupted = False
        with anyio.CancelScope(shield=True):
            while not close_task.done():
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError:
                    interrupted = True
                    current = asyncio.current_task()
                    if current is not None:
                        current.uncancel()
            close_task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _close_owned(self) -> None:
        logger.debug("[MCP] event=runtime_close outcome=started")
        # If lifecycle task exists, signal and await it to close contexts safely
        if self._lifecycle_task:
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()
            try:
                await self._lifecycle_task
            finally:
                if self._lifecycle_task.done():
                    self._lifecycle_task = None
                    self._stop_event = None
                    self._ready_event = None
                    self._lifecycle_error = None
        else:
            await _close_mcp_client_quietly(self.mcp_client)
            self.mcp_client = None
            self.toolkit = None
        logger.info("[MCP] event=runtime_close outcome=succeeded")

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
                logger.warning(
                    "[MCP] event=tool_deduplication outcome=skipped "
                    "reason=duplicate_name"
                )
                continue
            seen.add(name)
            deduped.append(tool)
        return deduped
