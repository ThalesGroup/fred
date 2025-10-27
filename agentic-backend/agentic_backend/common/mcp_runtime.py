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

import inspect
import logging
from contextlib import AsyncExitStack
from typing import Any, List, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agentic_backend.application_context import get_mcp_configuration
from agentic_backend.common.mcp_toolkit import McpToolkit
from agentic_backend.common.mcp_utils import get_connected_mcp_client_for_agent
from agentic_backend.core.agents.agent_spec import AgentTuning, MCPServerConfiguration
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    if not client:
        logger.warning("[MCP] close_quietly: No client instance provided.")
        return

    client_id = f"0x{id(client):x}"
    logger.info("[MCP] client_id=%s close_quietly", client_id)

    try:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            res = aclose()
            if inspect.isawaitable(res):
                await res
            logger.info(
                "[MCP] client_id=%s close_quietly: Closed client via aclose().",
                client_id,
            )
            return

        close = getattr(client, "close", None)
        if callable(close):
            close()
            logger.info(
                "[MCP] client_id=%s close_quietly: Closed client via close().",
                client_id,
            )
            return

        exit_stack = getattr(client, "exit_stack", None)
        if isinstance(exit_stack, AsyncExitStack):
            await exit_stack.aclose()
            logger.info(
                "[MCP] client_id=%s close_quietly: Closed client via AsyncExitStack.",
                client_id,
            )
            return

        # 🟢 LOG 1: No callable close method found
        logger.info(
            "[MCP] client_id=%s close_quietly: Client has no recognized close method.",
            client_id,
        )

    except Exception:
        # 🟢 LOG 1: Close failure
        logger.info(
            "[MCP] client_id=%s close_quietly: Client close ignored.",
            client_id,
            exc_info=True,
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
            server_configuration = get_mcp_configuration().get_server(s.name)
            if not server_configuration:
                raise ValueError(
                    f"[MCP][{self.agent_instance.get_name()}] "
                    f"Server '{s.name}' not found or disabled in global MCP configuration."
                )
            self.available_servers.append(server_configuration)

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None

        logger.info(
            "[MCP]agent=%s mcp_servers=%s ",
            self.agent_instance.get_name(),
            self.available_servers,
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
                self.agent_instance.get_name(),
            )
            # We allow the agent to run, but without MCP tools.
            return

        # 1. Get the RuntimeContext from the agent (guaranteed to be set by the factory)
        runtime_context: RuntimeContext = self.agent_instance.runtime_context
        access_token = runtime_context.access_token

        if not access_token:
            logger.warning(
                "[MCP] agent=%s init: No access_token found in RuntimeContext. Skipping MCP client connection.",
                self.agent_instance.get_name(),
            )
            # We allow the agent to run, but without MCP tools.
            return

        # 2. Define the minimal, token-aware provider function
        def access_token_provider() -> str | None:
            # We can use the agent's live context to support future token refresh
            return self.agent_instance.runtime_context.access_token

        try:
            # 3. Build and connect the client
            new_client = await get_connected_mcp_client_for_agent(
                agent_name=self.agent_instance.get_name(),
                mcp_servers=self.available_servers,
                access_token_provider=access_token_provider,
            )

            # 4. Set final state
            self.toolkit = McpToolkit(
                client=new_client,
                agent=self.agent_instance,
            )
            self.mcp_client = new_client

            logger.info(
                "[MCP] agent=%s init: Successfully built and connected client.",
                self.agent_instance.get_name(),
            )
        except Exception:
            logger.exception(
                "[MCP] agent=%s init: Failed to build and connect client.",
                self.agent_instance.get_name(),
            )
            raise

    def get_tools(self) -> List[BaseTool]:
        """
        Returns the list of tools from the toolkit.
        NOTE: The filtering logic now runs inside the toolkit, not here.
        """
        if not self.toolkit:
            logger.warning(
                "[MCP][%s] get_tools: Toolkit is None. Returning empty list.",
                self.agent_instance.get_name(),
            )
            return []

        # We assume McpToolkit.get_tools() handles policy/role filtering
        return self.toolkit.get_tools()

    async def aclose(self) -> None:
        """
        Shuts down the MCP client associated with this transient runtime.
        """
        logger.info(
            "[MCP][%s] aclose: Shutting down MCPRuntime and closing client.",
            self.agent_instance.get_name(),
        )
        await _close_mcp_client_quietly(self.mcp_client)
        self.mcp_client = None
        self.toolkit = None
        logger.info(
            "[MCP][%s] aclose: MCP shutdown complete.",
            self.agent_instance.get_name(),
        )
