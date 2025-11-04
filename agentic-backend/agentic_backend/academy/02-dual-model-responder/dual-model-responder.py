# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");

import logging
from typing import Any, Dict, Sequence, Tuple
import httpx
import requests
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import Tool

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

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


@expose_runtime_source("agent.Travel")
class Travel(AgentFlow):
    tuning = TRAVEL_TUNING

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = None
        self._tools: Dict[str, Tool] = {}

    # ---------------------------
    # Async init
    # ---------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()

        # Créer les outils comme Tool objects
        self._tools = {
            "geostreetmap.search": Tool.from_function(
                self.geostreetmap_search, name="geostreetmap.search"
            ),
            "format_osm_md": Tool.from_function(
                self.format_osm_md, name="format_osm_md"
            ),
        }

        # Construire le graph
        self._graph = self._build_graph()

    # ---------------------------
    # Graph
    # ---------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", ToolNode(tools=self._tools))
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")
        return builder

    # ---------------------------
    # Tools
    # ---------------------------
    async def geostreetmap_search(self, q: str) -> Any:
        """OpenStreetMap geocoding."""
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": q, "format": "json", "limit": 5}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()

    async def format_osm_md(self, lat: float, lon: float, category_tag: str) -> str:
        """Fetch POIs from Overpass API and return markdown table."""
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:60];
        node(around:5000,{lat},{lon})[{category_tag}];
        out;
        """
        md_output = f"## Points d'intérêt autour de {lat}, {lon} ({category_tag})\n\n"
        headers = [
            "Nom", "Numéro", "Rue", "Code Postal", "Ville",
            "Catégorie", "Cuisine", "Téléphone", "Site Web", "Lien OpenStreetMap"
        ]
        md_output += "| " + " | ".join(headers) + " |\n"
        md_output += "| " + " | ".join(["---"] * len(headers)) + " |\n"

        try:
            r = requests.get(
                overpass_url,
                params={"data": query},
                headers={"User-Agent": "FRED-Travel-Agent"},
                timeout=30
            )
            r.raise_for_status()
            data = r.json().get("elements", [])
        except Exception as e:
            logger.warning(f"Overpass API request failed: {e}")
            data = []

        if not data:
            return "*Aucun point d'intérêt trouvé.*\n\n" + md_output

        for e in data[:10]:
            try:
                tags = e.get("tags", {})
                website_url = tags.get("website")
                website = f"[Site Web]({website_url})" if website_url else "-"
                row = [
                    tags.get("name", "-"),
                    tags.get("addr:housenumber", "-"),
                    tags.get("addr:street", "-"),
                    tags.get("addr:postcode", "-"),
                    tags.get("addr:city", "-"),
                    tags.get("amenity", tags.get("tourism", tags.get("shop", "-"))),
                    tags.get("cuisine", "-"),
                    tags.get("phone", "-"),
                    website,
                    f"[OSM](https://www.openstreetmap.org/node/{e.get('id','')})"
                ]
                row = [str(x) if x is not None else "-" for x in row]
                md_output += "| " + " | ".join(row) + " |\n"
            except Exception as item_e:
                logger.warning(f"Failed to process element {e.get('id', 'unknown')}: {item_e}")
                continue

        return md_output

    # ---------------------------
    # Reasoner Node
    # ---------------------------
    async def reasoner(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError("TravelAgent: model not initialized")

        tpl = self.get_tuned_text("prompts.system") or ""
        system_text = self.render(tpl)
        messages = self.with_system(system_text, state["messages"])
        messages = self.with_chat_context_text(messages)

        try:
            response = await self.model.ainvoke(messages)

            # Collect tool outputs
            tool_payloads: Dict[str, Any] = {}
            for msg in state["messages"]:
                name = getattr(msg, "name", None)
                if isinstance(msg, ToolMessage) and isinstance(name, str):
                    raw = msg.content
                    normalized: Any = raw
                    if isinstance(raw, str):
                        try:
                            normalized = json.loads(raw)
                        except Exception:
                            normalized = raw
                    tool_payloads[name] = normalized

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
            logger.exception("TravelAgent: unexpected error")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred in TravelAgent. Please try again.")]
            )
            return {"messages": [fallback]}
