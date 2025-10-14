# app/agents/tabular/tabular.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import json
import logging
from typing import Any, List, Optional

from fred_core import get_model
from langchain_core.messages import ToolMessage, AIMessage
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

from app.core.chatbot.chat_schema import GeoPart, TextPart, MessagePart
from app.agents.tabular.vessel import VesselData, VesselFeature

logger = logging.getLogger(__name__)

# ---------------------------
# Agent tuning
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
                "such as CSV or Excel files. You can also display a geomap based on input you get from the tool results. Use the available tools to **list, inspect, and query datasets**.\n\n"
                "### Instructions:\n"
                "1. ALWAYS start by invoking the tool to **list available datasets and their schema**.\n"
                "2. Decide which dataset(s) to use.\n"
                "3. Formulate an SQL-like query using the relevant schema.\n"
                "4. Invoke the query tool to get the answer.\n"
                "5. Derive your final answer from the actual data.\n\n"
                "6. ALWAYS use the geojson column when available when asked to create/generate a geomap or a map"
                "### Rules:\n"
                "- Use markdown tables to present tabular results.\n"
                "- Do NOT invent columns or data that aren't present.\n"
                "- Format math formulas using LaTeX: `$$...$$` for blocks or `$...$` inline.\n"
                "- Always write text filters as case-insensitive (use LOWER() or ILIKE).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ]
)


@expose_runtime_source("agent.Tessa")
class Tessa(AgentFlow):
    """
    Tessa — an intelligent agent for tabular and SQL data analysis,
    capable of automatically rendering geospatial results when detected.
    """

    tuning = TABULAR_TUNING

    name: str = "Tabular Expert"
    nickname: str = "Tom"
    role: str = "Data Query and SQL Expert"
    description: str = (
        "Executes SQL-like queries (joins/aggregations) over structured datasets. "
        "Can analyze, summarize, and visualize tabular and geospatial data."
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
    # Graph setup
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        if self.mcp.toolkit is None:
            raise RuntimeError("Tessa: toolkit must be initialized before building the graph.")

        builder = StateGraph(MessagesState)

        builder.add_node("reasoner", self._run_reasoning_step)

        async def _refresh_and_rebind():
            self.model = await self.mcp.refresh_and_bind(self.model)

        tools_node = make_resilient_tools_node(
            get_tools=self.mcp.get_tools,
            refresh_cb=_refresh_and_rebind,
        )
        builder.add_node("tools", tools_node)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    # ---------------------------
    # Reasoning step
    # ---------------------------

    def _run_reasoning_step(self, step_input: dict) -> dict:
        """
        Main reasoning step for the tabular agent.
        Detects geospatial payloads (GeoJSON) inside ToolMessages,
        and returns a GeoPart if relevant; otherwise, continues normal reasoning.
        """

        messages = step_input.get("messages", [])
        geojson_data = None
        latest_tool_result = None

        # --- 1️⃣ Find the most recent ToolMessage (the one returning SQL results) ---
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                try:
                    # The tool result is usually a JSON string
                    payload = json.loads(msg.content)
                    latest_tool_result = payload
                    break
                except Exception:
                    continue

        # --- 2️⃣ If we found a tool result, check if it contains rows with geojson ---
        if latest_tool_result and isinstance(latest_tool_result, dict):
            if "rows" in latest_tool_result:
                geojson_data = build_feature_collection_from_tool(latest_tool_result)

        # --- 3️⃣ If geospatial data detected, return a GeoPart ---
        if geojson_data:
            final_parts = [
                TextPart(text="🗺️ Geospatial data detected — displaying map view."),
                GeoPart(
                    geojson=geojson_data,
                    popup_property="name",
                    fit_bounds=True,
                ),
            ]
            return {"messages": [AIMessage(content="", parts=final_parts)]}

        # --- 4️⃣ Otherwise, continue normal reasoning flow ---
        # (i.e., call LLM again with the previous context + last tool result)
        try:
            # fallback to normal model reasoning
            response = self.model.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.exception("Reasoning step failed: %s", e)
            return {"messages": [AIMessage(content=f"Error during reasoning: {e}")]}


    # ---------------------------
    # Dataset schema summary helper
    # ---------------------------
    def _extract_dataset_summaries_from_get_schema_reponse(
        self, data: list[dict]
    ) -> list[str]:
        summaries = []
        for entry in data:
            if isinstance(entry, dict) and {"document_name", "columns", "row_count"}.issubset(entry.keys()):
                try:
                    title = entry.get("document_name", "Untitled")
                    uid = entry.get("document_uid", "")
                    rows = entry.get("row_count", "?")
                    summaries.append(f"- **{title}** (`{uid}`), {rows} rows")
                except Exception as e:
                    logger.warning("Failed to summarize dataset entry: %s", e)
        return summaries

def build_feature_collection_from_tool(tool_result: dict) -> Optional[dict]:
    """
    Converts raw tool output (rows from PostgreSQL)
    into a valid GeoJSON FeatureCollection validated by VesselFeature/VesselData,
    only if the data actually contains geospatial fields.
    """
    rows = tool_result.get("rows", [])
    features = []

    # Quick pre-check: skip if there are no obvious geo fields
    if not rows:
        return None

    has_geo_fields = any(
        ("geojson" in row and row["geojson"])
        or ("latitude" in row and "longitude" in row)
        for row in rows
    )
    if not has_geo_fields:
        return None  # ❌ normal table, no geospatial data

    for row in rows:
        try:
            # Case 1: explicit GeoJSON column
            if "geojson" in row and row["geojson"]:
                geo = row["geojson"]
                if isinstance(geo, str):
                    geo = json.loads(geo)
                feature = VesselFeature(**geo)

            # Case 2: lat/lon columns
            elif "latitude" in row and "longitude" in row:
                feature = VesselFeature(
                    geometry={
                        "type": "Point",
                        "coordinates": [row["longitude"], row["latitude"]],
                    },
                    properties={
                        "name": row.get("boat_name", "Unknown"),
                        "type": row.get("type", "Unknown"),
                        "speed": row.get("speed"),
                        "destination": row.get("destination"),
                    },
                )
            else:
                continue

            features.append(feature)

        except Exception as e:
            logger.warning(f"Ignored invalid feature: {e}")

    if not features:
        return None

    vessel_collection = VesselData(features=features)
    return vessel_collection.model_dump()
