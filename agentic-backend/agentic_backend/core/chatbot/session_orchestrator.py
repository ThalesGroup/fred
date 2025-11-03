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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile
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

from agentic_backend.application_context import (
    get_default_model,
)
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import BaseAgentFactory
from agentic_backend.core.agents.agent_utils import log_agent_message_summary
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
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
                agent_msgs = await self.transcoder.stream_agent_response(
                    agent=agent,
                    input_messages=lc_history + [HumanMessage(message)],
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

        # 4) Persist session + history
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
        sessions = self.session_store.get_for_user(user.uid)
        enriched: List[SessionWithFiles] = []
        for session in sessions:
            if not self._is_user_action_authorized_on_session(
                session.id, user, Action.READ
            ):
                continue

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

    # ---------------- File uploads (kept for backward compatibility) ----------------

    @authorize(action=Action.CREATE, resource=Resource.MESSAGE_ATTACHMENTS)
    async def upload_file(
        self, user: KeycloakUser, session_id: str, agent_name: str, file: UploadFile
    ) -> dict:
        """
        Purpose:
          Keep simple "drop a file into this session's temp area" behavior unchanged,
          so the UI doesn't need to move right now. Can be split later to a dedicated service.
        """
        self._authorize_user_action_on_session(session_id, user, Action.UPDATE)
        try:
            session_folder = self._get_session_temp_folder(session_id)
            if file.filename is None:
                raise ValueError("Uploaded file must have a filename.")
            file_path = session_folder / file.filename
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            # Kick attachment processing (same behavior as before)
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

    def _get_session_temp_folder(self, session_id: str) -> Path:
        base_temp_dir = Path(tempfile.gettempdir()) / "chatbot_uploads"
        session_folder = base_temp_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        return session_folder

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
