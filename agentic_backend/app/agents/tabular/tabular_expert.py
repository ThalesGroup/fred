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


import json
import logging
from typing import Any, Dict

from fred_core import get_model
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.common.mcp_runtime import MCPRuntime
from app.common.structures import AgentSettings
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.agents.runtime_context import RuntimeContext
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

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        self.mcp = MCPRuntime(agent=self)
        self._recent_table_names: list[str] = []

    # ---------------------------
    # Tool cache helpers
    # ---------------------------
    def _maybe_parse_json(self, payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                return payload
        return payload

    def _latest_tool_output(self, state: MessagesState, tool_name: str) -> Any:
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == tool_name:
                return self._maybe_parse_json(msg.content)
        return None

    def _is_table_question(self, text: str) -> bool:
        lowered = text.lower()
        if "table" not in lowered:
            return False
        intent_markers = ("what", "list", "which", "again", "available", "show")
        return any(marker in lowered for marker in intent_markers)

    def _format_table_names(self, tables: list[str]) -> str:
        if not tables:
            return "I do not have any tables listed yet."
        bullets = "\n".join(f"- `{name}`" for name in tables)
        return f"The available table(s):\n{bullets}"

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_model(self.agent_settings.model)
        await self.mcp.init()  # start MCP + toolkit
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)

        # LLM node
        builder.add_node("reasoner", self.reasoner)

        tools = self.mcp.get_tools()
        tool_node = ToolNode(tools=tools)
        builder.add_node("tools", tool_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "Tessa: model is not initialized. Call async_init() first."
            )

        latest_tables_raw = self._latest_tool_output(state, "list_table_names")
        parsed_table_names: list[str] = []
        if isinstance(latest_tables_raw, list):
            parsed_table_names = [str(item) for item in latest_tables_raw]
        elif isinstance(latest_tables_raw, dict):
            names = latest_tables_raw.get("tables") or latest_tables_raw.get("data")
            if isinstance(names, list):
                parsed_table_names = [str(item) for item in names]

        if parsed_table_names:
            self._recent_table_names = parsed_table_names

        last_message = state["messages"][-1]
        cached_tables = self._recent_table_names
        if (
            cached_tables
            and isinstance(last_message, HumanMessage)
            and isinstance(last_message.content, str)
            and self._is_table_question(last_message.content)
        ):
            answer = AIMessage(content=self._format_table_names(cached_tables))
            return {"messages": [answer]}

        # 1) Build the system prompt from tuning (tokens like {today} resolved safely)
        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)

        # 2) Ask the model (prepend a single SystemMessage)
        recent_history = self.recent_messages(state["messages"], max_messages=6)
        messages = self.with_system(system_text, recent_history)
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
                    if getattr(msg, "name", "") == "list_table_names":
                        parsed = self._maybe_parse_json(raw)
                        if isinstance(parsed, list):
                            self._recent_table_names = [str(item) for item in parsed]
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
