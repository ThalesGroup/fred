# app/agents/sentinel/sentinel.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import json
import logging
from typing import Any, Dict, List

from fred_core import get_model

# 🟢 NEW IMPORT: Required for explicit type hint
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from pydantic import TypeAdapter

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
SENTINEL_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sentinel’s operating doctrine. Keep it focused on MCP tools, "
                "concise ops guidance, and actionable next steps."
            ),
            required=True,
            default=(
                "You are Sentinel, an operations and monitoring agent for the Fred platform.\n"
                "Use the available MCP tools to inspect OpenSearch health and application KPIs.\n"
                "- Use os.* tools for cluster status, shards, indices, mappings, and diagnostics.\n"
                "- Use kpi.* tools for usage, cost, latency, and error rates.\n"
                "Return clear, actionable summaries. If something is degraded, propose concrete next steps.\n"
                "When you reference data from tools, add short bracketed markers like [os_health], [kpi_query].\n"
                "Prefer structured answers with bullets and short tables when helpful.\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


class SentinelExpert(AgentFlow):
    """
    Sentinel — Ops & Monitoring agent (OpenSearch + KPIs).

    Uses lazy initialization for the MCP client to defer connection until the
    first user message, avoiding cold-start token issues.
    """

    tuning = SENTINEL_TUNING

    # 🟢 NEW: Explicitly type-hint self.model to stop Pylance warning
    # The bound model may become a Runnable (from .bind_tools), so allow Any to cover both BaseChatModel and Runnable types.
    model: BaseChatModel | Any | None = None

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        # MCP runtime keeps the tool client fresh and provides a current toolkit.
        self.mcp = MCPRuntime(
            agent=self,
        )
        # Accept list/dict tool payloads and raw strings (we’ll normalize)
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

        # 🟢 NEW: Flag to track if MCP has been initialized
        self._mcp_initialized = False

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self):
        # 1) LLM
        self.model = get_model(self.agent_settings.model)

        # Ensure a model was returned
        if self.model is None:
            raise RuntimeError(
                "Sentinel: get_model returned None for model config: "
                f"{self.agent_settings.model}"
            )

        # 2) Tools: 🔴 CHANGE - DO NOT CALL self.mcp.init() here.
        # Bind model with NO tools initially (self.mcp.get_tools() returns []).
        # Only call bind_tools if the returned model actually provides it.
        if hasattr(self.model, "bind_tools"):
            # mypy/pylance: we already guarded against None above
            self.model = self.model.bind_tools(self.mcp.get_tools())
        else:
            logger.warning(
                "Sentinel: model of type %s does not expose bind_tools(); skipping initial tool binding",
                type(self.model),
            )

        # 3) Graph
        self._graph = self._build_graph()

    async def aclose(self):
        # Let AgentManager call this on shutdown.
        await self.mcp.aclose()

    # ---------------------------
    # Lazy MCP Initialization Node
    # ---------------------------
    async def init_mcp(self, state: MessagesState):
        """
        Initializes the MCP client and rebinds the model with the loaded tools.
        This runs only on the first message.
        """
        if not self._mcp_initialized:
            logger.info("Sentinel: Lazy initializing MCP client and binding tools.")

            # This is the point where the connection happens
            await self.mcp.init()

            # Ensure model was initialized (async_init should have been called).
            if self.model is None:
                raise RuntimeError(
                    "Sentinel: model is not initialized. Call async_init() before MCP initialization."
                )

            # Rebind the model with the now-available tools only if supported.
            if hasattr(self.model, "bind_tools"):
                self.model = self.model.bind_tools(self.mcp.get_tools())
            else:
                logger.warning(
                    "Sentinel: model of type %s does not expose bind_tools(); skipping tool bind",
                    type(self.model),
                )

            self._mcp_initialized = True

        # Pass control to the reasoner
        return state

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        # Node for lazy initialization. This is the first step.
        builder.add_node("init_mcp", self.init_mcp)

        # LLM node
        builder.add_node("reasoner", self.reasoner)

        # Tools node, with resilient refresh
        async def _refresh_and_rebind():
            # On transient tool errors (401/timeout/stream close) refresh client & rebind.
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,
            refresh_cb=_refresh_and_rebind,
        )
        builder.add_node("tools", tools_node)

        # Flow: START → init_mcp → reasoner → (tools?) → reasoner → …
        builder.add_edge(START, "init_mcp")
        builder.add_edge("init_mcp", "reasoner")  # Link init node to the main logic

        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        """
        One LLM step; may decide to call tools (kpi.* or os.*).
        After tools run, ToolMessages are present in `state["messages"]`.
        We collect their outputs and attach to the model response metadata for the UI.
        """
        # This check is now redundant but kept for robustness/safety
        if self.model is None:
            raise RuntimeError(
                "Sentinel: model is not initialized. Call async_init() first."
            )

        # 1) Build the system prompt from tuning (and tokens like {today})
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)  # keeps unknown {tokens} literal

        # 2) Ask the model with a single SystemMessage prepended
        messages = self.with_system(system_text, state["messages"])
        messages = self.with_chat_context_text(messages)

        try:
            # Pylance is happy here due to the explicit type hint
            response = await self.model.ainvoke(messages)

            # 3) Collect tool outputs (latest per tool name) from the history
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                name = getattr(msg, "name", None)
                if isinstance(msg, ToolMessage) and isinstance(name, str):
                    raw = msg.content
                    # Accept dict/list directly; try JSON decode for strings
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    tool_payloads[name] = normalized

            # 4) Attach tool results to metadata for the UI
            md = getattr(response, "response_metadata", None)
            if not isinstance(md, dict):
                md = {}
            tools_md = md.get("tools", {})
            if not isinstance(tools_md, dict):
                tools_md = {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md

            return {"messages": [response]}

        except Exception:
            logger.exception("Sentinel: unexpected error")
            # Pylance is happy here due to the explicit type hint
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while checking the system. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
