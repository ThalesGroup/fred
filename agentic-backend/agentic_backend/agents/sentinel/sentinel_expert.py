# agentic_backend/agents/sentinel/sentinel.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import json
import logging
from typing import Any, Dict, List

from fred_core import get_model
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from pydantic import TypeAdapter

from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.resilient_tool_node import make_resilient_tools_node
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

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

    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values come from YAML/DB/UI).
    - async_init(): set model, init MCP (tools), bind tools, build graph.
    - Each node chooses if/when to use the tuned prompt (no global magic).
    """

    tuning = SENTINEL_TUNING

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        # MCP runtime keeps the tool client fresh and provides a current toolkit.
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            context_provider=lambda: self.get_runtime_context(),
        )
        # Accept list/dict tool payloads and raw strings (we’ll normalize)
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self):
        # 1) LLM
        self.model = get_model(self.agent_settings.model)

        # 2) Tools
        await self.mcp.init()  # start MCP + toolkit
        self.model = self.model.bind_tools(self.mcp.get_tools())

        # 3) Graph
        self._graph = self._build_graph()

    async def aclose(self):
        # Let AgentManager call this on shutdown.
        await self.mcp.aclose()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError(
                "Sentinel: toolkit must be initialized before building the graph."
            )

        builder = StateGraph(MessagesState)

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

        # Flow: START → reasoner → (tools?) → reasoner → …
        builder.add_edge(START, "reasoner")
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
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while checking the system. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
