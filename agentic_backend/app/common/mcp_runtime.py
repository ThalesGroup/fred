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

# app/common/mcp_runtime.py

from __future__ import annotations

import inspect
import logging
from contextlib import AsyncExitStack
from typing import Any, Callable, Optional

import anyio
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.common.mcp_toolkit import McpToolkit
from app.common.mcp_utils import get_mcp_client_for_agent

logger = logging.getLogger(__name__)


async def _close_mcp_client_quietly(client: Optional[MultiServerMCPClient]) -> None:
    if not client:
        return
    try:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            res = aclose()
            if inspect.isawaitable(res):
                await res
            return
        close = getattr(client, "close", None)
        if callable(close):
            close()
            return
        exit_stack = getattr(client, "exit_stack", None)
        if isinstance(exit_stack, AsyncExitStack):
            await exit_stack.aclose()
    except Exception:
        logger.info("[MCP] old client close ignored.", exc_info=True)


class MCPRuntime:
    """
    Owns the MCP client + toolkit for an agent.

    WHY: Identity is per *end user*, not per process. All public methods accept
    a `cfg` so we can read the *current* bearer from the graph's RunnableConfig.
    Never cache tool lists or transports across users.
    """

    def __init__(self, agent: Any):
        # WHY: AgentFlow is our source of truth for settings + token access.
        self.agent_settings = agent.get_agent_settings()
        self.agent_flow_instance = agent

        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.toolkit: Optional[McpToolkit] = None

        # Serialize refresh() across concurrent callers.
        self._refresh_lock = anyio.Lock()

        # Track which principal the live client was built for (best effort).
        self._principal_cache_key: Optional[str] = None

    # ---------- helpers ----------

    def _principal_from_cfg(self, cfg: Optional[dict]) -> str:
        """
        Extract a stable 'who' key from cfg (e.g., user_id or subject).
        WHY: If cfg's principal changes, we must rebuild transport.
        """
        if not cfg:
            return "anon"
        return (
            cfg.get("user_id") or cfg.get("subject") or cfg.get("principal") or "anon"
        )

    def get_end_user_access_token_from_cfg(self, cfg: Optional[dict]) -> str:
        """Reads the raw access token from the current run config."""
        if not cfg:
            return self.agent_flow_instance.get_end_user_access_token()
        return cfg.get("configurable", {}).get("access_token") or "MISSING_TOKEN"

    def _get_token_provider(self, cfg: Optional[dict]) -> Callable[[], str | None]:
        """
        Returns a callable that fetches the *current* access token when the
        MCP client needs it. It *closes over* the cfg for this turn.
        WHY: Token may rotate; we always read late from AgentFlow/cfg.
        """

        def _provider() -> str | None:
            # Delegate to AgentFlow for uniform token extraction
            return self.get_end_user_access_token_from_cfg(cfg)

        return _provider

    def _snapshot(self, where: str) -> None:
        tools = []
        if self.toolkit:
            # Avoid touching underlying client if not initialized yet
            tools = self.toolkit.peek_tool_names_safe()
        logger.info(
            "[MCP][Snapshot] %s | client=%s toolkit=%s principal=%s tools=[%s]",
            where,
            f"0x{id(self.mcp_client):x}" if self.mcp_client else "None",
            f"0x{id(self.toolkit):x}" if self.toolkit else "None",
            self._principal_cache_key or "None",
            ", ".join(tools),
        )

    # ---------- lifecycle (cfg-aware) ----------

    async def init(self, cfg: Optional[dict] = None) -> None:
        """
        Create a connected MCP client and toolkit bound to *this* cfg's principal.
        SAFE to call multiple times; it will replace an existing client if the
        principal changed.
        """
        principal = self._principal_from_cfg(cfg)
        # If we already have a matching principal, do nothing
        if self.mcp_client and self._principal_cache_key == principal:
            return

        # First init or principal changed -> build fresh
        self.mcp_client = await get_mcp_client_for_agent(
            self.agent_settings,
            access_token_provider=self._get_token_provider(cfg),
        )
        self.toolkit = McpToolkit(
            client=self.mcp_client,
            agent=self.agent_flow_instance,
        )
        self._principal_cache_key = principal
        self._snapshot("init")

    def get_tools(self, cfg: Optional[dict] = None) -> list[BaseTool]:
        """
        Return tools filtered for this turn (role/policy) and wired to a
        transport that resolves the *current* token on use.
        """
        if not self.toolkit:
            return []
        # WHY: policy is role/tenant dependent; pass cfg through.
        return self.toolkit.get_tools(cfg)

    async def aclose(self) -> None:
        await _close_mcp_client_quietly(self.mcp_client)
        self.mcp_client = None
        self.toolkit = None
        self._principal_cache_key = None

    async def refresh(self, cfg: Optional[dict] = None) -> None:
        """
        Rebuild MCP client + toolkit for *this* principal. Used after 401/timeout
        or when policy/tool catalog changed.
        """
        async with self._refresh_lock:
            self._snapshot("refresh/before")
            old = self.mcp_client
            try:
                new_client = await get_mcp_client_for_agent(
                    self.agent_settings,
                    access_token_provider=self._get_token_provider(cfg),
                )
                new_toolkit = McpToolkit(new_client, self.agent_flow_instance)
                self.mcp_client = new_client
                self.toolkit = new_toolkit
                self._principal_cache_key = self._principal_from_cfg(cfg)
                self._snapshot("refresh/after")
            except Exception:
                logger.exception("[MCP] Refresh failed; keeping previous client.")
                return
            finally:
                if old is not self.mcp_client:
                    await _close_mcp_client_quietly(old)
            logger.info("[MCP] Refresh complete.")

    async def refresh_and_bind(self, model, cfg: Optional[dict] = None):
        """
        Refresh MCP for the current principal and return a model bound to a
        fresh per-turn toolset. DO NOT mutate the shared base model.
        """
        await self.refresh(cfg)
        tools = self.get_tools(cfg)
        return model.bind_tools(tools) if hasattr(model, "bind_tools") else model
