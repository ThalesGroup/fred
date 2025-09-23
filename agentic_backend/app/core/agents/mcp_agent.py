# app/agents/mcp/mcp_agent.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import json
import logging
from typing import Any, Dict

from fred_core import get_model
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import tools_condition

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
MCP_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the MCP agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "You are an MCP-enabled assistant. Use the available MCP tools to solve the user's request:\n"
                "- ALWAYS use the tools at your disposal before providing any answer.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- When you reference tool results, keep short inline markers (e.g., [tool_name]).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


class MCPAgent(AgentFlow):
    """
    Dynamically-created agent that uses MCP-based tools.
    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values come from YAML/DB/UI)
    - async_init(): set model, init MCP, bind tools, build graph
    - Nodes opt-in to prepend tuned prompt (no global magic)
    """

    tuning = MCP_TUNING

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self):
        self.mcp = MCPRuntime(
            agent_settings=self.agent_settings,
            # If you expose runtime scoping (tenant/library/time), keep this provider:
            context_provider=lambda: self.get_runtime_context(),
        )
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError(
                "MCPAgent: toolkit must be initialized before building the graph."
            )

        builder = StateGraph(MessagesState)

        # LLM node
        builder.add_node("reasoner", self.reasoner)

        # Tools node with resilient refresh/rebind on transient failures
        async def _refresh_and_rebind():
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,
            refresh_cb=_refresh_and_rebind,
        )
        builder.add_node("tools", tools_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner", tools_condition
        )  # → "tools" when tool calls are requested
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        """
        One LLM step; the model may decide to call MCP tools.
        After tool calls, collect ToolMessages and surface their outputs for the UI.
        """
        if self.model is None:
            raise RuntimeError(
                "MCPAgent: model is not initialized. Call async_init() first."
            )

        # 1) Build the system prompt from tuning and render tokens (e.g., {today})
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)

        # 2) Ask the model (prepend a single SystemMessage)
        messages = self.with_system(system_text, state["messages"])

        try:
            response = await self.model.ainvoke(messages)

            # 3) Harvest tool outputs from ToolMessages → attach to response metadata for the UI
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw  # keep raw string if not JSON
                    if msg.name is not None:
                        tool_payloads[msg.name] = normalized

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
            logger.exception("MCPAgent: unexpected error during reasoning.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred.")]
            )
            return {"messages": [fallback]}
