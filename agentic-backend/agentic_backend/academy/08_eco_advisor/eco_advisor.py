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
from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union, cast

from fred_core import VectorSearchHit
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_document_library_tags_ids,
    get_rag_knowledge_scope,
    get_search_policy,
    should_skip_rag_search,
)
from agentic_backend.core.chatbot.chat_schema import GeoPart
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

MAX_TOOL_MESSAGE_CHARS = int(os.getenv("ECO_MAX_TOOL_MESSAGE_CHARS", "4000"))
RECENT_MESSAGES_WINDOW = int(os.getenv("ECO_RECENT_MESSAGES", "12"))
MAX_MAP_FEATURES = int(os.getenv("ECO_MAX_MAP_FEATURES", "60"))
MAP_STICKINESS_TURNS = max(0, int(os.getenv("ECO_MAP_STICKINESS_TURNS", "2")))
MAX_DOC_SNIPPETS = max(0, int(os.getenv("ECO_MAX_DOC_SNIPPETS", "4")))
DOC_SNIPPET_CHAR_LIMIT = max(120, int(os.getenv("ECO_DOC_SNIPPET_CHARS", "600")))
DOC_SEARCH_TOP_K = max(MAX_DOC_SNIPPETS, int(os.getenv("ECO_DOC_TOP_K", "6")))
MAP_REQUEST_KEYWORDS = (
    "carte",
    "cartes",
    "cartographie",
    "carto",
    "map",
    "maps",
    "plan",
    "plans",
    "geoloc",
    "géolocalise",
    "geolocalise",
    "geolocate",
    "voir sur une carte",
    "montre la carte",
    "montrez la carte",
    "affiche la carte",
    "afficher la carte",
    "show me the map",
    "show the map",
)

DatabaseContextPayload = Union[List[Dict[str, Any]], Dict[str, Any], str, None]


class DocumentContextPayload(TypedDict, total=False):
    query: str
    hits: List[Dict[str, Any]]
    snippets: List[Dict[str, Any]]


