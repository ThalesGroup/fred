# travel_agent.py

import logging
import httpx
import re
from typing import Optional, List
from typing_extensions import Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.runtime_source import expose_runtime_source
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ---------------------------
# Agent Tuning
# ---------------------------
TRAVEL_TUNING = AgentTuning(
    role="travel-guide",
    description="Travel agent simple using Overpass API",
    tags=["travel", "osm"],
    fields=[]
)

# ---------------------------
# State
# ---------------------------
class TravelState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], add_messages]
    city: str
    category_tag: str
    lat: Optional[float]
    lon: Optional[float]
    pois: List[dict]
    poi_markdown: str

# ---------------------------
# Agent
# ---------------------------
@expose_runtime_source("agent.Travel")
class Travel(AgentFlow):
    tuning = TRAVEL_TUNING
    _graph: Optional[StateGraph] = None

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self._graph = self._build_graph()

    # ---------------------------
    # Graph definition
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(TravelState)

        builder.add_node("parse_city", self.parse_city_node)
        builder.add_node("osm_search", self.osm_search_node)
        builder.add_node("fetch_pois", self.fetch_pois_node)
        builder.add_node("format", self.format_node)

        builder.add_edge(START, "parse_city")
        builder.add_edge("parse_city", "osm_search")
        builder.add_edge("osm_search", "fetch_pois")
        builder.add_edge("fetch_pois", "format")
        builder.add_edge("format", END)

        return builder

    # ---------------------------
    # Node 1 - extract city + category
    # ---------------------------
    async def parse_city_node(self, state: TravelState):
        msg = state["messages"][-1].content.lower()

        categories = ["restaurant", "cafe", "bar", "hotel", "museum", "park"]
        category = "tourism"
        city = msg
        for cat in categories:
            if cat in msg:
                category = cat
                city = msg.replace(cat, "").strip()
                break

        logger.info(f"[Parse] city={city}, cat={category}")

        state["city"] = city.title()
        state["category_tag"] = category
        return state

    # ---------------------------
    # Node 2 - OSM search
    # ---------------------------
    async def osm_search_node(self, state: TravelState):
        city = state.get("city", "")
        if not city:
            return state

        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": city, "format": "json", "limit": 1}
        logger.info(f"[OSM] Searching: {city}")

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            data = r.json()
            if data:
                state["lat"] = float(data[0]["lat"])
                state["lon"] = float(data[0]["lon"])
            else:
                state["lat"] = state["lon"] = None

        return state

    # ---------------------------
    # Node 3 - Fetch POIs
    # ---------------------------
    async def fetch_pois_node(self, state: TravelState):
        lat = state.get("lat")
        lon = state.get("lon")
        cat = state.get("category_tag", "tourism")

        if not lat or not lon:
            state["pois"] = []
            return state

        mapping = {
            "restaurant": ("amenity", "restaurant"),
            "cafe": ("amenity", "cafe"),
            "bar": ("amenity", "bar"),
            "hotel": ("tourism", "hotel"),
            "museum": ("tourism", "museum"),
            "park": ("leisure", "park"),
            "tourism": ("tourism", "attraction"),
        }

        key, value = mapping.get(cat, ("tourism", "attraction"))

        query = f"""
        [out:json][timeout:5];
        node(around:500,{lat},{lon})[{key}={value}];
        out 3;
        """

        url = "https://lz4.overpass-api.de/api/interpreter"
        logger.info(f"[POI] Fetching {cat} @ {lat},{lon}")

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"data": query})
            payload = r.json()
            state["pois"] = payload.get("elements", [])

        return state

    # ---------------------------
    # Node 4 - Format Markdown
    # ---------------------------
    async def format_node(self, state: TravelState):
        pois = state.get("pois", [])
        if not pois:
            md = "*Aucun POI trouvé*"
        else:
            md = "| Nom | Lien OSM |\n| --- | --- |\n"
            for p in pois:
                name = p.get("tags", {}).get("name", "-")
                osm_url = f"https://www.openstreetmap.org/node/{p['id']}"
                md += f"| {name} | [OSM]({osm_url}) |\n"

        state["poi_markdown"] = md
        return {"messages": [AIMessage(content=md)]}
