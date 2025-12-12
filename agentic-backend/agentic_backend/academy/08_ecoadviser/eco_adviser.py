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

"""
EcoAdvisor — Agent Fred orienté écologie / mobilité bas carbone.

Fred rationale:
- Cet agent est volontairement simple et pédagogique.
- Il réutilise le même pattern que Tessa:
  - un noeud LLM "reasoner"
  - un noeud "tools" fourni par l'infrastructure MCP
- La différence n'est PAS dans la structure du graphe,
  mais dans:
  - le prompt système (orienté CO₂ / mobilité)
  - la façon dont on guide l'utilisation des outils tabulaires.
- Objectif v1: avoir un agent complet et stable pour la démo,
  quitte à séparer plus tard un noeud compute_co2 dédié.
"""

import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union

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
from agentic_backend.core.chatbot.chat_schema import GeoPart
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

MAX_TOOL_MESSAGE_CHARS = int(os.getenv("ECO_MAX_TOOL_MESSAGE_CHARS", "4000"))
RECENT_MESSAGES_WINDOW = int(os.getenv("ECO_RECENT_MESSAGES", "12"))
MAX_MAP_FEATURES = int(os.getenv("ECO_MAX_MAP_FEATURES", "60"))

DatabaseContextPayload = Union[List[Dict[str, Any]], Dict[str, Any], str, None]


# ---------------------------------------------------------------------------
# 1) Tuning: ce que l'UI peut éditer
# ---------------------------------------------------------------------------

ECO_TUNING = AgentTuning(
    role="Eco Mobility Advisor",
    description=(
        "Helps users understand and reduce the CO₂ impact of their daily trips, "
        "using structured mobility datasets (bike lanes, public transport stops, etc.)."
    ),
    tags=["eco", "mobility", "co2", "data"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "EcoAdvisor's operating instructions: gather trip context, query "
                "the MCP tools, summarize findings, and compute CO₂ guidance."
            ),
            required=True,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
            default=(
                "You are **EcoAdvisor**, a pragmatic mobility and CO₂ guide.\n"
                "- Work in the user's language.\n"
                "- Use MCP tools instead of guessing; cite the `source` / `refreshed_at` fields they return.\n"
                "- Any tool output with lat/lon must be turned into the map already rendered in the UI—just describe what it shows and avoid suggesting external mapping steps unless the user asks.\n"
                "- Summaries stay short: headings, bullet lists, one Markdown table `Mode | CO₂ hebdo | Hypothèses`, then the key assumptions and rough everyday equivalents (aspirateur, chauffage...).\n"
                "- If data is missing or a tool fails, say so and state the fallback factors you used instead of hallucinating.\n"
                "Current date: {today}."
            ),
        ),
        FieldSpec(
            key="persona_salarie_cnr",
            type="prompt",
            title="Persona — Salarié CNR",
            description="Profil utilisateur de référence pour contextualiser les recommandations.",
            required=False,
            ui=UIHints(group="Personas", multiline=True, markdown=True),
            default=(
                "**Persona : Salarié CNR**\n"
                "- Travaille dans l'énergie (hydro, logistique fluviale, maintenance).\n"
                "- Sensibilisé à la transition bas carbone mais cherche des conseils pratiques.\n"
                "- Mix bureau / terrain, trajets domicile-travail variés autour de Lyon."
            ),
        ),
    ],
    # EcoAdvisor utilise maintenant:
    # - le serveur MCP tabulaire (hérité de Tessa)
    # - un serveur MCP dédié aux facteurs CO₂ (mcp-co2-service)
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
        MCPServerRef(name="mcp-co2-service", optional=True),
        MCPServerRef(name="mcp-geo-service", optional=True),
        MCPServerRef(name="mcp-tcl-service", optional=True),
    ],
)


class EcoState(TypedDict):
    """
    State LangGraph pour EcoAdvisor.

    Fred rationale:
    - On garde le même shape que Tessa pour rester compatible avec les helpers génériques:
      * messages: historique multi-turn
      * database_context: info "quels datasets / tables sont accessibles ?"
    - On pourra enrichir plus tard (ex: champs structurés pour distance, mode...).
    """

    messages: Annotated[list[AnyMessage], add_messages]
    database_context: DatabaseContextPayload


