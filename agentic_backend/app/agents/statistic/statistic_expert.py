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
STATISTIC_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sage’s operating instructions: analyse data, plot "
                "graphs and train classic ML models."
            ),
            required=True,
            default=(
                "You are a helpful and precise data science assistant working on structured data (CSV, Excel).\n"
                "Your main tasks are to analyze datasets, generate visualizations, and build simple machine learning models.\n\n"
                "### Instructions:\n"
                "1. List available datasets and explore their schema.\n"
                "2. Apply statistical analysis or ML models when asked.\n"
                "3. Visualize data using appropriate chart types.\n"
                "4. Answer clearly and interpret your results.\n\n"
                "### Rules:\n"
                "- Use markdown to format outputs and wrap code in code blocks.\n"
                "- NEVER make up data or columns that don't exist.\n"
                "- Prefer visual explanations and graphs where applicable.\n"
                "- Format mathematical expressions using LaTeX: `$$...$$` for display or `$...$` inline.\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


@expose_runtime_source("agent.Sage")
class Sage(AgentFlow):
    """
    Sage — searches and analyzes tabular documents via MCP tools (CSV, Excel, DB exports).
    Pattern alignment with AgentFlow:
    - Class-level `tuning` (spec only; values are provided by YAML/DB/UI).
    - async_init(): set model, init MCP, bind tools, build graph.
    - Nodes decide whether to prepend tuned prompts (no global magic).
    """

    tuning = STATISTIC_TUNING

    # Optional UX metadata (your system may read these from AgentSettings instead)
    name: str = "Statistic Expert"
    nickname: str = "Sage"
    role: str = "Data Scientist Expert"
    description: str = (
        "analyse data, plot graphs and train classic ML models. "
        "Ideal for analyzing tabular data ingested into the platform."
    )
    icon: str = "statistic_agent"
    categories: list[str] = ["statistic", "sql"]
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
                "Sage: toolkit must be initialized before building the graph."
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
                "Sage: model is not initialized. Call async_init() first."
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
            logger.exception("Sage failed during reasoning.")
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
