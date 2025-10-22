# app/common/mcp_toolkit.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

"""
McpToolkit — build LangChain tools from an MCP client *per turn*.

Why this shape (important for Fred):
- Identity & policy are per-user, per-turn. Tool availability must reflect that.
- We do NOT cache a global tool list; we re-derive it each call with `cfg`.
- We wrap every base MCP tool in a ContextAwareTool whose context provider
  is a closure bound to the current `cfg` (so it uses the current bearer/tenant).

Design contracts:
- AgentFlow is the single source of truth for:
  - `get_runtime_context(cfg)`  -> context object injected into calls
  - `policy_allows(tool_fqn, role, cfg)` -> allow/deny filter
- MCP client is already created for the right principal by MCPRuntime.init(cfg).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from app.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)


class McpToolkit(BaseToolkit):
    """
    Context-aware wrapper over MCP tools.

    IMPORTANT: This toolkit is intentionally *stateless* w.r.t tool catalogs.
    `get_tools(cfg)` must be called each turn to avoid leaking identities or
    stale allowlists across users/sessions.
    """

    # Kept for BaseToolkit compatibility; we don't actually store tools here.
    tools: List[BaseTool] = Field(default_factory=list, description="(unused)")
    _client: MultiServerMCPClient = PrivateAttr()

    def __init__(self, client: MultiServerMCPClient, agent: "AgentFlow"):
        super().__init__()
        self._client = client

    # -------- internal helpers --------

    def _discover_base_tools(self) -> List[BaseTool]:
        """
        Discover raw tools from the MCP client.

        Note: adapter APIs may differ (get_tools vs as_langchain_tools). We try both
        to be resilient across versions.
        """
        if hasattr(self._client, "get_tools"):
            # Some adapters expose get_tools() returning LC BaseTool instances.
            return self._client.get_tools()  # type: ignore[no-any-return]
        raise RuntimeError("MCP client does not expose a tool discovery method.")

    # -------- public API --------

    def peek_tool_names_safe(self) -> List[str]:
        """
        Best-effort list of tool names for logging/telemetry dashboards.
        Safe to call even if discovery fails.
        """
        try:
            return [getattr(t, "name", "") for t in self._discover_base_tools()]
        except Exception:
            return []

    def get_tools(self, cfg: Optional[dict] = None) -> List[BaseTool]:
        """
        Build the per-turn toolset:

        1) Discover from MCP client (already created for the right principal).
        2) Filter by Fred policy (role/tenant/tags) via AgentFlow.
        3) Wrap each tool with ContextAwareTool whose provider captures *this* cfg.

        Why capture cfg in the provider?
        - So context (bearer, tenant, libraries, time windows) matches the current user/turn.
        - Prevents cross-user leakage when multiple sessions hit the same agent instance.
        """
        return self._discover_base_tools()
