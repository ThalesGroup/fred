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

import hashlib
import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional, Tuple, TypedDict

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
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

MAX_TOOL_MESSAGE_CHARS = int(os.getenv("ECO_MAX_TOOL_MESSAGE_CHARS", "4000"))
RECENT_MESSAGES_WINDOW = int(os.getenv("ECO_RECENT_MESSAGES", "12"))
MAX_TRIP_MEMORY = int(os.getenv("ECO_MAX_TRIP_MEMORY", "6"))


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
                "EcoAdvisor's operating instructions: guide the user to describe "
                "their trip, query tabular mobility datasets (CSV/Excel via MCP), "
                "estimate CO₂ impact and propose low-carbon alternatives."
            ),
            required=True,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
            default=(
                "You are **EcoAdvisor**, a mobility and CO₂ impact assistant.\n\n"
                "Your mission is to help users understand and reduce the carbon footprint "
                "of their daily trips (home ↔ work, regular commutes, etc.).\n\n"
                "### Persona utilisateur\n"
                "{persona_salarie_cnr}\n"
                "Always answer in the same language the user used (if unsure, default to French,"
                " and keep all follow-up questions in that language).\n\n"
                "### Data & Tools\n"
                "- You can access structured tabular datasets (CSV/Excel) via tools.\n"
                "- Typical datasets include:\n"
                "  - bike_infra_demo: bike lanes and infrastructure in the Rhône / Lyon area\n"
                "  - tcl_stops_demo: public transport stops (TCL) with coordinates and served lines\n"
                "- First, **list the available datasets and their schema** using the tools.\n"
                "- Then, select the relevant tables and run queries to inspect nearby bike lanes\n"
                "  and public transport options.\n\n"
                "### CO₂ Reference Service\n"
                "- Do NOT rely on hardcoded emission factors. Always call the MCP tools provided by the CO₂ reference service (`mcp-co2-service`).\n"
                "- `list_emission_modes` helps you discover all supported modes and their metadata.\n"
                "- `get_emission_factor` returns a single factor with `source` and `last_update` so you can cite the reference explicitly.\n"
                "- `compare_trip_modes` should be used when you know the distance and frequency: it returns a comparison payload (weekly emissions per mode) ready to transform into a Markdown table.\n"
                "- When the service is unavailable, fall back to the baseline assumptions (car 0.192 kg/km, TCL 0.01 kg/km, bike/walk 0 kg/km) and clearly state that you relied on the backup factors.\n\n"
                "### Géocodage & distances exactes\n"
                "- Utilise d’abord le tool `estimate_trip_between_addresses` (MCP `mcp-geo-service`) en lui passant les deux adresses textuelles fournies par l’utilisateur. Il renvoie directement la distance OSRM (km), la durée estimée et les coordonnées retenues.\n"
                "- Si tu as besoin d’affiner, `geocode_location` fournit plusieurs correspondances pour une adresse donnée (limite par défaut sur la France) et `compute_trip_distance` calcule ensuite la distance entre deux couples lat/lon.\n"
                '- Réutilise la distance retournée (km) pour tous les calculs CO₂ et cite-la explicitement dans le résumé/tableau. Si `source="haversine"`, précise qu’il s’agit d’une approximation faute de route routable.\n'
                "### Trafic routier en temps réel\n"
                "- When car usage is mentioned (current or alternative) or when congestion could change the recommendation, call the traffic MCP (`mcp-traffic-service`).\n"
                "- Use the `get_live_traffic_segments` tool with approximate coordinates (lat,lng) for the origin/destination (city centres are fine) to retrieve the latest WFS data from Grand Lyon.\n"
                '- Cite the traffic insight explicitly (e.g., "Grand Lyon WFS signale un trafic lourd Villefranche → Givors : 35 min estimées").\n\n'
                "### Informations TCL temps réel\n"
                "- Si l'utilisateur envisage les transports en commun TCL, identifie l'arrêt concerné dans les datasets tabulaires (colonnes `stop_id` et `stop_name`). `stop_id` correspond à l'identifiant TCL (`identifiantarret`) à transmettre ensuite au service temps réel.\n"
                "- Appelle ensuite le MCP `mcp-tcl-service` via `get_tcl_realtime_passages` pour récupérer les passages à venir (ligne, destination, heure prévue). Utilise la valeur `stop_id` trouvée dans la table comme `stop_code`.\n"
                "- Lorsque tu lis `tcl_stops_demo`, récupère aussi `stop_lat` / `stop_lon` afin de pouvoir afficher l'arrêt sur la carte (GeoJSON).\n"
                "- Présente les résultats sous forme de liste ou petit tableau : `Ligne | Direction | Passage prévu | Dans X min` (heure locale HH:MM) afin que l'utilisateur visualise immédiatement la fréquence.\n"
                '- Ajoute une phrase de contexte (ex: "Prochains départs à République-Villeurbanne" ou "Données TCL actualisées à 12:34").\n'
                "- Lorsque plusieurs lignes existent, regroupe-les par ligne avant de donner les horaires pour limiter la verbosity.\n\n"
                "### Workflow\n"
                "1. Clarify the user's context:\n"
                "   - origin and destination (city or district is enough)\n"
                "   - main current mode of transport (car, bike, TCL, etc.)\n"
                "   - approximate one-way distance or time if available\n"
                "   - frequency (e.g., 5 days/week)\n"
                "2. Dès que des adresses complètes sont fournies, lance `estimate_trip_between_addresses` (ou, à défaut, `geocode_location` + `compute_trip_distance`) pour obtenir une distance fiable avant toute estimation d'émissions.\n"
                "3. Use tools to **list datasets and their schema**.\n"
                "4. Identify which tables are relevant (e.g., bike_infra_demo, tcl_stops_demo).\n"
                "5. Run SQL-like queries to:\n"
                "   - find long bike lanes near the origin/destination city\n"
                "   - find TCL stops in the same city or within a geographic area\n"
                "6. When relevant, fetch live traffic information to validate car commute feasibility (mention congestion in your answer).\n"
                "7. Based on distance and mode, estimate weekly CO₂ emissions using the factors above.\n"
                "8. Compare current mode vs alternatives (TCL, bike, walking if realistic).\n"
                "9. Produce a clear, concise **markdown summary** with:\n"
                "   - a short explanation in natural language\n"
                "   - a markdown table comparing modes and weekly CO₂\n"
                "   - explicit assumptions you made (distance, days/week, factors)\n\n"
                "### Vulgarisation CO₂\n"
                "- Après avoir affiché le total hebdomadaire en kg CO₂e, ajoute un bref passage `Équivalences quotidiennes` pour donner un ordre de grandeur.\n"
                "- Convertis systématiquement ce total en:\n"
                "  - heures d'aspirateur : 1 h (aspirateur 1 200 W, mix électrique UE 2023) ≈ 0,35 kg CO₂e\n"
                "  - jours de chauffage électrique d'une pièce de 20 m² : 1 jour (radiateur 1,5 kW pendant 8 h) ≈ 3,5 kg CO₂e\n"
                "- Arrondis ces équivalences au demi le plus proche (`≈ 2,5 h d'aspirateur`, `≈ 3 jours de chauffage`) et précise qu'il s'agit d'approximations.\n"
                "- Garde toujours la réponse technique chiffrée en kg CO₂e dans le tableau et le résumé.\n\n"
                "### Présentation UI\n"
                "- Structure ta réponse avec des sous-titres Markdown (`### Synthèse rapide`, `### Options détaillées`, `### Données & hypothèses`).\n"
                "- Mets en évidence les données ou ordres de grandeur critiques avec du gras limité (`**CO₂ actuel**`, `**Trafic impactant**`).\n"
                "- Reste concis: phrases courtes, pas de redites inutiles.\n"
                "- Utilise des pastilles couleurs via emoji standards pour qualifier les options: `🟢` (option bas carbone), `🟠` (point de vigilance), `🔴` (action à éviter). Ne dépasse jamais trois pastilles par réponse.\n"
                "- Ajoute au besoin des emojis transport (🚲, 🚗, 🚌, 🚶, etc ...) pour illustrer les options.\n"
                "- Termine les recommandations chiffrées par un tableau Markdown (colonnes `Mode | CO₂ hebdo | Hypothèses`) et ajoute un bloc `Hypothèses` en liste courte.\n"
                "- Fractionne les paragraphes en listes ou phrases courtes pour rester lisible dans l'UI.\n\n"
                "### Rules\n"
                "- ALWAYS base your conclusions on actual tool results when referring to datasets.\n"
                "- When addresses are given, ALWAYS call the geo tools before running CO₂ comparisons; do not invent distances.\n"
                "- NEVER invent columns or tables that do not exist in the schema.\n"
                "- Cite the CO₂ references by including the `source` and `last_update` returned by the emission tools.\n"
                "- Use markdown tables to present numeric comparisons.\n"
                "- If the user did not provide enough information (distance, frequency),\n"
                "  ask targeted follow-up questions before estimating CO₂.\n"
                "- If you are unsure about a detail, state your assumptions explicitly.\n\n"
                "Current date: {today}.\n\n"
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
                "**Persona : Salarié CNR (Compagnie Nationale du Rhône)**\n"
                "- **Domaines** : hydroélectricité, transport fluvial, aménagement territorial.\n"
                "- **Métiers clés** : ingénieurs énergie, techniciens maintenance, exploitants, pilotes fluviaux, logisticiens, écologues, chefs de projet RSE, juristes spécialisés.\n"
                "- **Diplômes** : BTS/DUT électrotechnique ou maintenance, écoles d’ingénieurs énergie/environnement (INSA Lyon, Grenoble INP, ENSEEIHT), certifications navigation rhodanienne.\n"
                "- **Compétences** : transition bas-carbone, biodiversité, réglementation eau/environnement, adaptabilité (astreintes, travail en équipe).\n"
                "- **Profil sociodémographique** : mix d’experts seniors hydro historiques et jeunes diplômés ENR, majorité CDI, efforts parité.\n"
                "- **Culture & valeurs** : engagement transition énergétique, ancrage territorial, partenariats collectivités.\n"
                "- **Enjeux actuels** : développement hydro/ENR, adaptation crues-sécheresses, innovation (smart grids, stockage énergie).\n"
            ),
        ),
    ],
    # EcoAdvisor utilise maintenant:
    # - le serveur MCP tabulaire (hérité de Tessa)
    # - un serveur MCP dédié aux facteurs CO₂ (mcp-co2-service)
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
        MCPServerRef(name="mcp-co2-service"),
        MCPServerRef(name="mcp-traffic-service"),
        MCPServerRef(name="mcp-tcl-service"),
        MCPServerRef(name="mcp-geo-service"),
    ],
)


