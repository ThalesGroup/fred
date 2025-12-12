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
from typing import Annotated, Any, Dict, List, TypedDict, Union

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
                "- First, **list the available datasets and their schema** using the tools.\n"
                "- Then, select the relevant tables and run queries to inspect nearby bike lanes\n"
                "  and public transport options.\n\n"
                "### TCL Transit Live Tools\n"
                "- Use the dedicated `mcp-tcl-service` whenever you need authoritative stop data.\n"
                "- Available tools:\n"
                "  - `search_tcl_stops` — keyword search with optional city/line filters.\n"
                "  - `find_nearby_tcl_stops` — input lat/lon + radius to list the closest stops (returns precise distances and served lines).\n"
                "  - `list_tcl_lines` and `get_tcl_metadata` — understand which lines are tracked and when the cache last refreshed.\n"
                "- Always surface the `source` and `refreshed_at` fields returned by these tools so the user trusts the provenance (Grand Lyon WFS vs fallback CSV).\n\n"
                "### CO₂ Reference Service\n"
                "- Do NOT rely on hardcoded emission factors. Always call the MCP tools provided by the CO₂ reference service (`mcp-co2-service`).\n"
                "- `list_emission_modes` helps you discover all supported modes and their metadata.\n"
                "- `get_emission_factor` returns a single factor with `source` and `last_update` so you can cite the reference explicitly.\n"
                "- `compare_trip_modes` should be used when you know the distance and frequency: it returns a comparison payload (weekly emissions per mode) ready to transform into a Markdown table.\n"
                "- When the service is unavailable, fall back to the baseline assumptions (car 0.192 kg/km, TCL 0.01 kg/km, bike/walk 0 kg/km) and clearly state that you relied on the backup factors.\n\n"
                "### Workflow\n"
                "1. Clarify the user's context:\n"
                "   - origin and destination (city or district is enough)\n"
                "   - main current mode of transport (car, bike, TCL, etc.)\n"
                "   - approximate one-way distance or time if available\n"
                "   - frequency (e.g., 5 days/week)\n"
                "2. Use tools to **list datasets and their schema**.\n"
                "3. Identify which tables are relevant (e.g., bike_infra_demo for active modes) and when to pivot to the TCL MCP for stops or line metadata.\n"
                "4. Combine SQL-like queries with the TCL tools to:\n"
                "   - find long bike lanes near the origin/destination city\n"
                "   - look up TCL stops/lines around the user request (search or nearby lookup)\n"
                "5. Based on distance and mode, estimate weekly CO₂ emissions using the factors above.\n"
                "6. Compare current mode vs alternatives (TCL, bike, walking if realistic).\n"
                "7. Produce a clear, concise **markdown summary** with:\n"
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
                "- Mets en évidence les données ou ordres de grandeur critiques avec du gras limité (`**CO₂ actuel**`, `**Point critique**`).\n"
                "- Reste concis: phrases courtes, pas de redites inutiles.\n"
                "- Utilise des pastilles couleurs via emoji standards pour qualifier les options: `🟢` (option bas carbone), `🟠` (point de vigilance), `🔴` (action à éviter). Ne dépasse jamais trois pastilles par réponse.\n"
                "- Ajoute au besoin des emojis transport (🚲, 🚗, 🚌, 🚶, etc ...) pour illustrer les options.\n"
                "- Termine les recommandations chiffrées par un tableau Markdown (colonnes `Mode | CO₂ hebdo | Hypothèses`) et ajoute un bloc `Hypothèses` en liste courte.\n"
                "- Fractionne les paragraphes en listes ou phrases courtes pour rester lisible dans l'UI.\n\n"
                "### Rules\n"
                "- ALWAYS base your conclusions on actual tool results when referring to datasets.\n"
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
    def _maybe_parse_json(self, payload: Any) -> Any:
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                return payload
        return payload

    def _format_context_for_prompt(self, database_context: DatabaseContextPayload) -> str:
        """
        Formatte la liste des bases / tables accessibles pour injection dans le prompt.

        Fred rationale:
        - On donne au LLM une vue synthétique des datasets disponibles
          → il n'a pas à "deviner" les noms de tables.
        """
        context_payload = self._maybe_parse_json(database_context)
        normalized_entries: List[Dict[str, Any]] = []

        if isinstance(context_payload, dict):
            normalized_entries = [
                {"database": db_name, "tables": tables}
                for db_name, tables in context_payload.items()
            ]
        elif isinstance(context_payload, list):
            for entry in context_payload:
                parsed_entry = self._maybe_parse_json(entry)
                if isinstance(parsed_entry, dict):
                    if "database" not in parsed_entry and "db_name" in parsed_entry:
                        parsed_entry["database"] = parsed_entry.get("db_name")
                    normalized_entries.append(parsed_entry)
                else:
                    normalized_entries.append(
                        {"database": "unknown_database", "tables": parsed_entry}
                    )
        elif context_payload:
            normalized_entries = [
                {"database": "unknown_database", "tables": context_payload}
            ]

        if not normalized_entries:
            return "No databases or tables currently loaded.\n"

        lines = ["You currently have access to the following structured datasets:\n"]
        for entry in normalized_entries:
            if not isinstance(entry, dict):
                lines.append(f"- {entry}")
                continue
            db = (
                entry.get("database")
                or entry.get("db_name")
                or "unknown_database"
            )
            tables_summary = self._summarize_tables(entry.get("tables"))
            lines.append(f"- Database: `{db}` with tables: {tables_summary}")
        return "\n".join(lines) + "\n\n"

    def _summarize_tables(self, tables: Any) -> str:
        """
        Retourne une représentation courte des tables accessibles dans une base.
        """
        if isinstance(tables, dict):
            summaries = []
            for table_name, columns in tables.items():
                detail = ""
                if isinstance(columns, list):
                    detail = f"{len(columns)} columns"
                summaries.append(
                    f"{table_name}{f' ({detail})' if detail else ''}"
                )
            return "[" + ", ".join(summaries) + "]" if summaries else "[]"

        if isinstance(tables, list):
            display_parts = []
            for table in tables:
                parsed = self._maybe_parse_json(table)
                if isinstance(parsed, dict):
                    table_name = (
                        parsed.get("table_name")
                        or parsed.get("name")
                        or parsed.get("table")
                        or "unknown_table"
                    )
                    row_count = parsed.get("row_count")
                    columns = parsed.get("columns")
                    column_summary = ""
                    if isinstance(columns, list):
                        column_names = [
                            col.get("name", "?")
                            for col in columns[:4]
                            if isinstance(col, dict)
                        ]
                        if column_names:
                            suffix = "…" if len(columns) > len(column_names) else ""
                            column_summary = f"cols: {', '.join(column_names)}{suffix}"
                    details = []
                    if isinstance(row_count, int):
                        details.append(f"{row_count} rows")
                    if column_summary:
                        details.append(column_summary)
                    if details:
                        display_parts.append(
                            f"{table_name} ({'; '.join(details)})"
                        )
                    else:
                        display_parts.append(table_name)
                else:
                    display_parts.append(str(parsed))
            return "[" + "; ".join(display_parts) + "]" if display_parts else "[]"

        if tables in (None, "", []):
            return "[]"
        return str(tables)

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
