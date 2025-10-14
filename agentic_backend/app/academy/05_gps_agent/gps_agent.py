# app/core/agents/gps_agent.py
# -----------------------------------------------------------------------------
# 💡 ACADEMY AGENT: GPS AGENT (STATIC DEMO) 💡
# This agent returns a hardcoded GeoJSON FeatureCollection to demonstrate
# the GeoPart structure and the Leaflet map component without using the LLM.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import List, Optional, TypedDict

# We can remove imports related to LLM (get_model, BaseModel, Field, LangChain)
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated

from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning

# Import GeoPart and TextPart
from app.core.chatbot.chat_schema import GeoPart, MessagePart, TextPart
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


# --- Agent State (Kept for LangGraph compatibility) ---
class GpsAgentState(TypedDict, total=False):
    """Minimal state: conversation messages."""

    messages: Annotated[List[AnyMessage], add_messages]


# --- Core Agent ---
@expose_runtime_source("agent.GpsAgent")
class GpsAgent(AgentFlow):
    """
    Returns static GeoJSON data for demonstration purposes.
    """

    tuning = AgentTuning()
    _graph: Optional[StateGraph] = None

    async def async_init(self):
        # We can remove self.model initialization
        self._graph = self._build_graph()

    # ... (_build_graph and _last_user_message_text are unchanged,
    #       though the latter is now unused but harmless)

    def _build_graph(self) -> StateGraph:
        """Sets up the single-node linear flow: generate -> END."""
        g = StateGraph(GpsAgentState)
        g.add_node("generate_node", self.generate_node)
        g.add_edge(START, "generate_node")
        g.add_edge("generate_node", END)
        return g

    def _last_user_message_text(self, state: GpsAgentState) -> str:
        """Fetches the content of the most recent user message."""
        for msg in reversed(state.get("messages", [])):
            if getattr(msg, "type", "") in ("human", "user"):
                return str(getattr(msg, "content", "")).strip()
        return ""

    # --------------------------------------------------------------------------
    # Node 1: Generate Node (STATIC GEOJSON)
    # --------------------------------------------------------------------------
    async def generate_node(self, state: GpsAgentState) -> GpsAgentState:
        """Generates static GeoJSON data for Mediterranean vessels near France."""

        # --- STATIC DATA DEFINITION ---
        # GeoJSON is [Longitude, Latitude]
        VESSEL_DATA = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.385, 43.296]},
                    "properties": {"name": "Marseille Port (Ref)", "type": "Port"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.2, 43.1]},
                    "properties": {
                        "name": "Cargo Vessel A",
                        "type": "Cargo",
                        "speed": "12.5 kts",
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.6, 43.5]},
                    "properties": {
                        "name": "Oil Tanker B",
                        "type": "Tanker",
                        "destination": "Fos-sur-Mer",
                    },
                },
            ],
        }
        # --- END STATIC DATA DEFINITION ---

        # Construct the final structured message using the GeoPart
        final_parts: list[MessagePart] = [
            TextPart(
                text="🗺️ Displaying map with static Mediterranean vessel locations near Marseille for demo."
            ),
            GeoPart(
                geojson=VESSEL_DATA,
                popup_property="name",  # Use the 'name' property for popups
                fit_bounds=True,
            ),
        ]

        # FINAL RETURN
        return {"messages": [AIMessage(content="", parts=final_parts)]}