class TripMemoryEntry(TypedDict, total=False):
    key: str
    origin_label: str
    destination_label: str
    origin_query: Optional[str]
    destination_query: Optional[str]
    distance_km: float
    duration_min: Optional[float]
    profile: str
    source: Optional[str]
    computed_at: Optional[str]
    message_id: Optional[str]


class EcoState(TypedDict, total=False):
    """
    State LangGraph pour EcoAdvisor.

    Fred rationale:
    - On garde le même shape que Tessa pour rester compatible avec les helpers génériques:
      * messages: historique multi-turn
      * database_context: info "quels datasets / tables sont accessibles ?"
    - On pourra enrichir plus tard (ex: champs structurés pour distance, mode...).
    """

    messages: Annotated[list[AnyMessage], add_messages]
    database_context: List[Dict[str, Any]]
    trip_memory: List[TripMemoryEntry]
    trip_memory_ids: List[str]


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
    def _maybe_parse_json(self, payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                return payload
        return payload

    def _tool_message_identity(self, message: ToolMessage) -> str:
        candidate = getattr(message, "id", None) or getattr(
            message, "tool_call_id", None
        )
        if candidate:
            return str(candidate)

        content = message.content
        if isinstance(content, str):
            raw = content
        else:
            try:
                raw = json.dumps(content, sort_keys=True)
            except Exception:
                raw = repr(content)

        digest_input = f"{message.name}:{raw}".encode("utf-8", errors="ignore")
        return hashlib.sha1(digest_input).hexdigest()

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_location_label(*values: Optional[str]) -> str:
        for value in values:
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed:
                    return trimmed
        return "Adresse non précisée"

    def _trip_entry_key(
        self,
        origin_label: str,
        destination_label: str,
        profile: Optional[str],
    ) -> str:
        normalized_profile = (profile or "").strip().lower()
        return "|".join(
            [
                origin_label.strip().lower(),
                destination_label.strip().lower(),
                normalized_profile,
            ]
        )

    def _trip_entry_from_tool_message(
        self, message: ToolMessage
    ) -> Optional[TripMemoryEntry]:
        if getattr(message, "name", "") != "estimate_trip_between_addresses":
            return None

        payload = self._maybe_parse_json(message.content)
        if not isinstance(payload, dict):
            return None

        distance_km = self._safe_float(payload.get("distance_km"))
        if distance_km is None:
            return None

        duration_min = self._safe_float(payload.get("duration_min"))
        origin = payload.get("origin") or {}
        destination = payload.get("destination") or {}
        profile = (payload.get("profile") or "").strip() or "driving"

        entry: TripMemoryEntry = {
            "origin_label": self._normalize_location_label(
                origin.get("label"), origin.get("query")
            ),
            "destination_label": self._normalize_location_label(
                destination.get("label"), destination.get("query")
            ),
            "origin_query": origin.get("query"),
            "destination_query": destination.get("query"),
            "distance_km": distance_km,
            "duration_min": duration_min,
            "profile": profile,
            "source": (payload.get("source") or "").strip() or None,
            "computed_at": payload.get("computed_at"),
        }
        entry["key"] = self._trip_entry_key(
            entry["origin_label"], entry["destination_label"], entry["profile"]
        )
        return entry

    def _update_trip_memory(
        self, state: EcoState
    ) -> Tuple[List[TripMemoryEntry], List[str]]:
        memory: List[TripMemoryEntry] = list(state.get("trip_memory") or [])
        processed_ids = list(state.get("trip_memory_ids") or [])
        processed_set = set(processed_ids)
        new_entries: List[TripMemoryEntry] = []

        for message in state.get("messages", []):
            if not isinstance(message, ToolMessage):
                continue
            entry = self._trip_entry_from_tool_message(message)
            if not entry:
                continue
            identity = self._tool_message_identity(message)
            if identity in processed_set:
                continue
            entry["message_id"] = identity
            new_entries.append(entry)
            processed_set.add(identity)

        if not new_entries:
            return memory, processed_ids

        updated_memory = list(memory)
        for entry in new_entries:
            key = entry.get("key")
            if key:
                updated_memory = [m for m in updated_memory if m.get("key") != key]
            updated_memory.append(entry)

        if MAX_TRIP_MEMORY > 0 and len(updated_memory) > MAX_TRIP_MEMORY:
            updated_memory = updated_memory[-MAX_TRIP_MEMORY:]

        processed_ids = [
            item.get("message_id") for item in updated_memory if item.get("message_id")
        ]

        state["trip_memory"] = updated_memory
        state["trip_memory_ids"] = processed_ids
        return updated_memory, processed_ids

    def _format_trip_memory(self, entries: List[TripMemoryEntry]) -> str:
        if not entries:
            return ""

        lines = [
            "### Mémoire des trajets\n",
            "Trajets déjà confirmés pendant cette conversation (réutilise-les si l'utilisateur y fait référence) :",
        ]
        for entry in entries:
            distance = entry.get("distance_km")
            distance_text = (
                f"{distance:.1f} km"
                if isinstance(distance, (int, float))
                else "distance inconnue"
            )
            duration = entry.get("duration_min")
            duration_text = ""
            if isinstance(duration, (int, float)):
                duration_text = f", ~{duration:.0f} min"
            source = entry.get("source")
            source_text = f" — source {source}" if source else ""
            origin_label = entry.get("origin_label", "Origine inconnue")
            destination_label = entry.get("destination_label", "Destination inconnue")
            profile = entry.get("profile") or "profil inconnu"
            lines.append(
                f"- {origin_label} → {destination_label} ({profile}, {distance_text}{duration_text}{source_text})"
            )

        return "\n".join(lines) + "\n\n"

    def _latest_tool_output(self, state: EcoState, tool_name: str) -> Any:
        """
        Récupère le dernier ToolMessage d'un tool donné.

        Fred rationale:
        - Permettrait de factoriser l'accès aux résultats (list datasets, query, etc.).
        - Non utilisé dans la v1, mais utile pour de futures post-analyses côté agent.
        """
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == tool_name:
                return self._maybe_parse_json(msg.content)
        return None

    def _format_context_for_prompt(self, database_context: List[Dict[str, Any]]) -> str:
        """
        Formatte la liste des bases / tables accessibles pour injection dans le prompt.

        Fred rationale:
        - On donne au LLM une vue synthétique des datasets disponibles
          → il n'a pas à "deviner" les noms de tables.
        """
        if not database_context:
            return "No databases or tables currently loaded.\n"

        parsed_context = self._maybe_parse_json(database_context)
        if isinstance(parsed_context, dict):
            parsed_context = [parsed_context]

        if not isinstance(parsed_context, list):
            logger.warning(
                "EcoAdvisor: unexpected database_context type: %s",
                type(parsed_context),
            )
            return "No databases or tables currently loaded.\n"

        lines = ["You currently have access to the following structured datasets:\n"]
        for entry in parsed_context:
            entry = self._maybe_parse_json(entry)
            if not isinstance(entry, dict):
                logger.warning(
                    "EcoAdvisor: skipping malformed database context entry: %r", entry
                )
                continue
            db = entry.get("database", "unknown_database")
            tables = entry.get("tables", [])
            lines.append(f"- Database: `{db}` with tables: {tables}")
        if len(lines) == 1:
            return "No databases or tables currently loaded.\n"
        return "\n".join(lines) + "\n\n"

    async def _ensure_database_context(self, state: EcoState) -> List[Dict[str, Any]]:
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

    def _extract_stop_features(
        self, payload: Any, max_points: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Build GeoJSON point features from tabular/tool payloads that contain TCL stops.
        """
        parsed = self._maybe_parse_json(payload)

        rows: List[Any] = []
        if isinstance(parsed, dict):
            for key in ("rows", "results", "data"):
                candidate = parsed.get(key)
                if isinstance(candidate, list):
                    rows = candidate
                    break
        elif isinstance(parsed, list):
            rows = parsed

        features: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            lat = self._safe_float(
                row.get("stop_lat")
                or row.get("lat")
                or row.get("latitude")
                or row.get("y")
            )
            lon = self._safe_float(
                row.get("stop_lon")
                or row.get("lon")
                or row.get("lng")
                or row.get("longitude")
                or row.get("x")
            )
            has_stop_label = any(
                key in row for key in ("stop_name", "stop_id", "stop_code", "nomarret", "arret")
            )
            if lat is None or lon is None or not has_stop_label:
                continue

            name = (
                row.get("stop_name")
                or row.get("nomarret")
                or row.get("arret")
                or row.get("name")
                or "Arrêt TCL"
            )

            props: Dict[str, Any] = {"name": str(name)}
            for key in ("stop_id", "stop_code", "ligne", "line", "destination", "platform"):
                if key in row and row[key] is not None:
                    props[key] = row[key]

            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": props,
                }
            )
            if len(features) >= max_points:
                break

        return features

    def _build_geo_part_from_recent_tools(self, state: EcoState) -> Optional[Dict[str, Any]]:
        """
        Convert recent tabular/TCL tool outputs into a GeoPart payload for the UI map.
        """
        for msg in reversed(state["messages"]):
            if not isinstance(msg, ToolMessage):
                continue
            tool_name = getattr(msg, "name", "") or ""
            if tool_name not in {"query", "read_query", "get_tcl_realtime_passages"}:
                continue
            features = self._extract_stop_features(msg.content)
            if features:
                return {
                    "type": "geo",
                    "geojson": {"type": "FeatureCollection", "features": features},
                    "popup_property": "name",
                    "fit_bounds": True,
                }
        return None

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

        trip_memory, trip_memory_ids = self._update_trip_memory(state)
        trip_memory_text = self._format_trip_memory(trip_memory)
        if trip_memory_text:
            system_text = f"{system_text}\n\n{trip_memory_text}"

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

            geo_part = self._build_geo_part_from_recent_tools(state)
            if geo_part:
                add_kwargs = getattr(response, "additional_kwargs", {}) or {}
                fred_parts = add_kwargs.get("fred_parts") or []
                fred_parts.append(geo_part)
                add_kwargs["fred_parts"] = fred_parts
                response.additional_kwargs = add_kwargs

            return {
                "messages": [response],
                "database_context": database_context,
                "trip_memory": trip_memory,
                "trip_memory_ids": trip_memory_ids,
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
                "trip_memory": trip_memory,
                "trip_memory_ids": trip_memory_ids,
            }
