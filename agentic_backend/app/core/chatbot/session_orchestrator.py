# chat/session_orchestrator.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import asyncio
import logging
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile
# (Optionnel) trace léger si tu veux l'utiliser plus tard
# from app.core.chatbot.orchestration_trace import OrchestrationTrace

from fred_core import Action, KeycloakUser, KPIActor, KPIWriter, Resource, authorize
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.application_context import (
    get_configuration,
    get_default_model,
    get_history_store,
    get_kpi_writer,
)
from app.core.agents.agent_manager import AgentManager
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import RuntimeContext
from app.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    Role,
    SessionSchema,
    SessionWithFiles,
    TextPart,
)
from app.core.chatbot.metric_structures import MetricsResponse
from app.core.chatbot.stream_transcoder import StreamTranscoder
from app.core.session.attachement_processing import AttachementProcessing
from app.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)

# Callback type used by WS controller to push events to clients
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt() -> datetime:
    """UTC timestamp (seconds resolution) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


class SessionOrchestrator:
    """
    Keep the controller thin. This orchestrator is the ONLY entry point used by
    the WebSocket/API layer to run a chat exchange. It owns:
      - session lifecycle
      - emitting the user message
      - KPI timing and counters
      - persistence of session + history
    It delegates ALL streaming/transcoding of LangGraph events to StreamTranscoder.
    """

    def __init__(self, session_store: BaseSessionStore, agent_manager: AgentManager):
        self.session_store = session_store
        self.agent_manager = agent_manager

        # Side services
        self.history_store = get_history_store()
        self.kpi: KPIWriter = get_kpi_writer()
        self.attachement_processing = AttachementProcessing()

        # Stateless worker that knows how to turn LangGraph events into ChatMessage[]
        self.transcoder = StreamTranscoder()

        # Cached config
        self.recursion_limit = get_configuration().ai.recursion.recursion_limit

    # ---------------- Public API (used by WS layer) ----------------

    @authorize(action=Action.CREATE, resource=Resource.SESSIONS)
    @authorize(action=Action.UPDATE, resource=Resource.SESSIONS)
    async def chat_ask_websocket(
        self,
        *,
        user: KeycloakUser,
        callback: CallbackType,
        session_id: str,
        message: str,
        agent_name: str,
        runtime_context: Optional[RuntimeContext] = None,
        client_exchange_id: Optional[str] = None,
    ) -> Tuple[SessionSchema, List[ChatMessage]]:
        """
        Entry point called by the WebSocket controller for a user question.
        """
        logger.info(
            "chat_ask_websocket user_id=%s session_id=%s agent=%s",
            user.uid,
            session_id,
            agent_name,
        )

        # KPI: count incoming question early (before any work)
        actor = KPIActor(type="human", user_id=user.uid)
        exchange_id = client_exchange_id or str(uuid4())
        self.kpi.count(
            "chat.user_message_total",
            1,
            dims={
                "agent_id": agent_name,
                "scope_type": "session",
                "scope_id": session_id,
                "exchange_id": exchange_id,
            },
            actor=actor,
        )

        # 1) Ensure session + rebuild minimal LC history
        session, lc_history, agent, _is_new_session = self._prepare_session_and_history(
            user=user,
            session_id=session_id,
            message=message,
            agent_name=agent_name,
            runtime_context=runtime_context,
        )

        # Rank base = current stored history length
        prior: List[ChatMessage] = self.history_store.get(session.id) or []
        base_rank = len(prior)

        # 2) Emit the user message immediately
        user_msg = ChatMessage(
            session_id=session.id,
            exchange_id=exchange_id,
            rank=base_rank,
            timestamp=_utcnow_dt(),
            role=Role.user,
            channel=Channel.final,
            parts=[TextPart(text=message)],
            metadata=ChatMetadata(),
        )
        all_msgs: List[ChatMessage] = [user_msg]
        await self._emit(callback, user_msg)

        # 3) Stream agent responses via the transcoder
        saw_final_assistant = False

        # --- NEW: compose a callback that enriches assistant messages with used-only plugins
        enriched_callback = self._wrap_with_plugins_used(callback, runtime_context)

        try:
            with self.kpi.timer(
                "chat.exchange_latency_ms",
                dims={
                    "agent_id": agent_name,
                    "user_id": user.uid,
                    "session_id": session.id,
                    "exchange_id": exchange_id,
                },
                actor=actor,
            ):
                agent_msgs = await self.transcoder.stream_agent_response(
                    compiled_graph=agent.get_compiled_graph(),
                    input_messages=lc_history + [HumanMessage(message)],
                    session_id=session.id,
                    exchange_id=exchange_id,
                    agent_name=agent_name,
                    base_rank=base_rank,
                    start_seq=1,  # user message already consumed rank=base_rank
                    callback=enriched_callback,  # <- inject enrichment centrally
                )
                all_msgs.extend(agent_msgs)
                saw_final_assistant = any(
                    (m.role == Role.assistant and m.channel == Channel.final)
                    for m in agent_msgs
                )
        except Exception:
            logger.exception("Agent execution failed")
        finally:
            self.kpi.count(
                "chat.exchange_total",
                1,
                dims={
                    "agent_id": agent_name,
                    "user_id": user.uid,
                    "session_id": session.id,
                    "exchange_id": exchange_id,
                    "status": "ok" if saw_final_assistant else "error",
                },
                actor=actor,
            )

        # 4) Persist session + history
        session.updated_at = _utcnow_dt()
        self.session_store.save(session)
        assert session.user_id == user.uid, "Session/user mismatch"
        self.history_store.save(session.id, prior + all_msgs, user.uid)

        return session, all_msgs

    # ---------------- Session/History helpers ----------------

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_sessions(self, user: KeycloakUser) -> List[SessionWithFiles]:
        sessions = self.session_store.get_for_user(user.uid)
        enriched: List[SessionWithFiles] = []
        for session in sessions:
            session_folder = self._get_session_temp_folder(session.id)
            file_names = (
                [f.name for f in session_folder.iterdir() if f.is_file()]
                if session_folder.exists()
                else []
            )
            enriched.append(
                SessionWithFiles(**session.model_dump(), file_names=file_names)
            )
        return enriched

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_session_history(self, session_id: str, user: KeycloakUser) -> List[ChatMessage]:
        # TODO: check session belongs to user
        return self.history_store.get(session_id) or []

    @authorize(action=Action.DELETE, resource=Resource.SESSIONS)
    def delete_session(self, session_id: str, user: KeycloakUser) -> None:
        # TODO: check session belongs to user
        self.session_store.delete(session_id)

    # ---------------- File uploads ----------------

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    async def upload_file(
        self, user: KeycloakUser, session_id: str, agent_name: str, file: UploadFile
    ) -> dict:
        """
        Simple temp storage for uploaded files tied to a session.
        """
        try:
            session_folder = self._get_session_temp_folder(session_id)
            if file.filename is None:
                raise ValueError("Uploaded file must have a filename.")
            file_path = session_folder / file.filename
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            # Keep existing attachment pipeline
            self.attachement_processing.process_attachment(file_path)

            logger.info(
                "[📁 Upload] File '%s' saved to %s for session '%s'",
                file.filename,
                file_path,
                session_id,
            )
            return {
                "filename": file.filename,
                "saved_path": str(file_path),
                "message": "File uploaded successfully",
            }
        except Exception:
            logger.exception("Failed to store uploaded file.")
            raise RuntimeError("Failed to store uploaded file.")

    # ---------------- Metrics passthrough ----------------

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: dict[str, List[str]],
    ) -> MetricsResponse:
        return self.history_store.get_chatbot_metrics(
            start=start,
            end=end,
            precision=precision,
            groupby=groupby,
            agg_mapping=agg_mapping,
            user_id=user_id,
        )

    # ---------------- internals ----------------

    def _get_session_temp_folder(self, session_id: str) -> Path:
        base_temp_dir = Path(tempfile.gettempdir()) / "chatbot_uploads"
        session_folder = base_temp_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        return session_folder

    async def _emit(self, callback: CallbackType, message: ChatMessage) -> None:
        """
        Supports sync OR async callbacks uniformly.
        """
        result = callback(message.model_dump())
        if asyncio.iscoroutine(result):
            await result

    def _prepare_session_and_history(
        self,
        *,
        user: KeycloakUser,
        session_id: str | None,
        message: str,
        agent_name: str,
        runtime_context: RuntimeContext | None = None,
    ) -> tuple[SessionSchema, list[BaseMessage], AgentFlow, bool]:
        session, is_new_session = self._get_or_create_session(
            user_id=user.uid, query=message, session_id=session_id
        )

        # Minimal LC history (user/assistant/system only)
        lc_history: list[BaseMessage] = []
        for m in self.get_session_history(session.id, user):
            if m.role == Role.user:
                lc_history.append(HumanMessage(_concat_text_parts(m.parts or [])))
            elif m.role == Role.assistant:
                md = m.metadata.model_dump() if m.metadata else {}
                lc_history.append(
                    AIMessage(
                        content=_concat_text_parts(m.parts or []),
                        response_metadata=md,
                    )
                )
            elif m.role == Role.system:
                lc_history.append(SystemMessage(_concat_text_parts(m.parts or [])))
            # Role.tool is ignored for prompt cleanliness.

        agent: AgentFlow = self.agent_manager.get_agent_instance(
            name=agent_name, runtime_context=runtime_context
        )
        return session, lc_history, agent, is_new_session

    def _get_or_create_session(
        self, *, user_id: str, query: str, session_id: Optional[str]
    ) -> Tuple[SessionSchema, bool]:
        if session_id:
            existing = self.session_store.get(session_id)
            if existing:
                logger.info("Resumed session %s for user %s", session_id, user_id)
                return existing, False

        new_session_id = secrets.token_urlsafe(8)
        title: str = (
            get_default_model()
            .invoke(
                "Give a short, clear title for this conversation based on the user's question. "
                "Return a few keywords only. Question: " + query
            )
            .content
        )
        session = SessionSchema(
            id=new_session_id, user_id=user_id, title=title, updated_at=_utcnow_dt()
        )
        self.session_store.save(session)
        logger.info("Created new session %s for user %s", new_session_id, user_id)
        return session, True

    # ---------- enrichment helpers (used-only plugins) ----------

    def _wrap_with_plugins_used(
        self,
        inner_cb: CallbackType,
        runtime_context: Optional[RuntimeContext],
    ) -> CallbackType:
        """
        Agrège l'usage 'used-only' sur l'ENTIER flux puis l'injecte dans metadata.extras.plugins.
        - Ne jette jamais d'exception.
        - N'écrase pas extras.plugins existant : on merge.
        - Déduit tools depuis les tool_calls de TOUT message streamé.
        - Déduit libraries depuis metadata.sources (tous messages), avec fallback RC si sources>0.
        - Compte docs_used cumulés.
        - Remonte search_policy depuis runtime_context si connue.
        """

        # --- état d'agrégation pour CETTE requête
        seen_tools: set[str] = set()
        seen_libs: set[str] = set()
        docs_used_total: int = 0
        search_policy_val: Optional[str] = self._extract_search_policy(runtime_context)

        async def _cb(msg_dict: Dict[str, Any]) -> None:
            nonlocal docs_used_total

            try:
                role = msg_dict.get("role")

                # 1) agrégation globale depuis CHAQUE message du stream
                # tools via parts[].type == "tool_call"
                for p in (msg_dict.get("parts") or []):
                    if isinstance(p, dict) and p.get("type") == "tool_call":
                        name = p.get("name")
                        if name:
                            seen_tools.add(str(name))

                # sources (pour libs + docs_used)
                md = msg_dict.get("metadata") or {}
                sources = md.get("sources")
                if isinstance(sources, list) and sources:
                    docs_used_total += len(sources)
                    # extraire les ids de biblio depuis chaque hit
                    for s in sources:
                        lib = self._extract_library_from_source(s)
                        if lib:
                            seen_libs.add(lib)

                # 2) au moment d'un message assistant, on publie l'état agrégé
                if role == "assistant":
                    md = msg_dict.setdefault("metadata", {})
                    extras = md.setdefault("extras", {})
                    existing = extras.get("plugins") if isinstance(extras.get("plugins"), dict) else {}

                    # si on a des sources mais aucune lib détectée, fallback RC
                    if docs_used_total > 0 and not seen_libs and runtime_context is not None:
                        selected = (
                            getattr(runtime_context, "selected_document_libraries_ids", None)
                            if not isinstance(runtime_context, dict)
                            else runtime_context.get("selected_document_libraries_ids")
                        )
                        if selected:
                            for lib in selected:
                                if lib:
                                    seen_libs.add(str(lib))

                    # construire le bloc 'used-only'
                    used_plugins: Dict[str, Any] = {}
                    if seen_tools:
                        used_plugins["tools"] = sorted(seen_tools)
                    if seen_libs:
                        used_plugins["libraries"] = sorted(seen_libs)
                    if docs_used_total:
                        used_plugins["docs_used"] = docs_used_total
                    if search_policy_val:
                        used_plugins["search_policy"] = search_policy_val

                    # merge non destructif avec ce qui existe déjà
                    if existing:
                        merged = {**used_plugins, **existing}  # existing prioritaire si conflit
                        extras["plugins"] = merged
                    elif used_plugins:
                        extras["plugins"] = used_plugins

                    md["extras"] = extras
                    msg_dict["metadata"] = md

            except Exception:
                # ne jamais bloquer le stream
                pass

            res = inner_cb(msg_dict)
            if asyncio.iscoroutine(res):
                await res

        return _cb  # type: ignore

    # -------- helpers extraction tolérants --------

    def _extract_library_from_source(self, src: Any) -> Optional[str]:
        """
        Tente de récupérer un identifiant de 'bibliothèque' depuis un VectorSearchHit
        ou un dict approchant. On essaie plusieurs clés courantes.
        """
        if src is None:
            return None

        # dict
        if isinstance(src, dict):
            for key in (
                "library_id",
                "document_library_id",
                "collection",
                "index",
                "index_name",
                "source_library",
                "corpus",
                "dataset",
            ):
                val = src.get(key)
                if val:
                    return str(val)
            return None

        # pydantic / objet
        for key in (
            "library_id",
            "document_library_id",
            "collection",
            "index",
            "index_name",
            "source_library",
            "corpus",
            "dataset",
        ):
            val = getattr(src, key, None)
            if val:
                return str(val)
        return None

    def _extract_search_policy(self, rc: Optional[RuntimeContext]) -> Optional[str]:
        if not rc:
            return None
        if isinstance(rc, dict):
            policy = rc.get("search_policy")
            return str(policy) if isinstance(policy, str) and policy else None
        policy = getattr(rc, "search_policy", None)
        return str(policy) if isinstance(policy, str) and policy else None


# ---------- pure helpers (kept local for discoverability) ----------

def _concat_text_parts(parts) -> str:
    texts: list[str] = []
    for p in parts or []:
        if getattr(p, "type", None) == "text":
            txt = getattr(p, "text", None)
            if txt:
                texts.append(str(txt))
    return "\n".join(texts).strip()