class GeoContext(TypedDict, total=False):
    geo_part: Dict[str, Any]
    remaining_turns: int


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
                "You are **EcoAdvisor**, a concise mobility & CO₂ guide.\n"
                "- Answer in the user's language and rely on the datasets imported via Knowledge Flow.\n"
                "- Tools (choose only what helps the current turn):\n"
                "  * `mcp-knowledge-flow-mcp-tabular` — context + SQL on the CSV datasets (bike infra, ADEME CO₂ factors, TCL stops, travel times).\n"
                "  * `mcp-knowledge-flow-mcp-text` — `search_documents_using_vectorization` to cite PDF excerpts (guides, aides financières, bonnes pratiques).\n"
                "  * `mcp-geo-service` — `geocode_location`, `compute_trip_distance`, `estimate_trip_between_addresses` for addresses and mode comparisons.\n"
                "  * `mcp-tcl-service` — `find_nearby_tcl_stops`, `search_tcl_stops`, `list_tcl_lines` for transit context.\n"
                "  * `mcp-fs` — `read_file` when you must surface a user attachment.\n"
                "- Prefer tool evidence over guesses; cite dataset `source`/`last_update` or PDF title + page.\n"
                "- Only show a map when locations truly matter.\n"
                "- Final answer: ≤4 short sentences; optionally add a Markdown table `Mode | CO₂ hebdo | Hypothèses` plus one real-world equivalence.\n"
                "- If data is missing or a call fails, state the gap and the assumption you used instead of inventing values."
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
    mcp_servers=[
        MCPServerRef(name="mcp-knowledge-flow-mcp-tabular"),
        MCPServerRef(name="mcp-knowledge-flow-mcp-text", optional=True),
        MCPServerRef(name="mcp-fs", optional=True),
        MCPServerRef(name="mcp-geo-service", optional=True),
        MCPServerRef(name="mcp-tcl-service", optional=True),
    ],
)


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
    database_context: DatabaseContextPayload
    document_context: DocumentContextPayload
    geo_context: GeoContext


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
        self._base_model: Optional[BaseChatModel] = None
        self.search_client = VectorSearchClient(agent=self)

    # -----------------------------------------------------------------------
    # Bootstrap: modèle + MCP + graphe
    # -----------------------------------------------------------------------
    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        # Modele "par défaut" de Fred pour le chat (fourni par la factory centrale).
        base_model = get_default_chat_model()
        self._base_model = base_model

        # Démarre la stack MCP tabulaire (client JSON-RPC, discovery des tools, etc.).
        await self.mcp.init()

        # On bind les tools MCP directement au modèle:
        # cela permet au LLM d'appeler des tools "nativement" via l'OpenAI tool-calling.
        self.model = base_model.bind_tools(self.mcp.get_tools())

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

    def _system_prompt(self) -> str:
        """Return the base system prompt (without auto-injected context)."""
        return self.render(self.get_tuned_text("prompts.system") or "")

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
    # Prompt + document context helpers
    # -----------------------------------------------------------------------
    async def _prepare_system_prompt(
        self, state: EcoState, *, map_requested: bool = False
    ) -> tuple[str, DatabaseContextPayload, DocumentContextPayload]:
        """Build the system prompt once (datasets + document snippets)."""

        tpl = self.get_tuned_text("prompts.system") or ""

        database_context = await self._ensure_database_context(state)
        tpl += self._format_context_for_prompt(database_context)

        document_context: DocumentContextPayload = (
            cast(DocumentContextPayload, state.get("document_context"))
            if isinstance(state.get("document_context"), dict)
            else {}
        )

        runtime_context = self.get_runtime_context()
        rag_scope = get_rag_knowledge_scope(runtime_context)
        should_lookup_docs = (
            MAX_DOC_SNIPPETS > 0 and not should_skip_rag_search(runtime_context)
        )
        if should_lookup_docs:
            doc_block, document_context = await self._ensure_document_context(
                state, document_context
            )
        else:
            doc_block = ""
            # Purge any cached snippets so we don't cite PDFs while in general-only mode.
            if document_context:
                document_context = cast(DocumentContextPayload, {})
                state["document_context"] = document_context

        if doc_block:
            tpl += f"\n\n{doc_block}"

        if rag_scope == "general_only":
            tpl += (
                "\n\nUser selected *General knowledge* mode: do not rely on the local CSV/PDF "
                "datasets nor call their MCP tools unless absolutely required to clarify the request. "
                "Answer from broad knowledge and be transparent when data points would need local imports."
            )
        elif rag_scope == "corpus_only":
            tpl += (
                "\n\nUser selected *Local data* mode: ground every recommendation in the tabular datasets "
                "or PDF snippets provided via the MCP tools. If a fact is missing from those resources, "
                "say so explicitly instead of inventing an answer. Do not rely on external or general knowledge. "
                "Only use facts coming from the MCP tool outputs, database context, or the PDF snippets above."
            )

        if map_requested:
            geo_ctx = cast(Optional[GeoContext], state.get("geo_context"))
            has_cached_geo = bool(
                isinstance(geo_ctx, dict) and isinstance(geo_ctx.get("geo_part"), dict)
            )
            instruction_lines = [
                "The latest user turn explicitly asked to see a map.",
                "Reuse the cached GeoPart if it exists, otherwise call the geo MCP tools to build one.",
            ]
            if not has_cached_geo:
                instruction_lines.append(
                    "There is no cached map yet, so plan on invoking the geo MCP."
                )
            tpl += "\n\n" + " ".join(instruction_lines)

        return self.render(tpl), database_context, document_context

    def _general_only_system_prompt(self) -> str:
        tpl = self.get_tuned_text("prompts.system") or ""
        tpl += (
            "\n\nGeneral knowledge mode is active: ignore the local CSV/PDF datasets and MCP tools. "
            "Answer using broad mobility and sustainability expertise, and state when precise local numbers "
            "would require re-enabling the data sources."
        )
        return self.render(tpl)

    async def _answer_general_only(self, state: EcoState) -> Dict[str, Any]:
        model = self._base_model or self.model
        if model is None:
            raise RuntimeError("EcoAdvisor: model is not initialized. Call async_init() first.")

        system_text = self._general_only_system_prompt()
        history = self.recent_messages(
            state.get("messages") or [], max_messages=max(RECENT_MESSAGES_WINDOW, 1)
        )
        messages = self.with_system(system_text, history)
        messages = self.with_chat_context_text(messages)
        messages = self._compact_messages_for_llm(messages)
        response = await model.ainvoke(messages)
        return {
            "messages": [response],
            "database_context": [],
            "document_context": {},
            "geo_context": state.get("geo_context"),
        }

    async def _answer_corpus_only(self, state: EcoState) -> Dict[str, Any]:
        model = self._base_model or self.model
        if model is None:
            raise RuntimeError("EcoAdvisor: model is not initialized. Call async_init() first.")

        runtime_context = self.get_runtime_context()
        question = self._extract_latest_user_question(state.get("messages") or []) or ""
        doc_tag_ids = get_document_library_tags_ids(runtime_context)
        search_policy = get_search_policy(runtime_context)
        top_k = max(1, self.get_tuned_int("rag.top_k", default=10, min_value=1))

        hits = self.search_client.search(
            question=question,
            top_k=top_k,
            document_library_tags_ids=doc_tag_ids,
            search_policy=search_policy,
        )
        if not hits:
            warn = (
                "No relevant documents were found for this question. "
                "You must not use general knowledge. Explain that you cannot answer without evidence from the corpus "
                "and invite the user to refine the question or provide documents."
            )
            return {
                "messages": [AIMessage(content=warn)],
                "database_context": [],
                "document_context": {},
                "geo_context": state.get("geo_context"),
            }

        hits = sort_hits(hits)
        ensure_ranks(hits)

        sources_block = format_sources_for_prompt(
            hits[:MAX_DOC_SNIPPETS], snippet_chars=DOC_SNIPPET_CHAR_LIMIT
        )
        document_context: DocumentContextPayload = {
            "query": question,
            "hits": [h.model_dump() for h in hits],
            "snippets": [h.model_dump() for h in hits[:MAX_DOC_SNIPPETS]],
        }
        state["document_context"] = document_context

        sys_msg = SystemMessage(content=self._system_prompt())
        history_max = self.get_tuned_int("rag.history_max_messages", default=6, min_value=0)
        history = self.get_recent_history(
            state["messages"],
            max_messages=history_max,
            include_system=False,
            include_tool=False,
            drop_last=True,
        )
        guardrails = (
            "\n\nIMPORTANT: Answer strictly using the provided documents. "
            "If they are insufficient, state that you cannot answer without evidence from the corpus. "
            "Do not rely on your general knowledge."
        )
        template = self.get_tuned_text("prompts.with_sources") or "Question:\n{question}\n\nDocuments:\n{sources}"
        rendered = self.render(template, question=question, sources=sources_block)
        human_msg = HumanMessage(content=rendered + guardrails)

        messages = [sys_msg, *history, human_msg]
        messages = self.with_chat_context_text(messages)
        messages = self._compact_messages_for_llm(messages)
        answer = await model.ainvoke(messages)
        attach_sources_to_llm_response(answer, hits[:MAX_DOC_SNIPPETS])
        return {
            "messages": [answer],
            "database_context": [],
            "document_context": document_context,
            "geo_context": state.get("geo_context"),
        }

    async def _ensure_document_context(
        self, state: EcoState, payload: DocumentContextPayload
    ) -> tuple[str, DocumentContextPayload]:
        """
        Cache document hits keyed by the latest user question to avoid re-searching
        when the user follows up.
        """
        question = self._extract_latest_user_question(state.get("messages") or [])
        if not question:
            return "", payload

        cached_query = payload.get("query")
        hits = payload.get("hits") or []
        if cached_query != question or not hits:
            hits = await self._search_pdf_resources(question)
            payload = cast(
                DocumentContextPayload,
                {"query": question, "hits": hits, "snippets": hits[:MAX_DOC_SNIPPETS]},
            )
        else:
            payload["snippets"] = payload.get("snippets") or hits[:MAX_DOC_SNIPPETS]

        state["document_context"] = payload
        block = self._format_document_snippets(payload.get("snippets"))
        return block, payload

    async def _search_pdf_resources(self, question: str) -> List[Dict[str, Any]]:
        if not question:
            return []

        # Respect the UI toggle: skip document retrieval when the user selected
        # the "General knowledge" scope.
        if should_skip_rag_search(self.get_runtime_context()):
            logger.debug("EcoAdvisor: skipping PDF search because general-only mode is active.")
            return []

        tools = self.mcp.get_tools()
        tool = next(
            (t for t in tools if t.name == "search_documents_using_vectorization"),
            None,
        )
        if not tool:
            logger.info(
                "EcoAdvisor: MCP tool 'search_documents_using_vectorization' unavailable."
            )
            return []

        payload: Dict[str, Any] = {
            "question": question,
            "top_k": DOC_SEARCH_TOP_K,
        }
        tags = get_document_library_tags_ids(self.get_runtime_context())
        if tags:
            payload["document_library_tags_ids"] = tags
        search_policy = get_search_policy(self.get_runtime_context())
        if search_policy:
            payload["search_policy"] = search_policy

        try:
            raw_hits = await tool.ainvoke(payload)
        except Exception as exc:
            logger.warning("EcoAdvisor: vector search failed: %s", exc)
            return []

        return self._normalize_document_hits(raw_hits)

    def _normalize_document_hits(self, raw_hits: Any) -> List[Dict[str, Any]]:
        if isinstance(raw_hits, str):
            try:
                raw_hits = json.loads(raw_hits)
            except Exception:
                logger.debug("EcoAdvisor: could not parse document hits JSON.")
                return []

        if isinstance(raw_hits, VectorSearchHit):
            return [raw_hits.model_dump()]

        if not isinstance(raw_hits, list):
            return []

        hits: List[Dict[str, Any]] = []
        for entry in raw_hits[:DOC_SEARCH_TOP_K]:
            if isinstance(entry, VectorSearchHit):
                hits.append(entry.model_dump())
            elif isinstance(entry, dict):
                hits.append(entry)
            else:
                logger.debug(
                    "EcoAdvisor: ignoring document hit of unsupported type %s",
                    type(entry).__name__,
                )
        return hits

    def _format_document_snippets(
        self, hits: Optional[List[Dict[str, Any]]]
    ) -> str:
        if not hits:
            return ""

        lines = [
            "Relevant PDF excerpts from Knowledge Flow (cite title + page when you use them):"
        ]
        for idx, hit in enumerate(hits, start=1):
            if not isinstance(hit, dict):
                continue
            title = (
                hit.get("title")
                or hit.get("file_name")
                or hit.get("uid")
                or "Document"
            )
            page = hit.get("page")
            tags = hit.get("tag_names") or []
            tags_text = (
                ", ".join(t for t in tags if isinstance(t, str) and t.strip())
                if isinstance(tags, list)
                else ""
            )
            meta_parts = []
            if page not in (None, ""):
                meta_parts.append(f"p.{page}")
            if tags_text:
                meta_parts.append(tags_text)
            meta_suffix = f" ({'; '.join(meta_parts)})" if meta_parts else ""

            snippet_text = self._clean_snippet(hit.get("content"))
            if not snippet_text:
                snippet_text = "(no excerpt available)"
            lines.append(f"{idx}. {title}{meta_suffix}: {snippet_text}")
        return "\n".join(lines)

    @staticmethod
    def _clean_snippet(raw: Any) -> str:
        if not raw:
            return ""
        snippet = str(raw)
        snippet = " ".join(snippet.split())
        if DOC_SNIPPET_CHAR_LIMIT > 0 and len(snippet) > DOC_SNIPPET_CHAR_LIMIT:
            return snippet[:DOC_SNIPPET_CHAR_LIMIT].rstrip() + "…"
        return snippet

    def _extract_latest_user_question(
        self, messages: List[AnyMessage]
    ) -> Optional[str]:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                text = self._message_to_text(msg)
                if text:
                    return text
        return None

    def _user_requests_map(self, state: EcoState) -> bool:
        question = self._extract_latest_user_question(state.get("messages") or [])
        if not question:
            return False
        normalized = question.casefold()
        return any(keyword in normalized for keyword in MAP_REQUEST_KEYWORDS)

    @staticmethod
    def _message_to_text(message: HumanMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(p.strip() for p in parts if p.strip())
        return ""

    def _coerce_vector_hits(
        self, hits: Optional[List[Any]]
    ) -> List[VectorSearchHit]:
        if not hits:
            return []

        parsed: List[VectorSearchHit] = []
        for entry in hits:
            if isinstance(entry, VectorSearchHit):
                parsed.append(entry)
                continue
            if isinstance(entry, dict):
                try:
                    parsed.append(VectorSearchHit.model_validate(entry))
                except Exception as exc:
                    logger.debug(
                        "EcoAdvisor: failed to coerce document hit: %s",
                        exc,
                    )
        return parsed

    def _collect_tool_payloads(
        self, messages: List[AnyMessage]
    ) -> Dict[str, Any]:
        payloads: Dict[str, Any] = {}
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", ""):
                raw = msg.content
                try:
                    normalized = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    normalized = raw
                tool_name = msg.name or "tool"
                if tool_name not in payloads:
                    payloads[tool_name] = normalized
            elif isinstance(msg, AIMessage):
                break
        return payloads

    def _enrich_response_metadata(
        self,
        response: AnyMessage,
        *,
        tool_payloads: Dict[str, Any],
        document_context: DocumentContextPayload,
    ) -> None:
        metadata = getattr(response, "response_metadata", {}) or {}
        tools_md = metadata.get("tools", {}) or {}
        tools_md.update(tool_payloads)
        metadata["tools"] = tools_md
        response.response_metadata = metadata

        snippet_hits = self._coerce_vector_hits(document_context.get("snippets"))
        if snippet_hits:
            attach_sources_to_llm_response(response, snippet_hits)

    def _attach_geo_part(self, response: AnyMessage, geo_part: GeoPart) -> None:
        add_kwargs = getattr(response, "additional_kwargs", None)
        if add_kwargs is None or not isinstance(add_kwargs, dict):
            add_kwargs = {}
            response.additional_kwargs = add_kwargs
        fred_parts = add_kwargs.get("fred_parts")
        if not isinstance(fred_parts, list):
            fred_parts = []
        fred_parts.append(geo_part.model_dump())
        add_kwargs["fred_parts"] = fred_parts

    def _remember_geo_part(self, state: EcoState, geo_part: GeoPart) -> None:
        state["geo_context"] = {
            "geo_part": geo_part.model_dump(),
            "remaining_turns": MAP_STICKINESS_TURNS,
        }

    def _consume_cached_geo_part(
        self, state: EcoState, *, force: bool = False
    ) -> Optional[GeoPart]:
        geo_ctx = cast(Optional[GeoContext], state.get("geo_context"))
        if not geo_ctx:
            return None
        geo_dict = geo_ctx.get("geo_part")
        if not isinstance(geo_dict, dict):
            state.pop("geo_context", None)
            return None
        remaining = int(geo_ctx.get("remaining_turns", 0) or 0)
        if force:
            refresh = max(MAP_STICKINESS_TURNS, 1)
            if remaining < refresh:
                remaining = refresh
        elif remaining <= 0:
            return None
        if remaining <= 0:
            return None
        geo_ctx["remaining_turns"] = max(remaining - 1, 0)
        try:
            return GeoPart.model_validate(geo_dict)
        except Exception:
            state.pop("geo_context", None)
            return None

    async def _handle_reasoner_failure(
        self, state: EcoState, document_context: DocumentContextPayload
    ) -> Dict[str, Any]:
        user_text = self._extract_latest_user_question(state.get("messages") or [])
        prompt_lines = [
            "You are EcoAdvisor. A technical error happened while analyzing mobility data.",
            "Write a brief apology that asks the user to retry or simplify their question.",
            "Respond in the same language as this text (default to English if empty):",
            user_text or "English",
        ]
        fallback = await self.model.ainvoke([HumanMessage(content="\n".join(prompt_lines))])
        return {
            "messages": [fallback],
            "database_context": [],
            "document_context": document_context,
            "geo_context": state.get("geo_context"),
        }

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
                            if len(features) >= MAX_MAP_FEATURES:
                                return
                    elif isinstance(nested, dict):
                        _collect(nested, source)
                        if len(features) >= MAX_MAP_FEATURES:
                            return
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
                        if len(features) >= MAX_MAP_FEATURES:
                            return
                # Fallback: traverse any other nested dict/list values to discover coordinates.
                for nested_value in payload.values():
                    if len(features) >= MAX_MAP_FEATURES:
                        return
                    if isinstance(nested_value, dict):
                        _collect(nested_value, source)
                    elif isinstance(nested_value, (list, tuple)):
                        for item in nested_value:
                            _collect(item, source)
                            if len(features) >= MAX_MAP_FEATURES:
                                return
            elif isinstance(payload, (list, tuple)):
                for item in payload:
                    _collect(item, source)
                    if len(features) >= MAX_MAP_FEATURES:
                        return

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

        runtime_context = self.get_runtime_context()
        rag_scope = get_rag_knowledge_scope(runtime_context)
        if rag_scope == "general_only":
            state["document_context"] = {}
            return await self._answer_general_only(state)

        wants_map = self._user_requests_map(state)
        (
            system_text,
            database_context,
            document_context,
        ) = await self._prepare_system_prompt(state, map_requested=wants_map)

        # 3) Construire l'historique de conversation minimal
        recent_history = self.recent_messages(
            state["messages"], max_messages=max(RECENT_MESSAGES_WINDOW, 1)
        )
        messages = self.with_system(system_text, recent_history)
        messages = self.with_chat_context_text(messages)
        messages = self._compact_messages_for_llm(messages)
        if rag_scope == "corpus_only":
            guardrail_msg = SystemMessage(
                content=(
                    "CORPUS-ONLY GUARDRAIL: Use only facts returned by the MCP tools or the PDF snippets/context provided. "
                    "If the data is missing or incomplete, state that you cannot answer without corpus evidence. "
                    "Do not use general knowledge."
                )
            )
            messages = [guardrail_msg, *messages]

        try:
            # 4) LLM + tool-calling: le modèle peut décider d'appeler MCP ou non
            response = await self.model.ainvoke(messages)

            tool_payloads = self._collect_tool_payloads(state["messages"])
            self._enrich_response_metadata(
                response,
                tool_payloads=tool_payloads,
                document_context=document_context,
            )
            geo_part = self._maybe_build_geo_part_from_tools(tool_payloads)
            if geo_part:
                self._attach_geo_part(response, geo_part)
                self._remember_geo_part(state, geo_part)
            else:
                cached_geo_part = self._consume_cached_geo_part(
                    state, force=wants_map
                )
                if cached_geo_part:
                    self._attach_geo_part(response, cached_geo_part)

            return {
                "messages": [response],
                "database_context": database_context,
                "document_context": document_context,
                "geo_context": state.get("geo_context"),
            }

        except Exception:
            logger.exception("EcoAdvisor failed during reasoning.")
            return await self._handle_reasoner_failure(state, document_context)
