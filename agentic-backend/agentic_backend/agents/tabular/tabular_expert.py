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
from typing import Annotated, Any, Dict, Iterable, List, Optional, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
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
from agentic_backend.core.chatbot.chat_schema import GeoPart, TextPart
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
                "You are a top-tier data analysis expert working with tabular data (CSV, Excel)."
                "Your goal is to answer user questions accurately and efficiently using the data, "
                "applying best practices in data exploration, SQL-like querying, and result presentation..\n\n"
                "### Instructions:\n"
                "- Assess datasets and choose the most relevant ones.\n"
                "- Design queries and calculations intelligently; optimize for clarity and performance.\n"
                "- Present results clearly in markdown tables.\n"
                "- Ensure all answers are based on actual data; do not invent values. \n"
                "- Normalize text when comparing or filtering in SQL (use LOWER()).\n\n"
                "If the user asks for a map/visualization and you include geospatial data, the UI will render it "
                "when you output a GeoPart. In that case, do NOT say you cannot show a map; instead confirm that "
                "the map is displayed and keep the explanation brief.\n\n"
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
    database_context: Dict[str, List[Dict[str, Any]]]


_LAT_KEYS = (
    "lat",
    "latitude",
    "lat_dd",
    "lat_deg",
    "lat_degrees",
    "y",
    "y_coord",
    "y_coordinate",
)
_LON_KEYS = (
    "lon",
    "lng",
    "long",
    "longitude",
    "lon_dd",
    "lon_deg",
    "lon_degrees",
    "x",
    "x_coord",
    "x_coordinate",
)
_POPUP_KEYS = (
    "name",
    "ship_name",
    "vessel_name",
    "vessel",
    "ship",
    "mmsi",
    "imo",
    "id",
)


def _last_user_text(messages: Iterable[AnyMessage]) -> str:
    for msg in reversed(list(messages)):
        if isinstance(msg, HumanMessage):
            return str(getattr(msg, "content", "")).strip()
        if getattr(msg, "type", "") in ("human", "user"):
            return str(getattr(msg, "content", "")).strip()
    return ""


def _wants_map(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "map",
            "plot",
            "where",
            "location",
            "carte",
            "visuel",
            "visuelle",
            "visuellement",
            "visualiser",
            "visualisation",
            "localiser",
            "localisation",
            "position",
            "positions",
            "ou sont",
        )
    )


def _iter_rows(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield row
        for value in payload.values():
            yield from _iter_rows(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_rows(item)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _select_key(row: Dict[str, Any], candidates: tuple[str, ...]) -> Optional[str]:
    lowered = {k.lower(): k for k in row.keys()}
    for key in candidates:
        if key in lowered:
            return lowered[key]
    return None


def _choose_popup_property(row: Dict[str, Any]) -> Optional[str]:
    return _select_key(row, _POPUP_KEYS)


def _row_to_properties(row: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            props[key] = value
        else:
            props[key] = str(value)
    return props


def _build_geo_part(
    tool_payloads: Dict[str, Any], max_points: int = 500
) -> Optional[GeoPart]:
    rows = list(_iter_rows(tool_payloads))
    if not rows:
        return None

    lat_key = _select_key(rows[0], _LAT_KEYS)
    lon_key = _select_key(rows[0], _LON_KEYS)
    if not lat_key or not lon_key:
        return None

    features: List[Dict[str, Any]] = []
    for row in rows:
        lat = _to_float(row.get(lat_key))
        lon = _to_float(row.get(lon_key))
        if lat is None or lon is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": _row_to_properties(row),
            }
        )
        if len(features) >= max_points:
            break

    if not features:
        return None

    popup_property = _choose_popup_property(rows[0])
    return GeoPart(
        geojson={"type": "FeatureCollection", "features": features},
        popup_property=popup_property,
        fit_bounds=True,
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

    def _format_context_for_prompt(
        self, database_context: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Format DB context where the dict structure is:
        {
            "<database_name>": [
                { "table_name": ..., "columns": [...], "row_count": ... },
                ...
            ]
        }
        """

        if not database_context:
            return "No databases or tables currently loaded.\n"

        # If entry is JSON in string form → parse it
        database_context = self._maybe_parse_json(database_context)

        lines = ["You have access to:"]

        # Each key is the name of a database
        for db_name, tables in database_context.items():
            lines.append(f"- Database: {db_name}")

            for table in tables:
                table = self._maybe_parse_json(table)
                if not isinstance(table, dict):
                    lines.append(f"  • Table: {table}")
                    continue

                table_name = table.get("table_name", "unknown")
                columns = table.get("columns", [])
                row_count = table.get("row_count", "unknown")

                lines.append(f"  • Table: {table_name}  (rows: {row_count})")
                # Normalize columns so non-iterables don't crash the prompt formatter.
                if isinstance(columns, int):
                    lines.append(f"      Columns: {columns} columns")
                    continue

                col_items: list[dict[str, Any]] = []
                if isinstance(columns, dict):
                    col_items = [
                        {"name": name, "dtype": dtype}
                        for name, dtype in columns.items()
                    ]
                elif isinstance(columns, list):
                    for col in columns:
                        if isinstance(col, dict):
                            col_items.append(col)
                        elif isinstance(col, str):
                            col_items.append({"name": col, "dtype": "unknown"})
                        else:
                            col_items.append({"name": str(col), "dtype": "unknown"})

                if not col_items:
                    lines.append("      Columns: unknown")
                    continue

                lines.append("      Columns:")

                for col in col_items:
                    col_name = col.get("name", "unknown")
                    col_type = col.get("dtype", "unknown")
                    lines.append(f"        - {col_name}: {col_type}")

        return "\n".join(lines)

    async def _ensure_database_context(
        self, state: TabularState
    ) -> Dict[str, List[Dict[str, Any]]]:
        if state.get("database_context"):
            return state["database_context"]

        logger.info("Fetching database context via MCP (get_tabular_context)...")
        try:
            tools = self.mcp.get_tools()
            tool = next((t for t in tools if t.name == "get_context"), None)
            if not tool:
                logger.warning("Unable to find tool 'get_context' in MCP server.")
                return {}

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
            return {}

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

            user_text = _last_user_text(state.get("messages", []))
            if _wants_map(user_text):
                geo_part = _build_geo_part(tool_payloads)
                if geo_part:
                    answer_text = str(getattr(response, "content", "") or "")
                    response = AIMessage(
                        content=answer_text,
                        additional_kwargs=getattr(response, "additional_kwargs", {}),
                        response_metadata=response.response_metadata,
                        parts=[TextPart(text=answer_text), geo_part],
                    )

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
