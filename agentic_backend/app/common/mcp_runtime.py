# app/common/mcp_runtime.py

from __future__ import annotations

import inspect
import logging
from contextlib import AsyncExitStack
from typing import Any, List, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.common.mcp_toolkit import McpToolkit
from app.common.mcp_utils import get_connected_mcp_client_for_agent
from app.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    if not client:
        # 🟢 LOG 1: No client to close
        logger.info("[MCP] close_quietly: No client instance provided.")
        return

    client_id = f"0x{id(client):x}"
    # 🟢 LOG 1: Starting client close attempt
    logger.info("[MCP] close_quietly: Attempting to close client %s...", client_id)

    try:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            res = aclose()
            if inspect.isawaitable(res):
                await res
            logger.info(
                "[MCP] close_quietly: Closed client %s via aclose().", client_id
            )
            return

        close = getattr(client, "close", None)
        if callable(close):
            close()
            logger.info("[MCP] close_quietly: Closed client %s via close().", client_id)
            return

        exit_stack = getattr(client, "exit_stack", None)
        if isinstance(exit_stack, AsyncExitStack):
            await exit_stack.aclose()
            logger.info(
                "[MCP] close_quietly: Closed client %s via AsyncExitStack.", client_id
            )
            return

        # 🟢 LOG 1: No callable close method found
        logger.info(
            "[MCP] close_quietly: Client %s has no recognized close method.", client_id
        )

    except Exception:
        # 🟢 LOG 1: Close failure
        logger.info(
            "[MCP] close_quietly: Client %s close ignored.", client_id, exc_info=True
        )


class MCPRuntime:
    """
    Minimal owner of the MCP client and toolkit for a transient, per-request agent.
    Relies on the agent's RuntimeContext for user authentication tokens.
    """

    def __init__(self, agent: Any):
        # WHY: AgentFlow is the source of truth for settings + context access.
        self.agent_settings = agent.get_agent_settings()
        self.agent_flow_instance = agent  # The transient AgentFlow instance

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None

        logger.info(
            "[MCPRuntime] Initialized minimal runtime for agent %s.",
            self.agent_settings.name,
        )

    # ---------- lifecycle (Token-aware initialization) ----------

    async def init(self) -> None:
        """
        Builds and connects the MCP client using the token available in the
        transient agent's RuntimeContext.

        NOTE: This should only be called once during the agent's async_init.
        """
        # 1. Get the RuntimeContext from the agent (guaranteed to be set by the factory)
        runtime_context: RuntimeContext = self.agent_flow_instance.runtime_context

        access_token = runtime_context.access_token

        if not access_token:
            logger.warning(
                "[MCP] init: No access_token found in RuntimeContext. Skipping MCP client connection."
            )
            # We allow the agent to run, but without MCP tools.
            return

        # 2. Define the minimal, token-aware provider function
        def access_token_provider() -> str | None:
            # We can use the agent's live context to support future token refresh
            return self.agent_flow_instance.runtime_context.access_token

        try:
            # 3. Build and connect the client
            new_client = await get_connected_mcp_client_for_agent(
                self.agent_settings,
                access_token_provider=access_token_provider,
            )

            # 4. Set final state
            self.toolkit = McpToolkit(
                client=new_client,
                agent=self.agent_flow_instance,
            )
            self.mcp_client = new_client

            logger.info(
                "[MCP] init: Successfully built and connected client for agent %s.",
                self.agent_settings.name,
            )
        except Exception:
            logger.exception(
                "[MCP] init: Failed to build and connect client for agent %s.",
                self.agent_settings.name,
            )
            raise

    def get_tools(self) -> List[BaseTool]:
        """
        Returns the list of tools from the toolkit.
        NOTE: The filtering logic now runs inside the toolkit, not here.
        """
        if not self.toolkit:
            logger.warning("[MCP] get_tools: Toolkit is None. Returning empty list.")
            return []

        # We assume McpToolkit.get_tools() handles policy/role filtering
        return self.toolkit.get_tools()

    async def aclose(self) -> None:
        """
        Shuts down the MCP client associated with this transient runtime.
        """
        logger.info("[MCP] aclose: Shutting down MCPRuntime and closing client.")
        await _close_mcp_client_quietly(self.mcp_client)
        self.mcp_client = None
        self.toolkit = None
        logger.info("[MCP] aclose: Shutdown complete.")
