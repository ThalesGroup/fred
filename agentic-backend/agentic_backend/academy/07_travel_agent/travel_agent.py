# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");

import logging
import re
import uuid
from typing import List, Optional, TypedDict
from typing_extensions import Annotated

import httpx
from langchain_core.messages import AIMessage, HumanMessage, AnyMessage
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
    osm_results: list
    pois: list
    top_n: int
    poi_markdown: str


# ---------------------------
# Travel Agent Implementation
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
    # Graph Definition
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("parse_city_and_category", self.parse_city_and_category_node)
        builder.add_node("osm_search", self.osm_search_node)
        builder.add_node("fetch_pois", self.fetch_pois_node)
        builder.add_node("format_pois", self.format_pois_node)  

        builder.add_edge(START, "parse_city_and_category")
        builder.add_edge("parse_city_and_category", "osm_search")
        builder.add_edge("osm_search", "fetch_pois")
        builder.add_edge("fetch_pois", "format_pois")
        builder.add_edge("format_pois", END)

        return builder

    # ---------------------------
    # Node 1: Parse city & category
    # ---------------------------
    async def parse_city_and_category_node(
        self, state: TravelAgentState
    ) -> TravelAgentState:
        user_msg = state["messages"][-1]
        query_text = str(getattr(user_msg, "content", "")).strip()
        logger.info(f"[TravelAgent] Parsing city and category from query: {query_text!r}")

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
                city, category_tag = parts[0], parts[1]
            else:
                logger.warning(f"[TravelAgent] LLM returned unexpected format: {text!r}")
        except Exception as e:
            logger.warning(f"[TravelAgent] Failed to parse city and category: {e}")

        state["city"] = city
        state["category_tag"] = category_tag

        return state

    # ---------------------------
    # Node 2: OSM search
    # ---------------------------
    async def osm_search_node(self, state: TravelAgentState) -> TravelAgentState:
        city = state.get("city", "")
        if not city:
            logger.warning("[TravelAgent] No city provided for OSM search")
            state["osm_results"] = []
            state["lat"] = None
            state["lon"] = None
            return state

        logger.info(f"[TravelAgent] Performing OSM search for city: {city!r}")

        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": city, "format": "json", "limit": 1}
        headers = {"User-Agent": "AgenticTravelBot/1.0 (contact@example.com)"}

        results = []
        lat, lon = None, None
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                results = r.json()
                if results:
                    lat = float(results[0].get("lat", 0))
                    lon = float(results[0].get("lon", 0))
        except httpx.RequestError as e:
            logger.warning(f"[TravelAgent] OSM request failed: {e}")
        except Exception as e:
            logger.exception(f"[TravelAgent] Unexpected error in OSM search: {e}")

        logger.info(f"[TravelAgent] OSM search results: {len(results)} items, lat={lat}, lon={lon}")
        state["osm_results"] = results
        state["lat"] = lat
        state["lon"] = lon
        return state

    # ---------------------------
    # Node 3: Fetch POIs
    # ---------------------------
    async def fetch_pois_node(self, state: TravelAgentState) -> TravelAgentState:
        user_msg = state["messages"][-1]
        query_text = str(getattr(user_msg, "content", "")).strip()

        match = re.search(r"(\d+)", query_text)
        top_n = int(match.group(1)) if match else 5

        lat = state.get("lat")
        lon = state.get("lon")
        category_tag = state.get("category_tag", "amenity")

        if lat is None or lon is None:
            state["pois"] = []
            state["top_n"] = top_n
            return state

        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:25];
        node(around:5000,{lat},{lon})[{category_tag}];
        out {top_n};
        """
        headers = {"User-Agent": "AgenticTravelBot/1.0 (contact@example.com)"}

        data = []
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                response = await client.get(overpass_url, params={"data": query})
                response.raise_for_status()
                payload = response.json()
                data = payload.get("elements", [])
        except httpx.RequestError as e:
            logger.warning(f"[TravelAgent] Overpass request failed: {e}")
        except Exception as e:
            logger.exception(f"[TravelAgent] Unexpected error fetching POIs: {e}")

        state["pois"] = data
        state["top_n"] = top_n
        return state

    # ---------------------------
    # Node 4: Format POIs
    # ---------------------------
    async def format_pois_node(self, state: TravelAgentState) -> TravelAgentState:
        lat = state.get("lat")
        lon = state.get("lon")
        category_tag = state.get("category_tag", "amenity")
        top_n = state.get("top_n", 5)
        pois = state.get("pois", [])

        if not lat or not lon:
            final_text = "*Aucun point d'intérêt trouvé (coordonnées manquantes).*"
        elif not pois:
            final_text = "*Aucun point d'intérêt trouvé. (catégorie manquante)*"
        else:
            md_output = f"## {top_n} POI les plus proches de {lat}, {lon} ({category_tag})\n\n"
            md_output += "| Nom | Lien OpenStreetMap |\n"
            md_output += "| --- | --- |\n"
            for e in pois[:top_n]:
                tags = e.get("tags", {})
                name = tags.get("name", "-")
                osm_url = f"https://www.openstreetmap.org/node/{e.get('id','')}"
                md_output += f"| {name} | [OSM]({osm_url}) |\n"
            final_text = md_output

        state["poi_markdown"] = final_text

        response = AIMessage(content=final_text)
        return {"messages": [response]}
