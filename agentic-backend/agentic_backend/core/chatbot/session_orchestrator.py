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

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, UploadFile, WebSocketDisconnect
from fred_core import (
    Action,
    AuthorizationError,
    KeycloakUser,
    Resource,
    authorize,
)
from fred_core.kpi import BaseKPIWriter, KPIActor
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from requests import HTTPError

from agentic_backend.application_context import (
    get_default_model,
)
from agentic_backend.common.kf_fast_text_client import KfFastTextClient
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import BaseAgentFactory
from agentic_backend.core.agents.agent_utils import log_agent_message_summary
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import (
    AttachmentRef,
    Channel,
    ChatbotRuntimeSummary,
    ChatMessage,
    ChatMetadata,
    Role,
    SessionSchema,
    SessionWithFiles,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from agentic_backend.core.chatbot.metric_structures import MetricsResponse
from agentic_backend.core.chatbot.stream_transcoder import StreamTranscoder
from agentic_backend.core.monitoring.base_history_store import BaseHistoryStore
from agentic_backend.core.session.attachement_processing import AttachementProcessing
from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)

# Callback type used by WS controller to push events to clients
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt() -> datetime:
    """UTC timestamp (seconds resolution) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _log_bench_phase(
    *,
    phase: str,
    start_ts: float,
    session_id: str,
    exchange_id: str,
    agent_name: str,
    **extras: Any,
) -> None:
    ms = int((time.monotonic() - start_ts) * 1000)
    extra = " ".join(f"{k}={v}" for k, v in extras.items())
    if extra:
        extra = " " + extra
    logger.info(
        "[BENCH] phase=%s ms=%d session=%s exchange=%s agent=%s%s",
        phase,
        ms,
        session_id,
        exchange_id,
        agent_name,
        extra,
    )


class SessionOrchestrator:
    """
    Why this class exists (architecture note):
      Keep the controller thin. This orchestrator is the ONLY entry point used by
      the WebSocket/API layer to run a chat exchange. It owns:
        - session lifecycle (get/create, title)
        - emitting the user message
        - KPI timing and counters
        - persistence of session + history
      It delegates ALL streaming/transcoding of LangGraph events to StreamTranscoder.
      Result: Single Responsibility, easy to unit test, and the WS layer remains simple.
    """

    def __init__(
        self,
        configuration: Configuration,
        session_store: BaseSessionStore,
        attachments_store: Optional[BaseSessionAttachmentStore],
        agent_factory: BaseAgentFactory,
        history_store: BaseHistoryStore,
        kpi: BaseKPIWriter,
    ):
        self.session_store = session_store
        self.attachments_store = attachments_store
        self.agent_factory = agent_factory
        if self.attachments_store:
            logger.info(
                "[SESSIONS] Attachment persistence enabled via %s",
                type(self.attachments_store).__name__,
            )
        # Side services
        self.history_store = history_store
        self.kpi: BaseKPIWriter = kpi
        self.attachement_processing = AttachementProcessing()
        self.restore_max_exchanges = configuration.ai.restore_max_exchanges
        self._rank_locks: Dict[str, asyncio.Lock] = {}
        # Stateless worker that knows how to turn LangGraph events into ChatMessage[]
        self.transcoder = StreamTranscoder()
        cfg_max_files = configuration.ai.max_attached_files_per_user
        self.max_attached_files_per_user = (
            20 if cfg_max_files is None else cfg_max_files
        )
        cfg_max_size_mb = configuration.ai.max_attached_file_size_mb
        self.max_attached_file_size_mb = (
            10 if cfg_max_size_mb is None else cfg_max_size_mb
        )
        self.max_attached_file_size_bytes = (
            None
            if self.max_attached_file_size_mb is None
            else self.max_attached_file_size_mb * 1024 * 1024
        )

    # ---------------- Public API (used by WS layer) ----------------

    def get_rank_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._rank_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._rank_locks[session_id] = lock
        return lock

    async def _ensure_next_rank(self, session: SessionSchema) -> int:
        if session.next_rank is None:
            prior_msgs = await asyncio.to_thread(self.history_store.get, session.id)
            prior: List[ChatMessage] = prior_msgs or []
            session.next_rank = len(prior)
            await asyncio.to_thread(self.session_store.save, session)
        return session.next_rank

    @authorize(action=Action.CREATE, resource=Resource.SESSIONS)
    @authorize(action=Action.UPDATE, resource=Resource.SESSIONS)
    async def chat_ask_websocket(
        self,
        *,
        user: KeycloakUser,
        callback: CallbackType,
        session_id: str | None,
        message: str,
        agent_name: str,
        runtime_context: RuntimeContext,
        client_exchange_id: Optional[str] = None,
    ) -> Tuple[SessionSchema, List[ChatMessage]]:
        """
        Entry point called by the WebSocket controller for a user question.
        Responsibility:
          - ensure session exists and rebuild minimal LC history
          - emit the user message
          - time + run the agent via StreamTranscoder
          - persist session + history
          - record KPIs (success/error)
        """
        # Check if user is authorized to talk in this session
        if session_id is not None:
            await asyncio.to_thread(
                self._authorize_user_action_on_session, session_id, user, Action.UPDATE
            )

        logger.debug(
            "chat_ask_websocket user_id=%s session_id=%s agent=%s",
            user.uid,
            session_id,
            agent_name,
        )

        # KPI: count incoming question early (before any work)
        actor = KPIActor(type="human", user_id=user.uid, groups=user.groups)
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
        t_total = time.monotonic()
        # 1) Get or create the session. We receive a None session_id for new sessions.
        t_session = time.monotonic()
        session = await self._get_or_create_session(
            user_id=user.uid, query=message, session_id=session_id
        )
        _log_bench_phase(
            phase="session_get_create",
            start_ts=t_session,
            session_id=session.id,
            exchange_id=exchange_id,
            agent_name=agent_name,
        )
        # If this session was created with a placeholder title, refresh it now from the first prompt.
        t_title = time.monotonic()
        await self._maybe_refresh_title_from_prompt(session=session, prompt=message)
        _log_bench_phase(
            phase="title_refresh",
            start_ts=t_title,
            session_id=session.id,
            exchange_id=exchange_id,
            agent_name=agent_name,
        )
        # Propagate effective session_id into runtime context so downstream calls
        # (vector search, attachments) can scope to the correct conversation.
        runtime_context.session_id = session.id
        # 2) Check if an agent instance can be created/initialized/reused
        t_agent_init = time.monotonic()
        agent, is_cached = await self.agent_factory.create_and_init(
            agent_name=agent_name,
            runtime_context=runtime_context,
            session_id=session.id,
        )
        _log_bench_phase(
            phase="agent_init",
            start_ts=t_agent_init,
            session_id=session.id,
            exchange_id=exchange_id,
            agent_name=agent_name,
            cached=is_cached,
        )
        cache_result = "hit" if is_cached else "miss"
        self.kpi.count(
            "agent.cache_lookup_total",
            1,
            dims={"agent_id": agent_name, "result": cache_result},
            actor=actor,
        )

        try:
            # 3) Rebuild minimal LangChain history (user/assistant/system only),
            # This method will only restore history if the agent is not cached.
            lc_history: List[AnyMessage] = []
            if not is_cached:
                t_restore = time.monotonic()
                lc_history = await asyncio.to_thread(
                    self._restore_history,
                    user=user,
                    session=session,
                )
                _log_bench_phase(
                    phase="history_restore",
                    start_ts=t_restore,
                    session_id=session.id,
                    exchange_id=exchange_id,
                    agent_name=agent_name,
                    count=len(lc_history),
                )
                label = f"agent={agent_name} session={session.id}"
                log_agent_message_summary(lc_history, label=label)

            rank_lock = self.get_rank_lock(session.id)
            async with rank_lock:
                t_rank = time.monotonic()
                base_rank = await self._ensure_next_rank(session)
                _log_bench_phase(
                    phase="rank_seed",
                    start_ts=t_rank,
                    session_id=session.id,
                    exchange_id=exchange_id,
                    agent_name=agent_name,
                    base_rank=base_rank,
                )

                # 4) Emit the user message immediately
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

                # Stream agent responses via the transcoder
                saw_final_assistant = False
                agent_msgs: List[ChatMessage] = []
                had_error = False
                had_cancelled = False
                error_code: Optional[str] = None
                try:
                    # Timer covers the entire exchange; default status="ok" unless overridden.
                    with self.kpi.timer(
                        "chat.exchange_latency_ms",
                        dims={
                            "agent_id": agent_name,
                            "user_id": user.uid,
                            "session_id": session.id,
                            "exchange_id": exchange_id,
                        },
                        actor=actor,
                    ) as kpi_dims:
                        # Build input messages ensuring the last message is the Human question.
                        input_messages = lc_history + [HumanMessage(message)]

                        stream_start = time.monotonic()
                        stream_status = "ok"
                        try:
                            agent_msgs = await self.transcoder.stream_agent_response(
                                agent=agent,
                                input_messages=input_messages,
                                session_id=session.id,
                                exchange_id=exchange_id,
                                agent_name=agent_name,
                                base_rank=base_rank,
                                start_seq=1,  # user message already consumed rank=base_rank
                                callback=callback,
                                user_context=user,
                                runtime_context=runtime_context,
                            )
                        except WebSocketDisconnect:
                            stream_status = "disconnect"
                            had_cancelled = True
                            error_code = "client_disconnect"
                            kpi_dims["status"] = "cancelled"
                            kpi_dims["error_code"] = error_code
                            logger.info(
                                "Agent execution cancelled by client disconnect (agent=%s session=%s exchange=%s)",
                                agent_name,
                                session.id,
                                exchange_id,
                            )
                        except asyncio.CancelledError:
                            stream_status = "cancelled"
                            had_cancelled = True
                            error_code = "cancelled"
                            kpi_dims["error_code"] = error_code
                            raise
                        except Exception:
                            stream_status = "error"
                            raise
                        finally:
                            _log_bench_phase(
                                phase="stream",
                                start_ts=stream_start,
                                session_id=session.id,
                                exchange_id=exchange_id,
                                agent_name=agent_name,
                                status=stream_status,
                            )
                        all_msgs.extend(agent_msgs)
                        # Success signal: exactly one assistant/final per exchange (enforced by transcoder)
                        saw_final_assistant = any(
                            (m.role == Role.assistant and m.channel == Channel.final)
                            for m in agent_msgs
                        )
                        # Error signal: explicit error marker from the transcoder.
                        for msg in agent_msgs:
                            extras = msg.metadata.extras if msg.metadata else {}
                            if (
                                extras.get("error") is True
                                or msg.channel == Channel.error
                            ):
                                had_error = True
                                error_code = extras.get("error_code") or error_code
                                break
                        if had_error:
                            kpi_dims["status"] = "error"
                            if error_code:
                                kpi_dims["error_code"] = error_code
                except asyncio.CancelledError:
                    logger.info(
                        "Agent execution cancelled by client (agent=%s session=%s exchange=%s)",
                        agent_name,
                        session.id,
                        exchange_id,
                    )
                    raise
                except Exception:
                    logger.exception("Agent execution failed")
                    # KPI timer already recorded status="error" on exception
                finally:
                    # Count the exchange outcome
                    exchange_status = (
                        "cancelled"
                        if had_cancelled
                        else (
                            "error"
                            if had_error
                            else ("ok" if saw_final_assistant else "error")
                        )
                    )
                    exchange_dims: Dict[str, str | None] = {
                        "agent_id": agent_name,
                        "user_id": user.uid,
                        "session_id": session.id,
                        "exchange_id": exchange_id,
                        "status": exchange_status,
                    }
                    if exchange_status in {"error", "cancelled"} and error_code:
                        exchange_dims["error_code"] = error_code
                    self.kpi.count(
                        "chat.exchange_total",
                        1,
                        dims=exchange_dims,
                        actor=actor,
                    )

                # 6) Attach the raw runtime context (single source of truth)
                self._attach_runtime_context(
                    runtime_context=runtime_context,
                    messages=agent_msgs,
                )

                # 7) Persist session + history
                t_persist = time.monotonic()
                session.updated_at = _utcnow_dt()
                session.next_rank = base_rank + len(all_msgs)
                await asyncio.to_thread(self.session_store.save, session)
                assert session.user_id == user.uid, "Session/user mismatch"
                # Save only the new messages; history stores are append/upsert-capable.
                await asyncio.to_thread(
                    self.history_store.save, session.id, all_msgs, user.uid
                )
                _log_bench_phase(
                    phase="persist",
                    start_ts=t_persist,
                    session_id=session.id,
                    exchange_id=exchange_id,
                    agent_name=agent_name,
                    messages=len(all_msgs),
                )

                _log_bench_phase(
                    phase="total",
                    start_ts=t_total,
                    session_id=session.id,
                    exchange_id=exchange_id,
                    agent_name=agent_name,
                )

                return session, all_msgs
        finally:
            self.agent_factory.release_agent(session.id, agent_name)
            stats = self.agent_factory.get_cache_stats()
            if stats:
                self.kpi.gauge(
                    "agent.cache_entries",
                    stats.size,
                    actor=actor,
                )
                self.kpi.gauge(
                    "agent.cache_inflight_total",
                    stats.in_use_total,
                    actor=actor,
                )
                self.kpi.gauge(
                    "agent.cache_inflight_entries",
                    stats.in_use_entries,
                    actor=actor,
                )
                self.kpi.gauge(
                    "agent.cache_evictions_total",
                    stats.evictions,
                    actor=actor,
                )
                self.kpi.gauge(
                    "agent.cache_blocked_evictions_total",
                    stats.blocked_evictions,
                    actor=actor,
                )

    # ---------------- Session/History helpers (intentionally here) ----------------

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_sessions(
        self,
        user: KeycloakUser,
    ) -> List[SessionWithFiles]:
        """
        Get all sessions for a user, enriched with the list of uploaded files.
        This method is only used by the UI to list sessions. It is not part of the
        chat exchange flow.
        """
        sessions = self.session_store.get_for_user(user.uid)
        enriched: List[SessionWithFiles] = []
        for session in sessions:
            if not self._is_user_action_authorized_on_session(
                session.id, user, Action.READ
            ):
                continue

            # Retrieve all agents
            history = self.get_session_history(session.id, user)
            agents = {
                msg.metadata.agent_name for msg in history if msg.metadata.agent_name
            }

            files_names: list[str] = []
            attachments: list[AttachmentRef] = []
            if self.attachments_store:
                try:
                    records = self.attachments_store.list_for_session(session.id)
                    files_names = [r.name for r in records]
                    attachments = [
                        AttachmentRef(id=r.attachment_id, name=r.name) for r in records
                    ]
                except Exception:
                    logger.exception(
                        "[SESSIONS] Failed to load attachments for session %s",
                        session.id,
                    )
            enriched.append(
                SessionWithFiles(
                    **session.model_dump(),
                    agents=agents,
                    file_names=files_names,
                    attachments=attachments,
                )
            )
        return enriched

    @authorize(action=Action.CREATE, resource=Resource.SESSIONS)
    def create_empty_session(
        self,
        user: KeycloakUser,
        agent_name: Optional[str] = None,
        title: Optional[str] = None,
    ) -> SessionSchema:
        """Explicitly create a new empty session (used by the UI before first upload/message)."""
        prefs: Optional[Dict[str, Any]] = (
            {"agent_name": agent_name} if agent_name else None
        )
        session = SessionSchema(
            id=secrets.token_urlsafe(8),
            user_id=user.uid,
            agent_name=agent_name,
            title=title or "New conversation",
            updated_at=_utcnow_dt(),
            preferences=prefs,
            next_rank=0,
        )
        self.session_store.save(session)
        logger.info(
            "[SESSIONS] Created empty session %s for user %s", session.id, user.uid
        )
        return session

    async def _maybe_refresh_title_from_prompt(
        self, *, session: SessionSchema, prompt: str
    ) -> None:
        """
        If a session was created with a placeholder title (e.g., via create_empty_session),
        generate a better one from the user's first question.
        """

        def _sanitize_title(raw: str) -> str:
            cleaned = raw.replace("\n", " ").strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            cleaned = re.sub(r"[^\w\s'-]", "", cleaned)
            words = cleaned.split()
            if len(words) > 5:
                cleaned = " ".join(words[:5])
            return cleaned[:80].strip()

        try:
            if session.title and session.title.strip().lower() != "new conversation":
                return
            prompt_text = (
                "Give a short, clear title for this conversation based on the user's question. "
                "Summarize the user intent in 3 to 5 words. "
                "Avoid special characters and punctuation. "
                "Return ONLY the title (no prefix), keep the same language as the question, and do not translate.\n\n"
                "User question: " + prompt
            )
            model = get_default_model()
            resp = await model.ainvoke(prompt_text)
            raw_title = resp.content if hasattr(resp, "content") else str(resp)
            logger.debug(
                "[SESSIONS] Title generation raw response model=%s prompt=%s raw=%s",
                getattr(model, "model", None) or type(model).__name__,
                prompt_text,
                raw_title,
            )
            new_title = _sanitize_title(raw_title)
            if not new_title:
                raise ValueError("Empty title from model")
            session.title = new_title
        except Exception:
            # Fallback: first few words of the prompt
            logger.warning("[SESSIONS] Failed to refresh session title", exc_info=True)
            words = prompt.strip().split()
            session.title = " ".join(words[:6]) if words else "New conversation"

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_session_history(
        self,
        session_id: str,
        user: KeycloakUser,
        limit: int | None = None,
        offset: int = 0,
    ) -> List[ChatMessage]:
        self._authorize_user_action_on_session(session_id, user, Action.READ)
        history = self.history_store.get(session_id) or []
        if limit is None:
            return history
        total = len(history)
        end = max(0, total - offset)
        start = max(0, end - limit)
        return history[start:end]

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_session_message(
        self, session_id: str, rank: int, user: KeycloakUser
    ) -> ChatMessage:
        self._authorize_user_action_on_session(session_id, user, Action.READ)
        history = self.history_store.get(session_id) or []
        for msg in history:
            if msg.rank == rank:
                return msg
        raise HTTPException(
            status_code=404,
            detail={
                "code": "message_not_found",
                "message": f"Message rank {rank} not found in session {session_id}.",
            },
        )

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_session_preferences(
        self, session_id: str, user: KeycloakUser
    ) -> Dict[str, Any]:
        """Return stored per-session preferences, if any."""
        self._authorize_user_action_on_session(session_id, user, Action.READ)
        session = self.session_store.get(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "message": f"Session {session_id} not found.",
                },
            )
        logger.info(
            "[SESSIONS][PREFS] Retrieved preferences for session=%s user=%s prefs=%s",
            session_id,
            user.uid,
            session.preferences,
        )
        prefs = session.preferences or {}
        # If the session was created with a chosen agent, surface it as a default pref.
        if "agent_name" not in prefs and session.agent_name:
            prefs = {**prefs, "agent_name": session.agent_name}
        return prefs

    @authorize(action=Action.UPDATE, resource=Resource.SESSIONS)
    def update_session_preferences(
        self, session_id: str, user: KeycloakUser, preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Replace the stored preferences blob for a session."""
        self._authorize_user_action_on_session(session_id, user, Action.UPDATE)
        session = self.session_store.get(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "message": f"Session {session_id} not found.",
                },
            )
        session.preferences = preferences or {}
        # Keep session.agent_name in sync with the latest user-selected agent, if provided.
        try:
            agent_name = session.preferences.get("agent_name")
            if isinstance(agent_name, str) and agent_name.strip():
                session.agent_name = agent_name.strip()
        except Exception:
            logger.warning(
                "[SESSIONS][PREFS] Failed to update agent_name in session=%s preferences: %s",
                session_id,
                session.preferences,
                exc_info=True,
            )
            pass
        # Important: do NOT bump session.updated_at for preference changes.
        # The UI orders conversations by updated_at and expects it to change only
        # on actual conversation activity (messages), not when viewing/toggling settings.
        self.session_store.save(session)
        try:
            prefs_str = json.dumps(session.preferences, default=str)
        except Exception:
            prefs_str = str(session.preferences)
        logger.info(
            "[SESSIONS][PREFS] Persisted preferences for session=%s user=%s keys=%s values=%s",
            session_id,
            user.uid,
            ",".join(sorted(session.preferences.keys())),
            prefs_str,
        )
        return session.preferences

    @authorize(action=Action.DELETE, resource=Resource.SESSIONS)
    async def delete_session(
        self, session_id: str, user: KeycloakUser, access_token: Optional[str] = None
    ) -> None:
        self._authorize_user_action_on_session(session_id, user, Action.DELETE)
        # Collect doc_uids before clearing
        doc_uids: set[str] = set()
        if self.attachments_store:
            try:
                for rec in self.attachments_store.list_for_session(session_id):
                    if rec.document_uid:
                        doc_uids.add(rec.document_uid)
            except Exception:
                logger.exception(
                    "[SESSIONS] Failed to collect attachment doc_uids before delete for session %s",
                    session_id,
                )
        await self.agent_factory.teardown_session_agents(session_id)
        self.session_store.delete(session_id)
        if self.attachments_store:
            self.attachments_store.delete_for_session(session_id)
        # Remote vector cleanup
        if doc_uids and access_token:
            client = KfFastTextClient(access_token=access_token)
            for doc_uid in doc_uids:
                try:
                    client.delete_ingested_vectors(doc_uid)
                    logger.info(
                        "[SESSIONS][ATTACH] Deleted vectors for doc_uid=%s (session cleanup)",
                        doc_uid,
                    )
                except Exception:
                    logger.warning(
                        "[SESSIONS][ATTACH] Failed to delete vectors for doc_uid=%s during session cleanup",
                        doc_uid,
                        exc_info=True,
                    )
        logger.info("[SESSIONS] Deleted session %s", session_id)

    # ---------------- File uploads (kept for backward compatibility) ----------------

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    async def delete_attachment(
        self,
        *,
        user: KeycloakUser,
        session_id: str,
        attachment_id: str,
        access_token: Optional[str] = None,
    ) -> None:
        """
        Delete an attachment from a session (persistence + vectors).
        """
        self._authorize_user_action_on_session(session_id, user, Action.UPDATE)
        doc_uid: Optional[str] = None
        if self.attachments_store:
            try:
                records = self.attachments_store.list_for_session(session_id)
                for rec in records:
                    if rec.attachment_id == attachment_id:
                        doc_uid = rec.document_uid
                        break
                self.attachments_store.delete(
                    session_id=session_id, attachment_id=attachment_id
                )
            except Exception:
                logger.exception(
                    "[SESSIONS][ATTACH] Failed to delete attachment record %s",
                    attachment_id,
                )
        if doc_uid and access_token:
            try:
                client = KfFastTextClient(access_token=access_token)
                client.delete_ingested_vectors(doc_uid)
                logger.info(
                    "[SESSIONS][ATTACH] Deleted vectors for doc_uid=%s (attachment removal)",
                    doc_uid,
                )
            except Exception:
                logger.warning(
                    "[SESSIONS][ATTACH] Failed to delete vectors for doc_uid=%s",
                    doc_uid,
                    exc_info=True,
                )
        logger.info(
            "[SESSIONS] Deleted attachment %s from session %s",
            attachment_id,
            session_id,
        )

    @authorize(action=Action.READ, resource=Resource.MESSAGE_ATTACHMENTS)
    async def get_attachment_summary(
        self,
        *,
        user: KeycloakUser,
        session_id: str,
        attachment_id: str,
    ) -> dict:
        """
        Return the stored markdown summary for a given attachment.
        """
        if not self.attachments_store:
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "attachments_disabled",
                    "message": "Attachment summaries are disabled (no attachment store configured).",
                },
            )

        self._authorize_user_action_on_session(session_id, user, Action.READ)

        try:
            records = self.attachments_store.list_for_session(session_id)
        except Exception:
            logger.exception(
                "[SESSIONS][ATTACH] Failed to list attachments for session %s",
                session_id,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "attachment_lookup_failed",
                    "message": "Failed to load attachment summaries.",
                },
            )

        record = next(
            (rec for rec in records if rec.attachment_id == attachment_id), None
        )
        if not record:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "attachment_not_found",
                    "message": f"Attachment {attachment_id} not found in session {session_id}.",
                },
            )

        return {
            "session_id": record.session_id,
            "attachment_id": record.attachment_id,
            "name": record.name,
            "summary_md": record.summary_md,
            "mime": record.mime,
            "size_bytes": record.size_bytes,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    @authorize(action=Action.CREATE, resource=Resource.SESSIONS)
    async def add_attachment_from_upload(
        self,
        *,
        user: KeycloakUser,
        access_token: str,
        session_id: Optional[str],
        file: UploadFile,
        max_chars: int = 12_000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> dict:
        """
        Fred rationale:
        - Zero temp-files: we stream the uploaded content to Knowledge Flow 'fast/text'.
        - Store compact text + vectors via Knowledge Flow; no in-memory cache is used.
        """
        if not self.attachments_store:
            logger.error(
                "[SESSIONS][ATTACH] Attachment uploads disabled: no attachments_store configured."
            )
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "attachments_disabled",
                    "message": "Attachment uploads are disabled (no attachment store configured).",
                },
            )
        # Enforce per-user attachment count limit
        max_files_user = self.max_attached_files_per_user
        try:
            if max_files_user is not None and self.attachments_store:
                total_for_user = 0
                # Count attachments across all sessions for this user
                for sess in self.session_store.get_for_user(user.uid):
                    try:
                        total_for_user += len(
                            self.attachments_store.list_for_session(sess.id)
                        )
                    except Exception:
                        logger.warning(
                            "[SESSIONS][ATTACH] Failed to count attachments for session %s",
                            sess.id,
                        )
                        continue
                if total_for_user >= max_files_user:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "attachment_limit_reached",
                            "message": f"Attachment limit reached ({max_files_user} files per user).",
                        },
                    )
        except HTTPException:
            raise
        except Exception:
            logger.exception("[SESSIONS][ATTACH] Failed to enforce attachment limit")
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "missing_filename",
                    "message": "Uploaded file must have a filename.",
                },
            )
        size_limit_bytes = self.max_attached_file_size_bytes
        if size_limit_bytes is not None:
            content = await file.read(size_limit_bytes + 1)
            if len(content) > size_limit_bytes:
                logger.warning(
                    "[SESSIONS][ATTACH] File too large: %s bytes=%d limit=%d (user=%s)",
                    file.filename,
                    len(content),
                    size_limit_bytes,
                    user.uid,
                )
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "attachment_too_large",
                        "message": f"Attachment exceeds limit ({self.max_attached_file_size_mb} MB).",
                    },
                )
        else:
            content = await file.read()  # stays in memory

        # If no session_id was provided (first interaction), create one now.
        # Use a lightweight title based on the filename to keep UX sensible.
        session = await self._get_or_create_session(
            user_id=user.uid,
            query=f"File: {file.filename}",
            session_id=session_id if session_id else None,
        )
        # Ensure the user has rights on this session (create/update if needed)
        self._authorize_user_action_on_session(session.id, user, Action.UPDATE)

        # 1) Secure session-mode client for Knowledge Flow (Bearer user token)
        client = KfFastTextClient(
            access_token=access_token,
            # Optional: refresh_user_access_token=lambda: self._refresh_user_token(user)
        )

        # 2) Ask KF to produce a compact Markdown (text-only) for conversational use
        try:
            # Build a compact summary for UI while ingesting full fast text below.
            summary_md = client.extract_text_from_bytes(
                filename=file.filename,
                content=content,
                mime=file.content_type,
                max_chars=max_chars,
                include_tables=include_tables,
                add_page_headings=add_page_headings,
            )
            summary_md = (summary_md or "").strip()
            if "\x00" in summary_md:
                # Some PDFs may surface NUL bytes; strip them to avoid DB errors.
                summary_md = summary_md.replace("\x00", "")
            if not summary_md:
                summary_md = "_(No summary returned by Knowledge Flow)_"
            logger.info(
                "[SESSIONS][ATTACH] Received summary for %s bytes=%d chars=%d",
                file.filename,
                len(content),
                len(summary_md),
            )
        except HTTPError as exc:  # Upstream format or processing failure
            status = exc.response.status_code if exc.response is not None else 502
            upstream_detail = (
                exc.response.text
                if getattr(exc, "response", None) is not None
                else str(exc)
            )
            logger.error(
                "Knowledge Flow rejected attachment %s (user=%s, status=%s, detail=%s)",
                file.filename,
                user.uid,
                status,
                upstream_detail,
            )
            raise HTTPException(
                status_code=status,
                detail={
                    "code": "upload_processing_failed",
                    "message": f"Failed to process {file.filename}.",
                    "upstream": upstream_detail,
                },
            ) from exc

        # 3) Create a stable attachment_id (UUID v4 is fine here)
        attachment_id = str(uuid.uuid4())

        # 3b) Ingest into vector store with session/user scoping
        document_uid: Optional[str] = None
        try:
            # Ingest full fast text (per-page) for higher recall; no max_chars cap.
            ingest_resp = client.ingest_text_from_bytes(
                filename=file.filename,
                content=content,
                session_id=session.id,
                scope="session",
                options={
                    "max_chars": None,
                    "include_tables": include_tables,
                    "add_page_headings": add_page_headings,
                    "return_per_page": True,
                },
            )
            document_uid = ingest_resp.get("document_uid")
            logger.info(
                "[SESSIONS][ATTACH] Ingested vectors doc_uid=%s chunks=%s",
                document_uid,
                ingest_resp.get("chunks"),
            )
        except HTTPError as exc:
            logger.error(
                "[SESSIONS][ATTACH] Vector ingest failed for %s (user=%s): %s",
                file.filename,
                user.uid,
                exc.response.text if exc.response is not None else str(exc),
            )
        except Exception:
            logger.exception(
                "[SESSIONS][ATTACH] Unexpected error during vector ingest for %s",
                file.filename,
            )

        # 4) Persist metadata for UI if configured
        if self.attachments_store:
            now = _utcnow_dt()
            try:
                self.attachments_store.save(
                    SessionAttachmentRecord(
                        session_id=session.id,
                        attachment_id=attachment_id,
                        name=file.filename,
                        summary_md=summary_md,
                        mime=file.content_type,
                        size_bytes=len(content),
                        document_uid=document_uid,
                        created_at=now,
                        updated_at=now,
                    )
                )
                logger.info(
                    "[SESSIONS][ATTACH] Persisted summary for session=%s attachment=%s chars=%d",
                    session.id,
                    attachment_id,
                    len(summary_md),
                )
            except Exception:
                logger.exception(
                    "[SESSIONS][ATTACH] Failed to persist attachment summary for session=%s attachment=%s",
                    session.id,
                    attachment_id,
                )

        # 5) Return a minimal DTO for the UI
        return {
            "session_id": session.id,
            "attachment_id": attachment_id,
            "filename": file.filename,
            "mime": file.content_type,
            "size_bytes": len(content),
            "preview_chars": min(len(summary_md), 300),  # hint for UI
            "session": session.model_dump(),
        }

    # ---------------- Metrics passthrough ----------------

    @authorize(action=Action.READ, resource=Resource.METRICS)
    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_metrics(
        self,
        user: KeycloakUser,
        start: str,
        end: str,
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
            user_id=user.uid,
        )

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_runtime_summary(self, user: KeycloakUser) -> ChatbotRuntimeSummary:
        """Return a simple per-user snapshot: sessions, active agents, attachments."""
        sessions = self.session_store.get_for_user(user.uid)
        session_ids = {s.id for s in sessions}
        sessions_total = len(session_ids)

        # Agent instances in cache filtered to these sessions
        try:
            active_keys = getattr(self.agent_factory, "list_active_keys", lambda: [])()
        except Exception:
            active_keys = []
        agents_active_total = sum(1 for sid, _ in active_keys if sid in session_ids)

        # Attachments across these sessions
        attachments_total = 0
        attachments_sessions = 0
        if self.attachments_store:
            try:
                for sid in session_ids:
                    records = self.attachments_store.list_for_session(sid)
                    if records:
                        attachments_sessions += 1
                        attachments_total += len(records)
            except Exception:
                logger.exception("[SESSIONS] Failed to compute attachment stats")
        max_att = 0

        return ChatbotRuntimeSummary(
            sessions_total=sessions_total,
            agents_active_total=agents_active_total,
            attachments_total=attachments_total,
            attachments_sessions=attachments_sessions,
            max_attachments_per_session=max_att,
        )

    # ---------------- internals ----------------

    def _authorize_user_action_on_session(
        self, session_id: str, user: KeycloakUser, action: Action
    ):
        """Raise an AuthorizationError if a user can't perform an action on a session"""
        if not self._is_user_action_authorized_on_session(session_id, user, action):
            raise AuthorizationError(
                user.uid,
                action.value,
                Resource.SESSIONS,
                f"Not authorized to {action.value} session {session_id}",
            )

    def _is_user_action_authorized_on_session(
        self, session_id: str, user: KeycloakUser, action: Action
    ) -> bool:
        """Check if a user can perform an action on a session"""
        session = self.session_store.get(session_id)
        if session is None:
            # A2A proxy sessions are not persisted locally; allow access to avoid noisy warnings.
            if session_id.startswith("a2a-"):
                return True
            return False

        # For now, ignore action, only owners can access their sessions
        # action is passed for future flexibility (ex: session sharing with attached permissions)
        return session.user_id == user.uid

    async def _emit(self, callback: CallbackType, message: ChatMessage) -> None:
        """
        Purpose:
          Uniformly support sync OR async callbacks from the WS layer without
          duplicating code at call sites.
        """
        result = callback(message.model_dump())
        if asyncio.iscoroutine(result):
            await result

    def _restore_history(
        self,
        *,
        user: KeycloakUser,
        session: SessionSchema,
    ) -> list[AnyMessage]:
        """
        Fred rationale:
        - Global order: strictly by rank (true chronology). Never sort by exchange_id.
        - Tool-call state is tracked **per exchange** (no cross-leak, no loss on interleave).
        - Emit ToolMessage only if its call_id exists in the **same exchange**.
        - Windowing by "last N exchanges" always keeps whole exchanges.
        """
        hist = self.get_session_history(session.id, user) or []
        if not hist:
            _rlog("empty", msg="No messages to restore", session_id=session.id)
            return []

        # 1) Chronology (rank is authoritative)
        hist = sorted(hist, key=lambda m: m.rank)
        try:
            min_rank = hist[0].rank if hist else None
            max_rank = hist[-1].rank if hist else None
            uniq_ex = len({m.exchange_id for m in hist})
        except Exception:
            min_rank = max_rank = None
            uniq_ex = None
        _rlog(
            "ordering",
            msg="Sorted history by rank",
            count=len(hist),
            order_by="rank",
            min_rank=min_rank,
            max_rank=max_rank,
            unique_exchanges=uniq_ex,
        )

        # 2) Optional window by last-N exchanges (keep whole exchanges)
        if getattr(self, "restore_max_exchanges", 0) > 0:
            last_ids: list[str] = []
            seen: set[str] = set()
            for m in reversed(hist):
                if m.exchange_id not in seen:
                    seen.add(m.exchange_id)
                    last_ids.append(m.exchange_id)
                    if len(last_ids) >= self.restore_max_exchanges:
                        break
            selected = set(last_ids)
            before = len(hist)
            hist = [m for m in hist if m.exchange_id in selected]
            hist = sorted(hist, key=lambda m: m.rank)
            try:
                min_rank = hist[0].rank if hist else None
                max_rank = hist[-1].rank if hist else None
            except Exception:
                min_rank = max_rank = None
            _rlog(
                "window",
                msg="Applied last-N exchanges window",
                kept=len(hist),
                dropped=before - len(hist),
                exchanges=last_ids,  # most-recent-first for readability
                order_by="rank",
                window_by="exchange_id",
                min_rank=min_rank,
                max_rank=max_rank,
            )

        lc_history: list[AnyMessage] = []

        # 3) Per-exchange tool-call context (robust to interleaving)
        from collections import defaultdict

        pending_tool_calls_by_ex: dict[str, list[dict]] = defaultdict(list)
        call_name_by_ex: dict[str, dict[str, str]] = defaultdict(dict)
        known_call_ids_by_ex: dict[str, set[str]] = defaultdict(set)
        current_exchange: str | None = None

        def flush_exchange_calls_if_any(ex_id: str | None):
            """If this exchange accumulated assistant tool_calls, emit a single AIMessage(tool_calls=[...])."""
            if not ex_id:
                return
            calls = pending_tool_calls_by_ex.get(ex_id)
            if calls:
                ai = AIMessage(content="", tool_calls=list(calls))
                lc_history.append(ai)
                _rlog(
                    "emit_ai_calls",
                    msg="Emitted AI(tool_calls)",
                    exchange_id=ex_id,
                    calls=[{"id": c.get("id"), "name": c.get("name")} for c in calls],
                )
                pending_tool_calls_by_ex[ex_id].clear()

        # 4) Replay
        for m in hist:
            # Exchange boundary: flush prior exchange batch (do NOT forget its state)
            if current_exchange is None:
                current_exchange = m.exchange_id
                _rlog(
                    "exchange_begin", msg="Begin exchange", exchange_id=current_exchange
                )
            elif m.exchange_id != current_exchange:
                flush_exchange_calls_if_any(current_exchange)
                _rlog("exchange_end", msg="End exchange", exchange_id=current_exchange)
                current_exchange = m.exchange_id
                _rlog(
                    "exchange_begin", msg="Begin exchange", exchange_id=current_exchange
                )

            # Assistant → accumulate tool_call parts (batched intent per exchange)
            if m.role == Role.assistant and m.channel == Channel.tool_call:
                for p in m.parts or []:
                    if isinstance(p, ToolCallPart):
                        args_raw = getattr(p, "args", None)
                        if isinstance(args_raw, dict):
                            args_obj = args_raw
                        elif isinstance(args_raw, str):
                            try:
                                args_obj = json.loads(args_raw)
                            except Exception:
                                args_obj = {"_raw": args_raw}
                        else:
                            args_obj = {}
                        call_id = p.call_id
                        name = p.name or "unnamed"
                        pending_tool_calls_by_ex[current_exchange].append(
                            {"id": call_id, "name": name, "args": args_obj}
                        )
                        if call_id:
                            known_call_ids_by_ex[current_exchange].add(call_id)
                        if call_id and p.name:
                            call_name_by_ex[current_exchange][call_id] = p.name
                        _rlog(
                            "acc_call",
                            msg="Accumulate tool_call",
                            exchange_id=current_exchange,
                            call_id=call_id,
                            name=name,
                        )
                continue

            # Tool result → only if matching call_id exists in THIS exchange
            if m.role == Role.tool and m.channel == Channel.tool_result:
                # Ensure the grouped AI(tool_calls=[...]) for *this* exchange precedes the ToolMessage(s).
                flush_exchange_calls_if_any(current_exchange)
                for p in m.parts or []:
                    if isinstance(p, ToolResultPart):
                        if p.call_id not in known_call_ids_by_ex[current_exchange]:
                            _rlog(
                                "skip_orphan_tool_result",
                                msg="Skip orphan ToolMessage (no matching call in this exchange)",
                                exchange_id=current_exchange,
                                call_id=p.call_id,
                            )
                            continue
                        content = p.content
                        if not isinstance(content, str):
                            try:
                                content = json.dumps(content, ensure_ascii=False)
                            except Exception:
                                content = str(content)
                        name = (
                            call_name_by_ex[current_exchange].get(p.call_id)
                            or "unknown_tool"
                        )
                        try:
                            tm = ToolMessage(
                                content=content, name=name, tool_call_id=p.call_id
                            )
                            lc_history.append(tm)
                            _rlog(
                                "emit_tool",
                                msg="Emitted ToolMessage",
                                exchange_id=current_exchange,
                                call_id=p.call_id,
                                name=name,
                                preview=_preview(content),
                            )
                        except Exception:
                            _rlog(
                                "emit_tool_error",
                                msg="Failed to restore ToolMessage",
                                exchange_id=current_exchange,
                                call_id=p.call_id,
                                name=name,
                            )
                            continue
                continue

            # Non-tool_call assistant/system/user → close any pending batch for THIS exchange
            flush_exchange_calls_if_any(current_exchange)

            if m.role == Role.user:
                text = _concat_text_parts(m.parts or [])
                hm = HumanMessage(text)
                lc_history.append(hm)
                _rlog(
                    "emit_human",
                    msg="Emitted HumanMessage",
                    exchange_id=current_exchange,
                    preview=_preview(text),
                )
                continue

            if m.role == Role.system:
                sys_txt = _concat_text_parts(m.parts or [])
                if sys_txt:
                    sm = SystemMessage(sys_txt)
                    lc_history.append(sm)
                    _rlog(
                        "emit_system",
                        msg="Emitted SystemMessage",
                        exchange_id=current_exchange,
                        preview=_preview(sys_txt),
                    )
                continue

            if m.role == Role.assistant:
                if m.channel != Channel.tool_call:
                    text = _concat_text_parts(m.parts or [])
                    am = AIMessage(text)
                    lc_history.append(am)
                    _rlog(
                        "emit_ai_text",
                        msg="Emitted AI text",
                        exchange_id=current_exchange,
                        preview=_preview(text),
                    )
                continue

            # Unknown/other roles → ignore (by design)

        # Tail: if transcript ends with pending calls and no results, keep the grouped AI(tool_calls=...)
        flush_exchange_calls_if_any(current_exchange)
        _rlog("restore_done", msg="Restoration complete", total=len(lc_history))

        return lc_history

    # --- Small, focused helpers to keep logs readable ---

    async def _get_or_create_session(
        self, *, user_id: str, query: str, session_id: Optional[str]
    ) -> SessionSchema:
        if session_id:
            existing = await asyncio.to_thread(self.session_store.get, session_id)
            if existing:
                logger.info(
                    "[AGENTS] resumed session %s for user %s", session_id, user_id
                )
                return existing

        new_session_id = secrets.token_urlsafe(8)
        response = await get_default_model().ainvoke(
            "Give a short, clear title for this conversation based on the user's question. "
            "Return a few keywords only. Question: " + query
        )
        title = response.content
        session = SessionSchema(
            id=new_session_id,
            user_id=user_id,
            title=title,
            updated_at=_utcnow_dt(),
            preferences=None,
            next_rank=0,
        )
        await asyncio.to_thread(self.session_store.save, session)
        logger.info(
            "[AGENTS] Created new session %s for user %s", new_session_id, user_id
        )
        return session

    # ---------------- runtime context attachment ----------------

    def _attach_runtime_context(
        self,
        *,
        runtime_context: Optional[RuntimeContext],
        messages: List[ChatMessage],
    ) -> None:
        """
        Attach the **raw RuntimeContext** to assistant/final messages.
        This is the canonical, unmodified source of truth.
        """
        if runtime_context is None:
            return
        for m in messages:
            if m.role == Role.assistant and m.channel == Channel.final:
                md = m.metadata or ChatMetadata()
                md.runtime_context = runtime_context
                m.metadata = md


