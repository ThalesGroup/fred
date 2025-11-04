# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");

import logging
from typing import Sequence, Tuple
import httpx
import requests

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import tool
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.simple_agent_flow import SimpleAgentFlow
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Non-MCP Tool: geocoding / streets
# ----------------------------------------------------------------------
@tool("geostreetmap.search")
def geostreetmap_search(q: str) -> dict:
    """
    Search a geocoding/streets endpoint using OpenStreetMap Nominatim.
    Returns JSON with candidates.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "limit": 5}
    r = httpx.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

# ----------------------------------------------------------------------
# Agent tuning / configuration
# ----------------------------------------------------------------------
TUNING = AgentTuning(
    role="travel_guide",
    description="Aide au voyageur : musées, monuments, restaurants, hôtels, etc.",
    tags=["tourism", "map", "free"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description="Définit la personnalité et le comportement de l’agent Travel.",
            required=True,
            default=(
                "You are a friendly travel guide. "
                "Use OpenStreetMap for real-time data. "
                "Fallback to LLM if no OSM data is found."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)

# ----------------------------------------------------------------------
# Travel Agent
# ----------------------------------------------------------------------
@expose_runtime_source("agent.Travel")
class Travel(SimpleAgentFlow):
    """
    Travel Agent avec workflow clair et MCP + outil non-MCP.
    """

    tuning = TUNING

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = get_default_chat_model()

    # --------------------------
    # Workflow principal
    # --------------------------
    async def arun(self, messages: Sequence[AnyMessage]) -> AIMessage:
        logger.debug(f"Travel.arun START. Input message count: {len(messages)}")
        tpl = self.get_tuned_text("prompts.system") or ""
        sys_prompt = self.render(tpl)

        llm_messages = self.with_system(sys_prompt, messages)
        llm_messages = self.with_chat_context_text(llm_messages)

        user_text = messages[-1].content if messages else ""

        # 1) MCP: LLM-assisted city & category extraction
        city, category_tag = await self._parse_city_and_category(user_text)
        logger.info(f"Detected: city='{city}', category='{category_tag}'")

        # 2) Non-MCP tool: geocoding via Nominatim
        coords = self._get_city_coords(city) if city else None

        # 3) Fetch POIs via Overpass API
        travel_response = ""
        if coords:
            lat, lon = coords
            travel_response = self._fetch_overpass_pois(lat, lon, category_tag)

        # 4) Fallback LLM si rien trouvé
        if not travel_response:
            try:
                response = await self.model.ainvoke(llm_messages)
                travel_response = self.ensure_aimessage(response).content
            except Exception as e:
                logger.error(f"Fallback LLM failed: {e}", exc_info=True)
                travel_response = "Désolé, je n'ai pas pu trouver d'informations."

        return AIMessage(content=travel_response)

    # --------------------------
    # MCP: city & category extraction
    # --------------------------
    async def _parse_city_and_category(self, prompt: str) -> Tuple[str, str]:
        """
        LLM parses city and OSM category from user query.
        Returns: (city, osm_tag)
        """
        system_prompt = (
            "You are a travel assistant. "
            "Extract city and OSM tag for Overpass API from user query. "
            "Return two values separated by comma: city name, osm tag."
        )
        user_prompt = f"User query: {prompt}\nReturn: city, osm_tag"

        try:
            response = await self.model.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
            text = response.content.strip()
            parts = [p.strip() for p in text.split(",")]
            if len(parts) == 2:
                return parts[0], parts[1]
        except Exception as e:
            logger.warning(f"MCP parsing failed: {e}")

        return "", "tourism"

    # --------------------------
    # Non-MCP: city geocoding
    # --------------------------
    def _get_city_coords(self, city: str) -> Tuple[float, float]:
        try:
            data = geostreetmap_search(city)
            if not data:
                return None
            loc = data[0]
            return float(loc["lat"]), float(loc["lon"])
        except Exception as e:
            logger.warning(f"Geocoding failed for {city}: {e}")
            return None

    # --------------------------
    # Fetch POIs from Overpass
    # --------------------------
    def _fetch_overpass_pois(self, lat: float, lon: float, category_tag: str) -> str:
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
            r = requests.get(overpass_url, params={"data": query}, headers={"User-Agent": "FRED-Travel-Agent"}, timeout=30)
            r.raise_for_status()
            data = r.json().get("elements", [])
        except Exception as e:
            logger.warning(f"Overpass API request failed: {e}")
            data = []

        if not data:
            return "*Aucun point d'intérêt trouvé ou erreur Overpass, mais voici ce qui a pu être récupéré.*\n\n" + md_output

        for e in data[:10]:
            try:
                tags = e.get("tags", {})

                # Site Web comme tag cliquable
                website_url = tags.get("website")
                if website_url:
                    website = f"[Site Web]({website_url})"
                else:
                    website = "-"

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

                # Assure que tous les champs sont des strings
                row = [str(x) if x is not None else "-" for x in row]
                md_output += "| " + " | ".join(row) + " |\n"

            except Exception as item_e:
                logger.warning(f"Failed to process element {e.get('id', 'unknown')}: {item_e}")
                continue

        return md_output
