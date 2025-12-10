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
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fred_core import (
    Action,
    AuthorizationError,
    BaseKPIWriter,
    KeycloakUser,
    KPIActor,
    Resource,
    authorize,
)
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
from agentic_backend.common.kf_lite_markdown_client import KfLiteMarkdownClient
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import BaseAgentFactory
from agentic_backend.core.agents.agent_utils import log_agent_message_summary
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    set_attachments_markdown,
)
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
from agentic_backend.core.chatbot.session_in_memory_attachements import (
    SessionInMemoryAttachments,
)
from agentic_backend.core.chatbot.stream_transcoder import StreamTranscoder
from agentic_backend.core.monitoring.base_history_store import BaseHistoryStore
from agentic_backend.core.session.attachement_processing import AttachementProcessing
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)

# Callback type used by WS controller to push events to clients
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt() -> datetime:
    """UTC timestamp (seconds resolution) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


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
        agent_factory: BaseAgentFactory,
        history_store: BaseHistoryStore,
        kpi: BaseKPIWriter,
    ):
        self.session_store = session_store
        self.agent_factory = agent_factory
        self.attachments_memory_store = SessionInMemoryAttachments(1000, 4)
        logger.info(
            "[SESSIONS] Initialized attachments memory store max_sessions=%d max_per_session=%d",
            1000,
            4,
        )
        # Side services
        self.history_store = history_store
        self.kpi: BaseKPIWriter = kpi
        self.attachement_processing = AttachementProcessing()
        self.restore_max_exchanges = configuration.ai.restore_max_exchanges
        # Stateless worker that knows how to turn LangGraph events into ChatMessage[]
        self.transcoder = StreamTranscoder()

    # ---------------- Public API (used by WS layer) ----------------

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
            self._authorize_user_action_on_session(session_id, user, Action.UPDATE)

        logger.debug(
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
        # 1) Get or create the session. We receive a None session_id for new sessions.
        session = self._get_or_create_session(
            user_id=user.uid, query=message, session_id=session_id
        )
        # 2) Check if an agent instance can be created/initialized/reused
        agent, is_cached = await self.agent_factory.create_and_init(
            agent_name=agent_name,
            runtime_context=runtime_context,
            session_id=session.id,
        )
        # 3) Prepare optional attachments context (lite markdown) and make it available via runtime_context
        # this corresponds to the attached files that the user added to his conversation. These files are transformed to lite markdown format
        # in turn added to the runtime context so that the agent can use them during its reasoning
        attachments_context = (
            self.attachments_memory_store.get_session_attachments_markdown(session.id)
        )
        set_attachments_markdown(runtime_context, attachments_context)

        # 3) Rebuild minimal LangChain history (user/assistant/system only),
        # This method will only restore history if the agent is not cached.
        lc_history: List[AnyMessage] = []
        if not is_cached:
            lc_history = self._restore_history(
                user=user,
                session=session,
            )
            label = f"agent={agent_name} session={session.id}"
            log_agent_message_summary(lc_history, label=label)

        # Rank base = current stored history length
        prior: List[ChatMessage] = self.history_store.get(session.id) or []
        base_rank = len(prior)

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

        # 3) Prepare optional attachments context (lite markdown) and make it available via runtime_context

        # 4) Stream agent responses via the transcoder
        saw_final_assistant = False
        agent_msgs: List[ChatMessage] = []
        try:
            # Timer covers the entire exchange; status defaults to "error" if exception bubbles.
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
                # Build input messages ensuring the last message is the Human question.
                input_messages = lc_history + [HumanMessage(message)]

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
                all_msgs.extend(agent_msgs)
                # Success signal: exactly one assistant/final per exchange (enforced by transcoder)
                saw_final_assistant = any(
                    (m.role == Role.assistant and m.channel == Channel.final)
                    for m in agent_msgs
                )
        except Exception:
            logger.exception("Agent execution failed")
            # KPI timer already recorded status="error" on exception
        finally:
            # Count the exchange outcome
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

        # 6) Attach the raw runtime context (single source of truth)
        self._attach_runtime_context(
            runtime_context=runtime_context,
            messages=agent_msgs,
        )

        # 7) Persist session + history
        session.updated_at = _utcnow_dt()
        self.session_store.save(session)
        assert session.user_id == user.uid, "Session/user mismatch"
        self.history_store.save(session.id, prior + all_msgs, user.uid)

        return session, all_msgs

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
            files_names = self.attachments_memory_store.get_session_attachment_names(
                session.id
            )
            id_name_pairs = (
                self.attachments_memory_store.get_session_attachment_id_name_pairs(
                    session.id
                )
            )
            attachments = [
                AttachmentRef(id=att_id, name=name) for att_id, name in id_name_pairs
            ]
            enriched.append(
                SessionWithFiles(
                    **session.model_dump(),
                    file_names=files_names,
                    attachments=attachments,
                )
            )
        return enriched

    @authorize(action=Action.READ, resource=Resource.SESSIONS)
    def get_session_history(
        self, session_id: str, user: KeycloakUser
    ) -> List[ChatMessage]:
        self._authorize_user_action_on_session(session_id, user, Action.READ)
        return self.history_store.get(session_id) or []

    @authorize(action=Action.DELETE, resource=Resource.SESSIONS)
    async def delete_session(self, session_id: str, user: KeycloakUser) -> None:
        self._authorize_user_action_on_session(session_id, user, Action.DELETE)
        await self.agent_factory.teardown_session_agents(session_id)
        self.session_store.delete(session_id)
        self.attachments_memory_store.clear_session(session_id)
        logger.info("[SESSIONS] Deleted session %s", session_id)

    # ---------------- File uploads (kept for backward compatibility) ----------------

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    async def delete_attachment(
        self,
        *,
        user: KeycloakUser,
        session_id: str,
        attachment_id: str,
    ) -> None:
        """
        Delete an in-memory attachment from a session.
        """
        self._authorize_user_action_on_session(session_id, user, Action.UPDATE)
        self.attachments_memory_store.delete(
            session_id=session_id, attachment_id=attachment_id
        )
        logger.info(
            "[SESSIONS] Deleted attachment %s from session %s",
            attachment_id,
            session_id,
        )

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    @authorize(action=Action.CREATE, resource=Resource.SESSIONS)
    async def add_attachment_from_upload(
        self,
        *,
        user: KeycloakUser,
        access_token: str,
        session_id: Optional[str],
        file: UploadFile,
        max_chars: int = 30_000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> dict:
        """
        Fred rationale:
        - Zero temp-files: we stream the uploaded content to Knowledge Flow 'lite/markdown'.
        - We store ONLY the compact Markdown summary in RAM (SessionInMemoryAttachments).
        - This powers 'retrieval implicite' in subsequent turns, exactly as designed.
        """
        supported_suffixes = {
            ".pdf",
            ".docx",
            ".csv",
        }
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "missing_filename",
                    "message": "Uploaded file must have a filename.",
                },
            )
        suffix = Path(file.filename).suffix.lower()
        if suffix not in supported_suffixes:
            logger.warning(
                "Unsupported upload extension rejected: %s (user=%s)",
                file.filename,
                user.uid,
            )
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "unsupported_file_type",
                    "message": f"Unsupported file type '{suffix or file.filename}'. Allowed: {', '.join(sorted(supported_suffixes))}.",
                },
            )
        content = await file.read()  # stays in memory

        # If no session_id was provided (first interaction), create one now.
        # Use a lightweight title based on the filename to keep UX sensible.
        session = self._get_or_create_session(
            user_id=user.uid,
            query=f"File: {file.filename}",
            session_id=session_id if session_id else None,
        )
        # Ensure the user has rights on this session (create/update if needed)
        self._authorize_user_action_on_session(session.id, user, Action.UPDATE)

        # 1) Secure session-mode client for Knowledge Flow (Bearer user token)
        client = KfLiteMarkdownClient(
            access_token=access_token,
            # Optional: refresh_user_access_token=lambda: self._refresh_user_token(user)
        )

        # 2) Ask KF to produce a compact Markdown (text-only) for conversational use
        try:
            summary_md = client.extract_markdown_from_bytes(
                filename=file.filename,
                content=content,
                mime=file.content_type,
                max_chars=max_chars,
                include_tables=include_tables,
                add_page_headings=add_page_headings,
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

        # 4) Put into in-RAM session cache for implicit retrieval
        self.attachments_memory_store.put(
            session_id=session.id,
            attachment_id=attachment_id,
            name=file.filename,
            summary_md=summary_md,
            mime=file.content_type,
            size_bytes=len(content),
        )

        # 5) Return a minimal DTO for the UI
        return {
            "session_id": session.id,
            "attachment_id": attachment_id,
            "filename": file.filename,
            "mime": file.content_type,
            "size_bytes": len(content),
            "preview_chars": min(len(summary_md), 300),  # hint for UI
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
        for sid in session_ids:
            ids = self.attachments_memory_store.list_ids(sid)
            if ids:
                attachments_sessions += 1
                attachments_total += len(ids)

        att_stats = self.attachments_memory_store.stats()
        max_att = int(att_stats.get("max_attachments_per_session", 0))

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

    def _get_or_create_session(
        self, *, user_id: str, query: str, session_id: Optional[str]
    ) -> SessionSchema:
        if session_id:
            existing = self.session_store.get(session_id)
            if existing:
                logger.info(
                    "[AGENTS] resumed session %s for user %s", session_id, user_id
                )
                return existing

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


def _safe(v):
    if isinstance(v, (list, tuple, set)):
        return (
            "["
            + ", ".join(map(_safe, list(v)[:5]))
            + ("]" if len(v) <= 5 else ", ...]")
        )
    if isinstance(v, dict):
        keys = list(v.keys())[:5]
        return "{keys=" + ",".join(keys) + ("}" if len(v) <= 5 else ",...}")
    if isinstance(v, str):
        v = v.replace("\n", " ")
        return f"'{v[:60]}...'" if len(v) > 63 else f"'{v}'"
    return repr(v)