# ---------- pure helpers (kept local for discoverability) ----------


def _concat_text_parts(parts) -> str:
    texts: list[str] = []
    for p in parts or []:
        if getattr(p, "type", None) == "text":
            txt = getattr(p, "text", None)
            if txt:
                texts.append(str(txt))
    return "\n".join(texts).strip()


def _rlog(event: str, **fields):
    """
    Structured restoration logs.
    Keep messages short; rely on fields for details. This makes grepping stable.
    """
    try:
        payload = " ".join(
            f"{k}={_safe(v)}" for k, v in fields.items() if v is not None
        )
    except Exception:
        payload = str(fields)
    logger.debug(f"[RESTORE] {event} | {payload}")


def _preview(content: str, limit: int = 90) -> str:
    if not content:
        return ""
    s = content.strip().replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _safe(v) -> str:
    if isinstance(v, (list, tuple, set)):
        return (
            "["
            + ", ".join([_safe(item) for item in list(v)[:5]])
            + ("]" if len(v) <= 5 else ", ...]")
        )
    if isinstance(v, dict):
        keys = list(v.keys())[:5]
        return (
            "{keys="
            + ",".join(str(k) for k in keys)
            + ("}" if len(v) <= 5 else ",...}")
        )
    if isinstance(v, str):
        v = v.replace("\n", " ")
        return f"'{v[:60]}...'" if len(v) > 63 else f"'{v}'"
    return repr(v)
