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
from typing import Annotated, Any, Dict, List, TypedDict

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
                "### CO₂ Estimates (simplified factors)\n"
                "When you need to estimate CO₂ emissions, you can use the following factors:\n"
                "- Car (thermal): 0.192 kg CO₂ per km\n"
                "- Public transport (average): 0.01 kg CO₂ per km\n"
                "- Bike / walking: 0 kg CO₂ per km\n"
                "These are simplified emission factors inspired by ADEME data, for demo purposes.\n\n"
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
                "Current date: {today}.\n\n"
            ),
        ),
    ],
    # EcoAdvisor utilise le même MCP server tabulaire que Tessa.
    # Fred rationale:
    # - On ne réinvente pas l'intégration back; on exploite la même passerelle MCP.
    mcp_servers=[
        MCPServerRef(id="mcp-knowledge-flow-mcp-tabular"),
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