@expose_runtime_source("agent.EcoAdvisor")
class EcoAdvisor(AgentFlow):
    """
    EcoAdvisor — Agent Fred spécialisé mobilité / CO₂, basé sur le pattern Tessa.

    Pattern commun Fred:
    - Class-level `tuning` (décrit l'agent, les prompts éditables, les MCP liés).
    - __init__ minimal: on stocke les settings et on instancie MCPRuntime.
    - async_init():
      - récupère un modèle par défaut
      - initialise le runtime MCP (connexion au server tabulaire)
      - bind les tools au modèle
      - construit le graphe LangGraph
    - _build_graph():
      - noeud LLM `reasoner`
      - noeuds tools (délégués à MCPRuntime)
      - boucle reasoner <-> tools contrôlée par tools_condition
    """

    tuning = ECO_TUNING

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)
        # Runtime MCP partagé avec Tessa: même principe, agent différent.
        self.mcp = MCPRuntime(agent=self)

    # -----------------------------------------------------------------------
    # Bootstrap: modèle + MCP + graphe
    # -----------------------------------------------------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        # Modele "par défaut" de Fred pour le chat (fourni par la factory centrale).
        self.model = get_default_chat_model()

        # Démarre la stack MCP tabulaire (client JSON-RPC, discovery des tools, etc.).
        await self.mcp.init()

        # On bind les tools MCP directement au modèle:
        # cela permet au LLM d'appeler des tools "nativement" via l'OpenAI tool-calling.
        self.model = self.model.bind_tools(self.mcp.get_tools())

        # Construction du graphe LangGraph pour cet agent.
        self._graph = self._build_graph()

    async def aclose(self):
        # Fred rationale:
        # - EcoAdvisor, comme Tessa, possède un runtime MCP à fermer proprement.
        await self.mcp.aclose()

    # -----------------------------------------------------------------------
    # Helpers MCP / contexte tabulaire
    # -----------------------------------------------------------------------
    def _format_context_for_prompt(self, database_context: DatabaseContextPayload) -> str:
        entries = self._normalize_context_entries(database_context)
        if not entries:
            return ""

        lines = ["Available datasets:"]
        for entry in entries:
            db = entry.get("database") or entry.get("db_name") or "unknown"
            tables = ", ".join(self._extract_table_names(entry.get("tables")))
            lines.append(f"- {db}: {tables or 'no visible tables'}")
        return "\n".join(lines) + "\n\n"

    def _normalize_context_entries(
        self, context: DatabaseContextPayload
    ) -> List[Dict[str, Any]]:
        payload = self._maybe_parse_json(context)
        if isinstance(payload, dict):
            return [
                {"database": db_name, "tables": tables}
                for db_name, tables in payload.items()
            ]
        if isinstance(payload, list):
            out = []
            for entry in payload:
                parsed = self._maybe_parse_json(entry)
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out
        if payload:
            return [{"database": "unknown", "tables": payload}]
        return []

    @staticmethod
    def _extract_table_names(tables: Any) -> List[str]:
        if isinstance(tables, dict):
            return list(tables.keys())
        if isinstance(tables, list):
            names = []
            for item in tables:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    names.append(
                        item.get("table_name")
                        or item.get("name")
                        or item.get("table")
                        or "table"
                    )
            return names
        if isinstance(tables, str):
            return [tables]
        return []

    @staticmethod
    def _maybe_parse_json(payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                return payload
        return payload

    async def _ensure_database_context(self, state: EcoState) -> DatabaseContextPayload:
        """
        Charge la liste des bases/tables disponibles via un tool MCP (ex: get_context).

        Fred rationale:
        - L'agent n'a pas besoin de connaître la config de Knowledge Flow.
        - Il suffit d'interroger MCP une fois et de garder le résultat en cache
          dans l'état du graphe.
        """
        if state.get("database_context"):
            return state["database_context"]

        logger.info("EcoAdvisor: fetching database context via MCP (get_context)...")
        try:
            tools = self.mcp.get_tools()
            tool = next((t for t in tools if t.name == "get_context"), None)
            if not tool:
                logger.warning(
                    "EcoAdvisor: unable to find tool 'get_context' in MCP server."
                )
                return []

            raw_context = await tool.ainvoke({})

            context = (
                json.loads(raw_context) if isinstance(raw_context, str) else raw_context
            )

            state["database_context"] = context
            return context

        except Exception as e:
            logger.warning(f"EcoAdvisor: could not load database context: {e}")
            return []

    # -----------------------------------------------------------------------
    # 2) Construction du graphe LangGraph
    # -----------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        """
        Graphe minimal:
        - 'reasoner' = noeud LLM
        - 'tools'    = noeud MCP (les tools eux-mêmes)
        - boucle reasoner → tools → reasoner tant que tools_condition le demande.

        Fred rationale:
        - Même pattern que Tessa: on obtient un comportement agentique
          (tool-calling, itérations) sans complexité inutile.
        - Si on veut ajouter un noeud `compute_co2` dédié plus tard,
          on pourra intercaler ce noeud entre reasoner et la réponse finale.
        """
        builder = StateGraph(EcoState)

        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", self.mcp.get_tool_nodes())

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges("reasoner", tools_condition)
        builder.add_edge("tools", "reasoner")

        return builder

    def _truncate_tool_message(self, message: ToolMessage) -> ToolMessage:
        """
        Limit the amount of tool output we send back to the LLM to keep the
        conversation under the model's context window.
        """
        if MAX_TOOL_MESSAGE_CHARS <= 0:
            return message

        content = message.content
        if isinstance(content, str):
            serialized = content
        else:
            try:
                serialized = json.dumps(content, ensure_ascii=False)
            except Exception:
                serialized = str(content)

        if len(serialized) <= MAX_TOOL_MESSAGE_CHARS:
            return message

        trimmed = serialized[:MAX_TOOL_MESSAGE_CHARS]
        trimmed += (
            f"... [EcoAdvisor truncated {len(serialized) - MAX_TOOL_MESSAGE_CHARS} "
            f"chars from tool '{message.name or 'tool'}']"
        )
        logger.info(
            "EcoAdvisor truncated tool output for %s from %s chars to %s chars",
            message.name or "tool",
            len(serialized),
            MAX_TOOL_MESSAGE_CHARS,
        )
        return ToolMessage(
            content=trimmed,
            name=message.name or "tool",
            tool_call_id=(message.tool_call_id or ""),
            additional_kwargs=getattr(message, "additional_kwargs", {}),
            id=getattr(message, "id", None),
        )

    def _compact_messages_for_llm(self, messages: List[AnyMessage]) -> List[AnyMessage]:
        return [
            self._truncate_tool_message(msg) if isinstance(msg, ToolMessage) else msg
            for msg in messages
        ]

    # -----------------------------------------------------------------------
    #  Helper: map rendering
    # -----------------------------------------------------------------------
    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _maybe_build_geo_part_from_tools(
        self, tool_payloads: Dict[str, Any]
    ) -> Optional[GeoPart]:
        """
        Convert any tool payload containing lat/lon info into a GeoPart so the UI can render maps.
        """

        features: List[Dict[str, Any]] = []

        def _extract_feature(entry: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
            geometry = entry.get("geometry")
            if isinstance(geometry, dict):
                coords = geometry.get("coordinates")
                if (
                    geometry.get("type") == "Point"
                    and isinstance(coords, (list, tuple))
                    and len(coords) >= 2
                ):
                    lon = self._safe_float(coords[0])
                    lat = self._safe_float(coords[1])
                    if lat is not None and lon is not None:
                        return {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [lon, lat]},
                            "properties": _build_properties(entry, source),
                        }

            lon = (
                entry.get("lon")
                or entry.get("longitude")
                or entry.get("lng")
                or entry.get("x")
            )
            lat = entry.get("lat") or entry.get("latitude") or entry.get("y")
            lat_val = self._safe_float(lat)
            lon_val = self._safe_float(lon)
            if lat_val is None or lon_val is None:
                return None
            return {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon_val, lat_val]},
                "properties": _build_properties(entry, source),
            }

        def _build_properties(entry: Dict[str, Any], source: str) -> Dict[str, Any]:
            candidates = [
                entry.get("name"),
                entry.get("label"),
                entry.get("stop_id"),
                entry.get("id"),
            ]
            name = next((value for value in candidates if isinstance(value, str) and value.strip()), None)
            properties: Dict[str, Any] = {
                "name": name or f"Point ({source})",
                "source": entry.get("source") or source,
            }
            optional_keys = [
                "stop_id",
                "city",
                "district",
                "zone",
                "lines",
                "distance_m",
                "line",
                "mode",
                "label",
            ]
            for key in optional_keys:
                value = entry.get(key)
                if value in (None, "", []):
                    continue
                if key == "lines" and isinstance(value, list):
                    properties[key] = ", ".join(str(v) for v in value)
                elif key == "distance_m":
                    try:
                        properties[key] = round(float(value), 1)
                    except (TypeError, ValueError):
                        continue
                else:
                    properties[key] = value
            return properties

        def _collect(payload: Any, source: str):
            if len(features) >= MAX_MAP_FEATURES:
                return
            if isinstance(payload, dict):
                feature = _extract_feature(payload, source)
                if feature:
                    features.append(feature)
                    if len(features) >= MAX_MAP_FEATURES:
                        return
                for key in (
                    "results",
                    "items",
                    "data",
                    "records",
                    "features",
                    "points",
                ):
                    nested = payload.get(key)
                    if isinstance(nested, (list, tuple)):
                        for item in nested:
                            _collect(item, source)
                    elif isinstance(nested, dict):
                        _collect(nested, source)
                if "origin_lat" in payload and "origin_lon" in payload:
                    lat = self._safe_float(payload.get("origin_lat"))
                    lon = self._safe_float(payload.get("origin_lon"))
                    if lat is not None and lon is not None:
                        features.append(
                            {
                                "type": "Feature",
                                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                                "properties": {
                                    "name": "Point de référence",
                                    "source": source,
                                },
                            }
                        )
            elif isinstance(payload, (list, tuple)):
                for item in payload:
                    _collect(item, source)

        for tool_name, payload in tool_payloads.items():
            _collect(payload, tool_name)
            if len(features) >= MAX_MAP_FEATURES:
                break

        if not features:
            return None

        return GeoPart(
            geojson={"type": "FeatureCollection", "features": features},
            popup_property="name",
            fit_bounds=True,
        )

    # -----------------------------------------------------------------------
    # 3) Noeud LLM principal
    # -----------------------------------------------------------------------
    async def reasoner(self, state: EcoState):
        """
        Noeud LLM principal d'EcoAdvisor.

        Fred rationale:
        - C'est ici que l'on applique le prompt système "éco/mobilité".
        - On enrichit ce prompt avec le contexte des datasets accessibles.
        - On laisse le modèle choisir:
          - quand appeler les tools MCP (list, schema, query)
          - quand passer à la formulation des recommandations CO₂.
        """

        if self.model is None:
            raise RuntimeError(
                "EcoAdvisor: model is not initialized. Call async_init() first."
            )

        # 1) Récupérer le prompt système tunable (via YAML/UI)
        tpl = self.get_tuned_text("prompts.system") or ""

        # 2) Charger / mettre à jour le contexte des bases/tabulaires
        database_context = await self._ensure_database_context(state)
        tpl += self._format_context_for_prompt(database_context)
        system_text = self.render(tpl)

        # 3) Construire l'historique de conversation minimal
        recent_history = self.recent_messages(
            state["messages"], max_messages=max(RECENT_MESSAGES_WINDOW, 1)
        )
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)
        messages = self._compact_messages_for_llm(messages)

        try:
            # 4) LLM + tool-calling: le modèle peut décider d'appeler MCP ou non
            response = await self.model.ainvoke(messages)

            # 5) Injecter dans les metadata les payloads des tools déjà appelés
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
            geo_part = self._maybe_build_geo_part_from_tools(tool_payloads)
            if geo_part:
                add_kwargs = getattr(response, "additional_kwargs", None)
                if add_kwargs is None or not isinstance(add_kwargs, dict):
                    add_kwargs = {}
                    response.additional_kwargs = add_kwargs
                fred_parts = add_kwargs.get("fred_parts")
                if not isinstance(fred_parts, list):
                    fred_parts = []
                fred_parts.append(geo_part.model_dump())
                add_kwargs["fred_parts"] = fred_parts

            return {
                "messages": [response],
                "database_context": database_context,
            }

        except Exception:
            logger.exception("EcoAdvisor failed during reasoning.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content=(
                            "An error occurred while analyzing mobility data. "
                            "Please try again or simplify your question."
                        )
                    )
                ]
            )
            return {
                "messages": [fallback],
                "database_context": [],
            }
