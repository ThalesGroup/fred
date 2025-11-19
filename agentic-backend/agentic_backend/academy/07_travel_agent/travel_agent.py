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

import logging
import os
import re
from typing import List, Optional, TypedDict

import httpx
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, Required

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


# ---------------------------
# Agent State
# ---------------------------
class TravelAgentState(TypedDict, total=False):
    # `messages` is always present in LangGraph MessagesState, so mark it as Required
    messages: Required[Annotated[List[AnyMessage], add_messages]]
    city: str
    category_tag: str
    lat: Optional[float]
    lon: Optional[float]
    osm_results: list
    pois: list
    top_n: int
    poi_markdown: str
    geo_error: Optional[str]


# ---------------------------
# Thought helper (for UI trace)
# ---------------------------
def mk_thought(*, label: str, node: str, content: str) -> AIMessage:
    """
    Emit an assistant-side 'thought' trace so the UI can show
    step-by-step progress (Thoughts accordion).
    """
    return AIMessage(
        content="",
        response_metadata={
            "thought": content,
            "extras": {"task": "travel", "node": node, "label": label},
        },
    )


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
    # Helpers
    # ---------------------------
    @staticmethod
    def _infer_category_tag(query_text: str) -> str:
        """
        Infer an Overpass filter expression from the natural language query.
        Returns a string like 'amenity=restaurant][\"diet:vegetarian\"=\"yes\"'.
        """
        text = query_text.lower()
        filters: List[str] = []

        # Base POI type
        if any(
            kw in text
            for kw in (
                "restaurant",
                "restaurants",
                "resto",
                "diner",
                "dîner",
                "food",
                "eat",
                "manger",
            )
        ):
            filters.append("amenity=restaurant")
        elif any(kw in text for kw in ("hotel", "hôtel", "stay", "hébergement")):
            filters.append("tourism=hotel")
        elif any(kw in text for kw in ("museum", "musée")):
            filters.append("tourism=museum")
        elif any(kw in text for kw in ("bar", "pub")):
            filters.append("amenity=bar")
        elif any(kw in text for kw in ("park", "parc", "garden", "jardin")):
            filters.append("leisure=park")
        else:
            # Generic tourism attractions as a safe default
            filters.append("tourism=attraction")

        # Dietary preferences
        if any(
            kw in text
            for kw in (
                "vegetarian",
                "végétarien",
                "végétariens",
                "végétarienne",
                "veggie",
            )
        ):
            # Keys with ':' must be quoted in Overpass QL.
            filters.append('"diet:vegetarian"="yes"')
        if any(kw in text for kw in ("vegan", "végane", "vegane")):
            filters.append('"diet:vegan"="yes"')

        # Overpass allows multiple [key=value] filters chained
        return "][".join(filters)

    @staticmethod
    def _http_headers() -> dict:
        ua = os.getenv(
            "TRAVEL_AGENT_USER_AGENT",
            "FredTravelAgent/1.0 (https://fredk8.dev; contact: dimitri.tombroff@thalesgroup.com)",
        )
        return {"User-Agent": ua}

    @staticmethod
    def _format_pois_markdown(
        lat: float, lon: float, category_tag: str, top_n: int, pois: list
    ) -> str:
        # Human-friendly summary instead of a technical header with raw coordinates.
        header_count = min(top_n, len(pois))
        if header_count > 0:
            md_output = f"Voici {header_count} lieux trouvés à proximité :\n\n"
        else:
            md_output = "Voici les lieux trouvés à proximité :\n\n"

        for e in pois[:top_n]:
            tags = e.get("tags", {})
            name = tags.get("name", "-")
            osm_url = f"https://www.openstreetmap.org/node/{e.get('id', '')}"
            md_output += f"- {name} — [Voir sur OpenStreetMap]({osm_url})\n"
        return md_output

    async def _fallback_llm_answer(self, state: "TravelAgentState") -> str:
        """
        Fallback when OSM/Overpass cannot provide POIs.
        Uses the configured system prompt to generate a textual answer.
        """
        sys_prompt = self.get_tuned_text("prompts.system") or (
            "You are a friendly travel guide. "
            "When map tools do not return data, still suggest some relevant places "
            "based on your general knowledge. Answer in French."
        )

        last_msg = state["messages"][-1]
        query_text = str(getattr(last_msg, "content", "")).strip()
        city = state.get("city") or "-"
        top_n = state.get("top_n", 5)

        user_prompt = (
            "Les outils de carte n'ont retourné aucun point d'intérêt pour cette requête.\n"
            f"Ville détectée : {city}.\n"
            f"Requête de l'utilisateur : {query_text}\n\n"
            f"Propose jusqu'à {top_n} lieux intéressants correspondant à cette demande, "
            "au format Markdown (liste à puces)."
        )

        try:
            response = await self.model.ainvoke(
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
            text = str(getattr(response, "content", "")).strip()
            return text or "*Je n'ai pas pu trouver de suggestions.*"
        except Exception as e:
            logger.warning(f"[TravelAgent] Fallback LLM answer failed: {e}")
            return "*Je n'ai pas pu trouver de suggestions.*"

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
        logger.info(
            f"[TravelAgent] Parsing city and category from query: {query_text!r}"
        )

        system_prompt = (
            "You are a travel assistant. "
            "Extract the city name mentioned in the user query. "
            "Return ONLY the city name as plain text. "
            "If you are not sure, return an empty string."
        )
        user_prompt = f"User query: {query_text}\nReturn: city name only."

        city = ""
        try:
            response = await self.model.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
            text = getattr(response, "content", "").strip()
            city = text.splitlines()[0].strip()
        except Exception as e:
            logger.warning(f"[TravelAgent] Failed to parse city name: {e}")

        category_tag = self._infer_category_tag(query_text)

        summary = (
            f"Requête comprise comme: ville='{city or 'inconnue'}', "
            f"filtre='{category_tag}'."
        )
        # IMPORTANT: return only the updated fields, not the full state,
        # so that `messages` are not replayed as new observations.
        return {
            "city": city,
            "category_tag": category_tag,
            "messages": [
                mk_thought(
                    label="parse_query",
                    node="parse_city_and_category",
                    content=summary,
                )
            ],
        }

    # ---------------------------
    # Node 2: OSM search
    # ---------------------------
    async def osm_search_node(self, state: TravelAgentState) -> TravelAgentState:
        city = state.get("city", "")
        if not city:
            logger.warning("[TravelAgent] No city provided for OSM search")
            return {
                "osm_results": [],
                "lat": None,
                "lon": None,
                # No city => simple thought, no new data
                "messages": [
                    mk_thought(
                        label="osm_search_skip",
                        node="osm_search",
                        content="Aucune ville détectée, géocodage ignoré.",
                    )
                ],
            }

        logger.info(f"[TravelAgent] Performing OSM search for city: {city!r}")

        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": city, "format": "json", "limit": 1}
        headers = self._http_headers()

        results = []
        lat, lon = None, None
        geo_error: Optional[str] = None
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                results = r.json()
                if results:
                    lat = float(results[0].get("lat", 0))
                    lon = float(results[0].get("lon", 0))
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.warning(f"[TravelAgent] OSM HTTP error {status}: {e}")
            if status == 403:
                geo_error = (
                    "Le service de géocodage OpenStreetMap (Nominatim) refuse l'accès "
                    "(erreur HTTP 403)."
                )
            else:
                geo_error = f"Le service de géocodage OpenStreetMap a renvoyé une erreur HTTP {status}."
        except httpx.RequestError as e:
            logger.warning(f"[TravelAgent] OSM request failed: {e}")
            geo_error = (
                "Le service de géocodage OpenStreetMap est temporairement inaccessible."
            )
        except Exception as e:
            logger.exception(f"[TravelAgent] Unexpected error in OSM search: {e}")
            geo_error = (
                "Une erreur inattendue est survenue lors de la recherche de la ville."
            )

        logger.info(
            f"[TravelAgent] OSM search results: {len(results)} items, lat={lat}, lon={lon}"
        )
        if geo_error:
            summary = f"Échec du géocodage pour '{city}': {geo_error}"
        elif lat is not None and lon is not None:
            summary = f"Géocodage réussi pour '{city}': lat={lat}, lon={lon}."
        else:
            summary = f"Aucune coordonnée trouvée pour '{city}'."

        return {
            "osm_results": results,
            "lat": lat,
            "lon": lon,
            "geo_error": geo_error,
            "messages": [
                mk_thought(label="osm_search", node="osm_search", content=summary)
            ],
        }

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
        category_tag = state.get("category_tag", "tourism=attraction")
        geo_error = state.get("geo_error")

        if lat is None or lon is None:
            return {
                "pois": [],
                "top_n": top_n,
                "messages": [
                    mk_thought(
                        label="fetch_pois_skip",
                        node="fetch_pois",
                        content="Coordonnées manquantes, aucune recherche de POI effectuée.",
                    )
                ],
            }

        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:25];
        node(around:5000,{lat},{lon})[{category_tag}];
        out {top_n};
        """
        headers = self._http_headers()

        data = []
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                response = await client.get(overpass_url, params={"data": query})
                response.raise_for_status()
                payload = response.json()
                data = payload.get("elements", [])
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.warning(f"[TravelAgent] Overpass HTTP error {status}: {e}")
            geo_error = (
                f"Le service de carte Overpass a renvoyé une erreur HTTP {status} "
                "lors de la recherche des points d'intérêt."
            )
        except httpx.RequestError as e:
            logger.warning(f"[TravelAgent] Overpass request failed: {e}")
            geo_error = "Le service de carte Overpass est temporairement inaccessible."
        except Exception as e:
            logger.exception(f"[TravelAgent] Unexpected error fetching POIs: {e}")
            geo_error = (
                "Une erreur inattendue est survenue lors de la récupération "
                "des points d'intérêt."
            )

        if geo_error:
            summary = f"Erreur Overpass lors de la recherche de POI: {geo_error}"
        else:
            summary = (
                f"Overpass a renvoyé {len(data)} POI candidats "
                f"(rayon 5km autour de {lat}, {lon})."
            )

        return {
            "pois": data,
            "top_n": top_n,
            "geo_error": geo_error,
            "messages": [
                mk_thought(label="fetch_pois", node="fetch_pois", content=summary)
            ],
        }

    # ---------------------------
    # Node 4: Format POIs
    # ---------------------------
    async def format_pois_node(self, state: TravelAgentState) -> TravelAgentState:
        lat = state.get("lat")
        lon = state.get("lon")
        category_tag = state.get("category_tag", "amenity")
        top_n = state.get("top_n", 5)
        pois = state.get("pois", [])
        geo_error = state.get("geo_error")

        if geo_error:
            fallback = await self._fallback_llm_answer(state)
            final_text = f"Attention : {geo_error}\n\n{fallback}"
        elif lat is None or lon is None:
            final_text = await self._fallback_llm_answer(state)
        elif not pois:
            final_text = await self._fallback_llm_answer(state)
        else:
            final_text = self._format_pois_markdown(
                lat=lat,
                lon=lon,
                category_tag=category_tag,
                top_n=top_n,
                pois=pois,
            )

        response = AIMessage(content=final_text)
        # Only emit the new assistant message (plus optional markdown),
        # never the full `messages` history.
        return {
            "poi_markdown": final_text,
            "messages": [response],
        }
