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
from typing import Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
TABULAR_TUNING = AgentTuning(
    role="Structured Data Analyst",
    description="searches and analyzes tabular documents via MCP tools (CSV, Excel)",
    tags=["data"],
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
                "- When filtering or comparing text values in SQL, always normalize both sides with LOWER().\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
    ],
)


class TabularState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    database_context: List[
        Dict[str, Any]
    ]  # [{"database": "db1", "tables": ["t1", "t2"]}]


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

    # ---------------------------
    # Bootstrap
    # ---------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        await self.mcp.init()  # start MCP + toolkit
        self.model = self.model.bind_tools(self.mcp.get_tools())
        self._graph = self._build_graph()

    async def aclose(self):
        await self.mcp.aclose()

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

    def _latest_tool_output(self, state: TabularState, tool_name: str) -> Any:
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == tool_name:
                return self._maybe_parse_json(msg.content)
        return None

    def _format_context_for_prompt(self, database_context: List[Dict[str, Any]]) -> str:
        """Format the DB context for injection into the system prompt in a clear hierarchical style."""
        if not database_context:
            return "No databases or tables currently loaded.\n"

        lines = ["You have access to :"]
        for entry in database_context:
            entry = self._maybe_parse_json(entry)
            db = entry.get("database", "unknown")
            tables = entry.get("tables", [])
            lines.append(f"- Database: {db} with tables: {tables}")
        return "\n".join(lines)

    async def _ensure_database_context(
        self, state: TabularState
    ) -> List[Dict[str, Any]]:
        if state.get("database_context"):
            return state["database_context"]

        logger.info("Fetching database context via MCP (get_tabular_context)...")
        try:
            tools = self.mcp.get_tools()
            tool = next((t for t in tools if t.name == "get_context"), None)
            if not tool:
                logger.warning("Unable to find tool 'get_context' in MCP server.")
                return []

            raw_context = await tool.ainvoke({})

            # Parser la string JSON en liste de dicts
            context = (
                json.loads(raw_context) if isinstance(raw_context, str) else raw_context
            )

            # Sauvegarder dans l'état pour les appels suivants
            state["database_context"] = context
            return context

        except Exception as e:
            logger.warning(f"Could not load database context: {e}")
            return []

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TabularState)

        # LLM node
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", self.mcp.get_tool_nodes())
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # LLM node
    # ---------------------------
    async def reasoner(self, state: TabularState):
        if self.model is None:
            raise RuntimeError(
                "Tessa: model is not initialized. Call async_init() first."
            )

        tpl = self.get_tuned_text("prompts.system") or ""

        # 🟢 Load database + tables context if missing
        database_context = await self._ensure_database_context(state)
        tpl += self._format_context_for_prompt(database_context)
        system_text = self.render(tpl)

        # Build message sequence
        recent_history = self.recent_messages(state["messages"], max_messages=5)
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            # 🔹 Update metadata with tool responses
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                    raw = msg.content
                    try:
                        normalized = json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:
                        normalized = raw
                    tool_payloads[msg.name or "unknown_tool"] = normalized

            md = getattr(response, "response_metadata", {}) or {}
            tools_md = md.get("tools", {}) or {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md

            return {
                "messages": [response],
                "database_context": database_context,
            }

        except Exception:
            logger.exception("Tessa failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while analyzing tabular data."
                    )
                ]
            )
            return {
                "messages": [fallback],
                "database_context": [],
            }

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
