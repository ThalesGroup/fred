# app/agents/sentinel/sentinel.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from pydantic import TypeAdapter

from app.common.mcp_utils import get_mcp_client_for_agent

from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.flow import AgentFlow
from app.core.model.model_factory import get_model

from app.agents.sentinel.sentinel_toolkit import SentinelToolkit

logger = logging.getLogger(__name__)


class SentinelExpert(AgentFlow):
    """
    Fred rationale:
    - Sentinel relies on MCP tools (kpi.*, os.*). Tokens for those HTTP calls can expire.
    - To avoid “first-call 401” after a user returns, we run a *very cheap* MCP preflight
      at the start of every reasoning turn. This forces the auth layer to mint/refresh an
      access token *before* any real tool is invoked by ToolNode.
    - If a 401 still slips through, our tool wrappers / ToolNode logging will show it.
    """

    name: str
    role: str
    nickname: str
    description: str
    icon: str = "ops_agent"
    categories: list[str] = []
    tag: str = "ops"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.nickname = agent_settings.nickname or agent_settings.name
        self.role = agent_settings.role
        self.description = agent_settings.description
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.model = None
        self.mcp_client = None
        self.toolkit = None
        self.categories = agent_settings.categories or ["ops", "monitoring"]
        self.tag = agent_settings.tag or "ops"
        self.base_prompt = self._generate_prompt()

        # Generic adapter that tolerates list/dict tool payloads (we won't enforce a single schema)
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

    async def async_init(self):
        # LLM
        self.model = get_model(self.agent_settings.model)

        # MCP: connect to all servers configured for this agent (should include /mcp-kpi and /mcp-opensearch-ops)
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)

        # Toolkit (context-aware wrapper over kpi.* and os.* tools)
        self.toolkit = SentinelToolkit(
            self.mcp_client, lambda: self.get_runtime_context()
        )

        # Bind tools
        self.model = self.model.bind_tools(self.toolkit.get_tools())
        self._snapshot_tools("async_init/bound") 
        # Build graph
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
            toolkit=self.toolkit,
        )

        # --- helper: very cheap preflight to mint/refresh token --------------------------
    def _find_tool(self, name: str):
        if not self.toolkit:
            return None
        for t in self.toolkit.get_tools():
            if getattr(t, "name", None) == name:
                return t
        return None

    def _snapshot_tools(self, where: str) -> None:
        try:
            tools = self.toolkit.get_tools() if self.toolkit else []
            summary = ", ".join(f"{getattr(t, 'name', '?')}@{id(t):x}" for t in tools)
            logger.info(
                "[MCP][Snapshot] %s | client=%s toolkit=%s tools=[%s]",
                where,
                f"0x{id(self.mcp_client):x}" if self.mcp_client else "None",
                f"0x{id(self.toolkit):x}" if self.toolkit else "None",
                summary,
            )
        except Exception:
            logger.info("[MCP][Snapshot] %s | <failed to list tools>", where, exc_info=True)

    async def _refresh_mcp_session(self) -> None:
        logger.info("[MCP] Refreshing MCP session...")
        self._snapshot_tools("refresh/before") 
        old = self.mcp_client
        self.mcp_client = await get_mcp_client_for_agent(self.agent_settings)
        self.toolkit = SentinelToolkit(self.mcp_client, lambda: self.get_runtime_context())
        self.model = self.model.bind_tools(self.toolkit.get_tools())
        self._snapshot_tools("refresh/after")
        logger.info("[MCP] Refresh complete.")
        try:
            if old:
                close_fn = getattr(old, "aclose", None)
                if callable(close_fn):
                    await close_fn()
                else:
                    close_fn = getattr(old, "close", None)
                    if callable(close_fn):
                        close_fn()
        except Exception:
            logger.info("[MCP] old client close ignored.", exc_info=True)

    logger.info("[MCP] Refresh complete.")
    async def _preflight_mcp(self, timeout_seconds: float = 2.0) -> None:
        """
            Fred rationale:
            - Hit a *harmless* MCP endpoint via its LangChain tool (e.g., os_health -> GET /os/health)
            using the same client/auth path the real tools use.
            - Short timeout, errors are *non-fatal*. We only want to trigger the auth refresh.
        """
        tool = self._find_tool("os_health")
        if tool is None:
            logger.debug("MCP preflight skipped: os_health tool not found.")
            return
        try:
            # BaseTool supports invoke/ainvoke; pass empty dict as no-arg payload
            await asyncio.wait_for(tool.ainvoke({}), timeout=timeout_seconds)
            logger.warning("MCP preflight ok via os_health.")
        except Exception as e:
            # Intentionally non-fatal: we just want to exercise the auth path.
            logger.warning("MCP preflight failed (continuing): %s", e)

    def _generate_prompt(self) -> str:
        return (
            "You are Sentinel, an operations and monitoring agent for the Fred platform.\n"
            "Use the available MCP tools to inspect OpenSearch health and application KPIs.\n"
            "- Use os.* tools for cluster status, shards, indices, mappings, and diagnostics.\n"
            "- Use kpi.* tools for usage, cost, latency, and error rates.\n"
            "Return clear, actionable summaries. If something is degraded, propose concrete next steps.\n"
            "When you reference data from tools, add short bracketed markers like [os_health], [kpi_query].\n"
            "Prefer structured answers with bullets and short tables when helpful.\n"
            f"Current date: {self.current_date}.\n"
        )

    def _build_graph(self) -> StateGraph:
        if self.toolkit is None:
            raise RuntimeError("Toolkit must be initialized before building graph")
        
        self._snapshot_tools("build_graph/before_tools_node")
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)

        tools_node = make_resilient_tools_node(
            get_tools=lambda: (self.toolkit.get_tools() if self.toolkit else []),
            refresh_cb=self._refresh_mcp_session,
        )
        builder.add_node("tools", tools_node)   
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    async def reasoner(self, state: MessagesState):
        """
        One LLM step; may call tools (kpi.* or os.*). After tools run, we collect their
        outputs (JSON/objects) from ToolMessages and attach to response metadata for the UI.

        Fred rationale:
        - Run MCP preflight *before* the LLM decides to call tools. This ensures the
          underlying httpx Auth minted a fresh token (client-credentials) for this turn.
        - Preflight should be cheap and non-fatal: if it fails, we log and keep going.
        """
        if self.model is None:
            raise RuntimeError("Model is not initialized. Did you forget to call async_init()?")

        # if self.toolkit is not None:
        #     await self._preflight_mcp(timeout_seconds=2.0)

        try:
            response = self.model.invoke([self.base_prompt] + state["messages"])

            # Collect tool outputs by tool name, keep last result per tool call
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    # Normalize content: accept list/dict directly, else try JSON parse
                    normalized = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    if msg.name is not None:
                        tool_payloads[msg.name] = normalized

            # Attach tool results to metadata for the UI
            existing = response.response_metadata.get("tools", {})
            existing.update(tool_payloads)
            response.response_metadata["tools"] = existing

            return {"messages": [response]}

        except Exception as e:
            logger.exception("Sentinel: unexpected error: %s", e)
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred while checking the system. Please try again.")]
            )
            return {"messages": [fallback]}
