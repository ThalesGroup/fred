# app/agents/tabular/tabular.py
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

from app.common.mcp_runtime import MCPRuntime
from app.common.resilient_tool_node import make_resilient_tools_node
from app.common.structures import AgentSettings
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
TABULAR_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Tessa’s operating instructions: list datasets, inspect schema, "
                "formulate and run queries, and answer from actual results."
            ),
            required=True,
            default=(
                "You are a data analyst agent tasked with answering user questions based on structured tabular data "
                "such as CSV or Excel files. Use the available tools to **list, inspect, and query datasets**.\n\n"
                "### Instructions:\n"
                "1. ALWAYS start by invoking the tool to **list available datasets and their schema**.\n"
                "2. Decide which dataset(s) to use.\n"
                "3. Formulate an SQL-like query using the relevant schema.\n"
                "4. Invoke the query tool to get the answer.\n"
                "5. Derive your final answer from the actual data.\n\n"
                "### Rules:\n"
                "- Use markdown tables to present tabular results.\n"
                "- Do NOT invent columns or data that aren't present.\n"
                "- Format math formulas using LaTeX: `$$...$$` for blocks or `$...$` inline.\n"
                "- Always write text filters as case-insensitive (use LOWER() or ILIKE) so 'Oui' == 'oui' == 'OUI' for example.\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


@expose_runtime_source("agent.Tessa")
class Tessa(AgentFlow):
    """
    Tessa — searches and analyzes tabular documents via MCP tools (CSV, Excel, DB exports).
    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values are provided by YAML/DB/UI).
    - async_init(): set model, init MCP, bind tools, build graph.
    - Nodes decide whether to prepend tuned prompts (no global magic).
    """

    tuning = TABULAR_TUNING

    # Optional UX metadata (your system may read these from AgentSettings instead)
    name: str = "Tabular Expert"
    nickname: str = "Tom"
    role: str = "Data Query and SQL Expert"
    description: str = (
        "Executes SQL-like queries (joins/aggregations) over structured datasets. "
        "Ideal for analyzing tabular data ingested into the platform."
    )
    icon: str = "tabular_agent"
    categories: list[str] = ["tabular", "sql"]
    tag: str = "data"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(
            agent_settings=agent_settings,
            context_provider=lambda: self.get_runtime_context(),
        )
        # Accept list/dict tool payloads and raw strings; we normalize for UI metadata
        self._any_list_adapter: TypeAdapter[List[Any]] = TypeAdapter(List[Any])

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self):
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
                "Tessa: toolkit must be initialized before building the graph."
            )

        builder = StateGraph(MessagesState)

        # LLM node
        builder.add_node("reasoner", self._run_reasoning_step)

        # Tools node, with resilient refresh/rebind
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
        )  # → "tools" if tool calls requested
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "Tessa: model is not initialized. Call async_init() first."
            )

        # 1) Build the system prompt from tuning (tokens like {today} resolved safely)
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)

        # 2) Ask the model (prepend a single SystemMessage)
        messages = self.with_system(system_text, state["messages"])
        messages = self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            # 3) Collect tool outputs from ToolMessages and attach to response metadata for the UI
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
                    tool_payloads[msg.name or "unknown_tool"] = normalized

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
            logger.exception("Tessa failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while analyzing tabular data."
                    )
                ]
            )
            return {"messages": [fallback]}

    # ---------------------------
    # (Optional) helper for listing datasets from a prior tool result
    # ---------------------------
    def _extract_dataset_summaries_from_get_schema_reponse(
        self, data: list[dict]
    ) -> list[str]:
        summaries = []
        for entry in data:
            if isinstance(entry, dict) and {
                "document_name",
                "columns",
                "row_count",
            }.issubset(entry.keys()):
                try:
                    title = entry.get("document_name", "Untitled")
                    uid = entry.get("document_uid", "")
                    rows = entry.get("row_count", "?")
                    summaries.append(f"- **{title}** (`{uid}`), {rows} rows")
                except Exception as e:
                    logger.warning("Failed to summarize dataset entry: %s", e)
        return summaries
