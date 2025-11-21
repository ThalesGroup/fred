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
import re
import unicodedata
from typing import Annotated, Any, Dict, List, NotRequired, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langgraph.constants import END, START
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

FALLBACK_EMISSION_FACTORS = {
    "voiture": 0.192,  # kg CO₂/km – ADEME (démo simplifiée)
    "tcl": 0.01,
    "velo": 0.0,
}
MODE_KEYWORDS = {
    "voiture": ("voiture", "auto", "car", "covoiturage", "voitures", "vehicule"),
    "tcl": (
        "tcl",
        "bus",
        "tram",
        "metro",
        "métro",
        "train",
        "rer",
        "transport en commun",
        "transports en commun",
        "tc",
    ),
    "velo": ("velo", "vélo", "bike", "bicyclette", "vtt"),
}
DISTANCE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:km|kilometres?)")
FREQUENCY_PATTERN = re.compile(
    r"(\d+)\s*(?:j|jour|jours|fois)\s*(?:/?\s*(?:par)?\s*(?:sem|semaine))?"
)
DAILY_KEYWORDS = ("quotidien", "quotidienne", "tous les jours", "chaque jour")
SERVICE_MODE_MAP = {
    "voiture": "car_thermal",
    "tcl": "public_transport",
    "velo": "bike",
}
SERVICE_MODE_LABELS = {
    "car_thermal": "Voiture",
    "public_transport": "TCL",
    "bike": "Vélo",
}
SERVICE_DISPLAY_ORDER = ["car_thermal", "public_transport", "bike"]


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
                "### Data & Tools\n"
                "- You can access structured tabular datasets (CSV/Excel) via tools.\n"
                "- Typical datasets include:\n"
                "  - bike_infra_demo: bike lanes and infrastructure in the Rhône / Lyon area\n"
                "  - tcl_stops_demo: public transport stops (TCL) with coordinates and served lines\n"
                "- First, **list the available datasets and their schema** using the tools.\n"
                "- Then, select the relevant tables and run queries to inspect nearby bike lanes\n"
                "  and public transport options.\n\n"
                "### CO₂ Reference Service (Étape 2)\n"
                "- Do NOT store emission factors in the prompt.\n"
                "- Use the dedicated tools (`list_emission_modes`, `get_emission_factor`, `compare_trip_modes`) "
                "provided by the CO₂ MCP server.\n"
                "- Always cite the `source` and `last_update` returned by the tool in your final answer.\n\n"
                "### Workflow\n"
                "1. Clarify the user's context:\n"
                "   - origin and destination (city or district is enough)\n"
                "   - main current mode of transport (car, bike, TCL, etc.)\n"
                "   - approximate one-way distance or time if available\n"
                "   - frequency (e.g., 5 days/week)\n"
                "2. Use tools to **list datasets and their schema**.\n"
                "3. Identify which tables are relevant (e.g., bike_infra_demo, tcl_stops_demo).\n"
                "4. Run SQL-like queries to:\n"
                "   - find long bike lanes near the origin/destination city\n"
                "   - find TCL stops in the same city or within a geographic area\n"
                "5. Based on distance and mode, estimate weekly CO₂ emissions using the factors above.\n"
                "6. Compare current mode vs alternatives (TCL, bike, walking if realistic).\n"
                "7. Produce a clear, concise **markdown summary** with:\n"
                "   - a short explanation in natural language\n"
                "   - a markdown table comparing modes and weekly CO₂\n"
                "   - explicit assumptions you made (distance, days/week, factors)\n\n"
                "### Rules\n"
                "- ALWAYS base your conclusions on actual tool results when referring to datasets.\n"
                "- NEVER invent columns or tables that do not exist in the schema.\n"
                "- Use markdown tables to present numeric comparisons.\n"
                "- If the user did not provide enough information (distance, frequency),\n"
                "  ask targeted follow-up questions before estimating CO₂.\n"
                "- If you are unsure about a detail, state your assumptions explicitly.\n\n"
                "### Mandatory Markdown Output (Étape 0)\n"
                "At the end of every answer you MUST append:\n"
                "1. A table with the columns `Mode | CO₂ / semaine | Hypothèses`.\n"
                "   The rows must be **Voiture**, **TCL**, **Vélo** (in that order).\n"
                "2. A bold heading `**Hypothèses** :` followed by the explicit assumptions\n"
                "   (distance, fréquence, facteurs utilisés).\n"
                "3. A bold heading `**Pistes bas carbone** :` followed by 2–3 actionable suggestions\n"
                "   tailored to the context.\n"
                "If distance/frequency are missing, ask before producing the table.\n\n"
                "Current date: {today}.\n\n"
            ),
        ),
    ],
    # EcoAdvisor utilise le même MCP server tabulaire que Tessa.
    # Fred rationale:
    # - On ne réinvente pas l'intégration back; on exploite la même passerelle MCP.
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
        MCPServerRef(name="mcp-co2-service"),
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
    database_context: List[Dict[str, Any]]
    distance_km: NotRequired[Optional[float]]
    frequency_days: NotRequired[Optional[int]]
    mode: NotRequired[Optional[str]]
    co2_payload: NotRequired[Optional[Dict[str, Any]]]


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

        lines = ["You currently have access to the following structured datasets:\n"]
        for entry in database_context:
            entry = self._maybe_parse_json(entry)
            db = entry.get("database", "unknown_database")
            tables = entry.get("tables", [])
            lines.append(f"- Database: `{db}` with tables: {tables}")
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
    # Helpers champs structurés / CO₂
    # -----------------------------------------------------------------------
    async def _invoke_tool(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        tools = self.mcp.get_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        if not tool:
            raise ValueError(f"EcoAdvisor: tool '{tool_name}' not available via MCP.")
        return await tool.ainvoke(payload)

    def _message_to_text(self, message: HumanMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            segments = []
            for block in content:
                if isinstance(block, dict):
                    segments.append(block.get("text") or "")
                else:
                    segments.append(str(block))
            return " ".join(segments)
        return str(content)

    def _normalize_text(self, text: str) -> str:
        lowered = text.lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _detect_mode(self, normalized_text: str) -> Optional[str]:
        for mode, keywords in MODE_KEYWORDS.items():
            if any(keyword in normalized_text for keyword in keywords):
                return mode
        return None

    def _extract_trip_hints(self, state: EcoState) -> Dict[str, Optional[Any]]:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                raw_text = self._message_to_text(message)
                normalized = self._normalize_text(raw_text)
                hints: Dict[str, Optional[Any]] = {}
                if match := DISTANCE_PATTERN.search(normalized):
                    try:
                        hints["distance_km"] = float(match.group(1).replace(",", "."))
                    except ValueError:
                        pass
                if match := FREQUENCY_PATTERN.search(normalized):
                    try:
                        hints["frequency_days"] = int(match.group(1))
                    except ValueError:
                        pass
                else:
                    if any(keyword in normalized for keyword in DAILY_KEYWORDS):
                        hints["frequency_days"] = 5
                if mode := self._detect_mode(normalized):
                    hints["mode"] = mode
                return hints
        return {}

    def _merge_trip_fields(
        self, state: EcoState, hints: Dict[str, Optional[Any]]
    ) -> Dict[str, Optional[Any]]:
        merged = {
            "distance_km": state.get("distance_km"),
            "frequency_days": state.get("frequency_days"),
            "mode": state.get("mode"),
        }
        for key, value in hints.items():
            if value is not None:
                merged[key] = value
        return merged

    def _service_mode(self, user_mode: Optional[str]) -> str:
        if not user_mode:
            return "car_thermal"
        return SERVICE_MODE_MAP.get(user_mode, "car_thermal")

    def _service_alternatives(self, current_service_mode: str) -> List[str]:
        return [m for m in SERVICE_DISPLAY_ORDER if m != current_service_mode]

    def _generate_suggestions(self, current_mode: Optional[str]) -> List[str]:
        suggestions: List[str] = []
        if current_mode != "tcl":
            suggestions.append(
                "Tester une combinaison TCL + marche pour réduire de 90 % les émissions."
            )
        if current_mode != "velo":
            suggestions.append(
                "Planifier 1 à 2 trajets hebdo à vélo lorsque la météo est clémente."
            )
        suggestions.append(
            "Optimiser le remplissage de la voiture (covoiturage) les jours où elle reste nécessaire."
        )
        return suggestions[:3]

    async def _compare_modes_via_mcp(
        self, distance_km: float, frequency_days: int, current_mode: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not self.mcp:
            return None
        current_service_mode = self._service_mode(current_mode)
        alternatives = self._service_alternatives(current_service_mode)
        daily_distance = round(max(distance_km, 0.0) * 2.0, 3)
        try:
            raw = await self._invoke_tool(
                "compare_trip_modes",
                {
                    "distance_km": daily_distance,
                    "frequency_days_per_week": frequency_days,
                    "current_mode": current_service_mode,
                    "alternatives": alternatives,
                    "weeks_per_year": 47,
                },
            )
            comparison = self._maybe_parse_json(raw)
            if isinstance(comparison, dict) and comparison.get("ok"):
                comparison["_daily_distance_km"] = daily_distance
                comparison["_service_current_mode"] = current_service_mode
                return comparison
        except Exception:
            logger.exception("EcoAdvisor: compare_trip_modes tool call failed.")
        return None

    def _collate_service_entries(self, comparison: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        entries: Dict[str, Dict[str, Any]] = {}
        for entry in [comparison.get("current")] + comparison.get("alternatives", []):
            if isinstance(entry, dict) and entry.get("mode"):
                entries[entry["mode"]] = entry
        return entries

    def _build_service_table(
        self,
        comparison: Dict[str, Any],
        frequency_days: int,
    ) -> str:
        entries = self._collate_service_entries(comparison)
        rows = ["| Mode | CO₂ / semaine | Hypothèses |", "| --- | --- | --- |"]
        for service_mode in SERVICE_DISPLAY_ORDER:
            entry = entries.get(service_mode)
            label = SERVICE_MODE_LABELS.get(service_mode, service_mode)
            if not entry:
                rows.append(f"| {label} | n.d. | Facteur indisponible |")
                continue
            weekly = float(entry.get("weekly_kg_co2", 0.0))
            factor = float(entry.get("factor_kg_per_km", 0.0))
            per_day = float(entry.get("distance_km_per_day", comparison.get("_daily_distance_km", 0.0)))
            freq = int(entry.get("frequency_days_per_week", frequency_days))
            rows.append(
                f"| {label} | {weekly:.2f} kg | {per_day:.1f} km/j x {freq} j x {factor:.3f} kg/km |"
            )
        return "\n".join(rows)

    def _sources_from_comparison(self, comparison: Dict[str, Any]) -> List[str]:
        entries = self._collate_service_entries(comparison)
        sources = set()
        for entry in entries.values():
            source = entry.get("source")
            update = entry.get("last_update")
            if source:
                label = entry.get("label") or SERVICE_MODE_LABELS.get(entry.get("mode"), entry.get("mode"))
                sources.add(f"{label} — {source} (maj {update})")
        return sorted(sources)

    def _generate_service_suggestions(
        self,
        comparison: Dict[str, Any],
        current_service_mode: str,
    ) -> List[str]:
        suggestions: List[str] = []
        savings = comparison.get("savings") or []
        positive_savings = [
            s for s in savings if s.get("delta_yearly_kg_co2", 0) > 0
        ]
        if positive_savings:
            best = max(positive_savings, key=lambda s: s["delta_yearly_kg_co2"])
            best_mode = best.get("to_mode")
            label = SERVICE_MODE_LABELS.get(best_mode, best_mode)
            delta = best.get("delta_yearly_kg_co2", 0.0)
            suggestions.append(
                f"Basculer vers {label} permettrait d'éviter environ {delta:.1f} kg CO₂/an."
            )
        if current_service_mode != "bike":
            suggestions.append(
                "Planifier quelques trajets à vélo ou vélo + TCL pour réduire encore les émissions."
            )
        suggestions.append(
            "S'appuyer sur les facteurs officiels ADEME (via le service CO₂) pour suivre les progrès."
        )
        return suggestions[:3]

    def _build_service_payload(
        self,
        comparison: Dict[str, Any],
        distance_km: float,
        frequency_days: int,
        suggestions: List[str],
    ) -> Dict[str, Any]:
        table_markdown = self._build_service_table(comparison, frequency_days)
        sources = self._sources_from_comparison(comparison)
        daily_distance = comparison.get("_daily_distance_km", distance_km * 2)
        assumptions = (
            f"{distance_km:.1f} km aller ({daily_distance:.1f} km AR), "
            f"{frequency_days} jours/semaine. Facteurs fournis par le service CO₂."
        )
        if sources:
            assumptions += f" Sources: {', '.join(sources)}."
        return {
            "table_markdown": table_markdown,
            "assumptions": assumptions,
            "suggestions": suggestions,
            "weekly_distance_km": daily_distance * frequency_days / 2,
            "distance_km": distance_km,
            "frequency_days": frequency_days,
        }

    def _build_co2_payload(
        self,
        distance_km: float,
        frequency_days: int,
        current_mode: Optional[str],
    ) -> Dict[str, Any]:
        weekly_distance = round(distance_km * 2 * frequency_days, 2)
        rows = ["| Mode | CO₂ / semaine | Hypothèses |", "| --- | --- | --- |"]
        for label, key in (("Voiture", "voiture"), ("TCL", "tcl"), ("Vélo", "velo")):
            factor = FALLBACK_EMISSION_FACTORS[key]
            emission = round(weekly_distance * factor, 2)
            rows.append(
                f"| {label} | {emission:.2f} kg | {weekly_distance:.1f} km x {factor:.3f} kg/km |"
            )
        table_markdown = "\n".join(rows)
        assumptions = (
            f"{distance_km:.1f} km aller, {frequency_days} jours/semaine, "
            "2 trajets quotidiens."
        )
        suggestions = self._generate_suggestions(current_mode)
        return {
            "table_markdown": table_markdown,
            "assumptions": assumptions,
            "suggestions": suggestions,
            "weekly_distance_km": weekly_distance,
            "distance_km": distance_km,
            "frequency_days": frequency_days,
        }

    # -----------------------------------------------------------------------
    # 2) Construction du graphe LangGraph
    # -----------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        """
        Graphe structuré :
        - reasoner ↔ tools : boucle agentique pour explorer les datasets tabulaires.
        - compute_co2      : calcul Python via le service CO₂ (fallback statique si service indispo).
        - reasoner_final   : synthèse finale réutilisant le tableau calculé.
        """
        builder = StateGraph(EcoState)

        builder.add_node("reasoner", self.reasoner)
        builder.add_node("tools", self.mcp.get_tool_nodes())
        builder.add_node("compute_co2", self.compute_co2)
        builder.add_node("reasoner_final", self.reasoner_final)

        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner",
            tools_condition,
            {"tools": "tools", "__end__": "compute_co2"},
        )
        builder.add_edge("tools", "reasoner")
        builder.add_edge("compute_co2", "reasoner_final")
        builder.add_edge("reasoner_final", END)

        return builder

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
        recent_history = self.recent_messages(state["messages"], max_messages=5)
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)

        trip_hints = self._extract_trip_hints(state)
        merged_trip = self._merge_trip_fields(state, trip_hints)

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

            result: Dict[str, Any] = {
                "messages": [response],
                "database_context": database_context,
            }
            for field in ("distance_km", "frequency_days", "mode"):
                value = merged_trip.get(field)
                if value is not None:
                    result[field] = value
            return result

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

    # -----------------------------------------------------------------------
    # 4) Noeud compute_co2
    # -----------------------------------------------------------------------
    async def compute_co2(self, state: EcoState):
        trip_hints = self._extract_trip_hints(state)
        merged_trip = self._merge_trip_fields(state, trip_hints)
        distance = merged_trip.get("distance_km")
        frequency = merged_trip.get("frequency_days")
        current_mode = merged_trip.get("mode")

        payload: Optional[Dict[str, Any]] = None
        if distance is not None and frequency is not None and frequency > 0:
            comparison = await self._compare_modes_via_mcp(distance, frequency, current_mode)
            if comparison:
                service_mode = comparison.get("_service_current_mode", "car_thermal")
                suggestions = self._generate_service_suggestions(comparison, service_mode)
                payload = self._build_service_payload(
                    comparison, distance, frequency, suggestions
                )
            else:
                payload = self._build_co2_payload(distance, frequency, current_mode)
        result: Dict[str, Any] = {"messages": [], "co2_payload": payload}
        for field, value in (
            ("distance_km", distance),
            ("frequency_days", frequency),
            ("mode", current_mode),
        ):
            if value is not None:
                result[field] = value
        return result

    # -----------------------------------------------------------------------
    # 5) Noeud reasoner_final
    # -----------------------------------------------------------------------
    async def reasoner_final(self, state: EcoState):
        if self.model is None:
            raise RuntimeError(
                "EcoAdvisor: model is not initialized. Call async_init() first."
            )

        tpl = self.get_tuned_text("prompts.system") or ""
        database_context = await self._ensure_database_context(state)
        tpl += self._format_context_for_prompt(database_context)

        co2_payload = state.get("co2_payload")
        if co2_payload:
            suggestions_md = "\n".join(f"- {s}" for s in co2_payload["suggestions"])
            tpl += (
                "### Precomputed weekly CO₂ summary\n"
                f"{co2_payload['table_markdown']}\n\n"
                f"**Hypothèses (ne pas modifier)** : {co2_payload['assumptions']}\n"
                f"**Pistes bas carbone suggérées** :\n{suggestions_md}\n"
                "Réutilise ces valeurs exactes dans ta réponse finale.\n\n"
            )
        else:
            tpl += (
                "### compute_co2 status\n"
                "Les champs `distance_km` et `frequency_days` sont manquants. "
                "Demande ces informations à l'utilisateur avant de conclure.\n\n"
            )

        system_text = self.render(tpl)
        recent_history = self.recent_messages(state["messages"], max_messages=8)
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)
        response = await self.model.ainvoke(messages)

        return {
            "messages": [response],
            "database_context": database_context,
        }
