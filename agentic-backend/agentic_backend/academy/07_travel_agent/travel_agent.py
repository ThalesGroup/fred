# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");

import logging
import re
from typing import List, Optional, TypedDict
from typing_extensions import Annotated
import httpx
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.constants import START, END
from langgraph.graph import MessagesState, StateGraph
from langgraph.graph.message import add_messages

from agentic_backend.core.chatbot.chat_schema import TextPart, MessagePart
from agentic_backend.core.runtime_source import expose_runtime_source
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ---------------------------
# Travel Agent Tuning
# ---------------------------
TRAVEL_TUNING = AgentTuning(
    role="travel_guide",
    description="Travel guide agent: museums, monuments, restaurants, hotels, etc.",
    tags=["tourism", "map", "free"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description="Defines Travel agent behavior.",
            required=True,
            default=(
                "You are a friendly travel guide. "
                "Use the available tools for geolocation and POIs. "
                "Fallback to LLM if no data is found."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)

# ---------------------------
# Agent State
# ---------------------------
class TravelAgentState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], add_messages]
    city: str
    category_tag: str
    lat: Optional[float]
    lon: Optional[float]
    pois: list
    top_n: int
    poi_markdown: str


# ---------------------------
# Travel Agent Implementation (One Node Version)
# ---------------------------
@expose_runtime_source("agent.Travel")
class Travel(AgentFlow):
    tuning = TRAVEL_TUNING
    _graph: Optional[StateGraph] = None

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        if getattr(self, "model", None) is None:
            from agentic_backend.application_context import get_default_chat_model
            self.model = get_default_chat_model()
        self._graph = self._build_graph()

    # ---------------------------
    # Graph with single node
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("travel_main", self.travel_main_node)
        builder.add_edge(START, "travel_main")
        builder.add_edge("travel_main", END)
        return builder

    # ---------------------------
    # Unified Travel Node
    # ---------------------------
    async def travel_main_node(self, state: TravelAgentState) -> TravelAgentState:
        user_msg = state["messages"][-1]
        query_text = str(getattr(user_msg, "content", "")).strip()
        logger.info(f"[TravelAgent] Processing query: {query_text!r}")

        # Step 1: Parse city and category via LLM
        system_prompt = (
            "You are a travel assistant. "
            "Extract city and OSM tag for Overpass API from user query. "
            "Return two values separated by comma: city name, osm tag."
        )
        user_prompt = f"User query: {query_text}\nReturn: city, osm_tag"

        city, category_tag = "", "tourism"
        try:
            response = await self.model.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
            text = getattr(response, "content", "").strip()
            parts = [p.strip() for p in text.split(",")]
            if len(parts) == 2:
                city, category_tag = parts
            else:
                logger.warning(f"[TravelAgent] Unexpected LLM output: {text!r}")
        except Exception as e:
            logger.warning(f"[TravelAgent] Failed to parse city/category: {e}")

        # Step 2: OSM search for coordinates
        lat, lon = None, None
        if city:
            try:
                async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "AgenticTravelBot/1.0"}) as client:
                    r = await client.get("https://nominatim.openstreetmap.org/search", params={"q": city, "format": "json", "limit": 1})
                    r.raise_for_status()
                    results = r.json()
                    if results:
                        lat = float(results[0].get("lat", 0))
                        lon = float(results[0].get("lon", 0))
            except Exception as e:
                logger.warning(f"[TravelAgent] OSM lookup failed: {e}")

        # Step 3: Fetch POIs
        match = re.search(r"(\d+)", query_text)
        top_n = int(match.group(1)) if match else 5
        pois = []

        if lat and lon:
            query = f"""
            [out:json][timeout:25];
            node(around:5000,{lat},{lon})[{category_tag}];
            out {top_n};
            """
            try:
                async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "AgenticTravelBot/1.0"}) as client:
                    r = await client.get("https://overpass-api.de/api/interpreter", params={"data": query})
                    r.raise_for_status()
                    payload = r.json()
                    pois = payload.get("elements", [])
            except Exception as e:
                logger.warning(f"[TravelAgent] Overpass fetch failed: {e}")

        # Step 4: Format Markdown output
        if not lat or not lon:
            final_text = "*Aucun point d'intérêt trouvé (coordonnées manquantes).*"
        elif not pois:
            final_text = "*Aucun point d'intérêt trouvé (catégories manquantes).*"
        else:
            md_output = f"## {top_n} POI les plus proches de {city} ({category_tag})\n\n"
            md_output += "| Nom | Lien OpenStreetMap |\n| --- | --- |\n"
            for e in pois[:top_n]:
                name = e.get("tags", {}).get("name", "-")
                osm_url = f"https://www.openstreetmap.org/node/{e.get('id','')}"
                md_output += f"| {name} | [OSM]({osm_url}) |\n"
            final_text = md_output

        logger.info(f"[TravelAgent] Done for {city or 'unknown city'} ({category_tag}), found {len(pois)} POIs")

        return {"messages": [AIMessage(content=final_text)]}
