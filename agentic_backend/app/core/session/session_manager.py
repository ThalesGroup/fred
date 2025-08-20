# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Sequence
from uuid import uuid4

from fastapi import UploadFile
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from app.application_context import (
    get_configuration,
    get_default_model,
    get_history_store,
)
from app.core.agents.agent_manager import AgentManager
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import RuntimeContext
from app.core.chatbot.chat_schema import (
    ChatMessage,
    ChatMetadata,
    ChatTokenUsage,
    Channel,
    FinishReason,
    Role,
    SessionSchema,
    SessionWithFiles,
    MessagePart,
    TextPart,
    CodePart,
    ImageUrlPart,
    ToolCallPart,
    ToolResultPart,
)
from app.core.chatbot.metric_structures import MetricsResponse
from app.core.session.stores.base_session_store import BaseSessionStore
from app.core.session.attachement_processing import AttachementProcessing

logger = logging.getLogger(__name__)

# Type for callback functions (sync or async)
CallbackType = Callable[[Dict], None] | Callable[[Dict], Awaitable[None]]


def utcnow_dt() -> datetime:
    """UTC timestamp (seconds resolution) for pydantic to serialize as ISO-8601."""
    return datetime.now(timezone.utc).replace(microsecond=0)


# ---------------- helpers (v2-native, strongly typed) ----------------

def _parts_from_raw_content(raw: Any) -> List[MessagePart]:
    """
    Convert LangChain/OpenAI-style content into v2 MessagePart models.
    Supports: text, image_url, light code heuristic for multi-line text blocks.
    """
    parts: List[MessagePart] = []
    if raw is None:
        return parts

    if isinstance(raw, str):
        if raw.strip():
            parts.append(TextPart(text=raw))
        return parts

    if isinstance(raw, list):
        for itm in raw:
            if isinstance(itm, dict):
                t = itm.get("type")
                if t in ("text", "input_text"):
                    txt = itm.get("text") or itm.get("input_text")
                    if txt:
                        parts.append(TextPart(text=str(txt)))
                elif t == "image_url":
                    url = (itm.get("image_url") or {}).get("url")
                    if url:
                        parts.append(ImageUrlPart(url=url))
                elif t == "input_text" and isinstance(itm.get("text"), str) and "\n" in itm["text"]:
                    parts.append(CodePart(code=itm["text"]))
        return parts

    parts.append(TextPart(text=str(raw)))
    return parts


def _concat_text_parts(parts: Sequence[MessagePart]) -> str:
    texts: List[str] = []
    for p in parts or []:
        if getattr(p, "type", None) == "text":
            txt = getattr(p, "text", None)
            if txt:
                texts.append(str(txt))
    return "\n".join(texts).strip()


def _extract_tool_calls(msg: Any) -> List[dict]:
    """
    Normalize tool calls from AIMessage:
      - OpenAI: msg.tool_calls or msg.additional_kwargs['tool_calls']
      - Each call → {call_id, name, args(dict)}
    """
    calls = []
    tc = getattr(msg, "tool_calls", None)
    if not tc:
        add = getattr(msg, "additional_kwargs", {}) or {}
        tc = add.get("tool_calls")
    if not tc:
        return calls

    for i, c in enumerate(tc):
        cid = c.get("id") or f"t{i+1}"
        if "function" in c:
            fn = c["function"] or {}
            name = fn.get("name") or "unnamed"
            args_raw = fn.get("arguments")
        else:
            name = c.get("name") or "unnamed"
            args_raw = c.get("args")

        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {"_raw": args_raw}
        elif isinstance(args_raw, dict):
            args = args_raw
        else:
            args = {"_raw": args_raw}

        calls.append({"call_id": cid, "name": name, "args": args})
    return calls


def _clean_token_usage(raw: dict | None) -> Optional[ChatTokenUsage]:
    if not raw:
        return None
    try:
        return ChatTokenUsage(
            input_tokens=int(raw.get("input_tokens", 0) or 0),
            output_tokens=int(raw.get("output_tokens", 0) or 0),
            total_tokens=int(raw.get("total_tokens", 0) or 0),
        )
    except Exception:
        return None


def _coerce_finish_reason(val: Any) -> Optional[FinishReason]:
    if val is None:
        return None
    try:
        return FinishReason(str(val))
    except Exception:
        return FinishReason.other


# ---------------- SessionManager (v2) ----------------

class SessionManager:
    """
    Manages user sessions and interactions with the chatbot using Chat Protocol v2.
    """

    def __init__(self, session_store: BaseSessionStore, agent_manager: AgentManager):
        self.session_store = session_store
        self.agent_manager = agent_manager
        self.temp_files: dict[str, list[str]] = defaultdict(list)
        self.attachement_processing = AttachementProcessing()
        self.history_store = get_history_store()
        config = get_configuration()
        self.recursion_limit = config.ai.recursion.recursion_limit

    # ---------------- high-level API ----------------

    async def chat_ask_websocket(
        self,
        callback: CallbackType,
        user_id: str,
        session_id: str,
        message: str,
        agent_name: str,
        runtime_context: Optional[RuntimeContext] = None,
        client_exchange_id: Optional[str] = None,
    ) -> Tuple[SessionSchema, List[ChatMessage]]:
        logger.info(
            "chat_ask_websocket user_id=%s session_id=%s agent=%s",
            user_id,
            session_id,
            agent_name,
        )

        session, history_msgs, agent, _is_new_session = self._prepare_session_and_history(
            user_id=user_id,
            session_id=session_id,
            message=message,
            agent_name=agent_name,
            runtime_context=runtime_context,
        )
        exchange_id = client_exchange_id or str(uuid4())

        # Rank base = current stored history length
        prior: List[ChatMessage] = self.history_store.get(session.id) or []
        base_rank = len(prior)
        seq = 0

        # 1) User message
        user_parts: List[MessagePart] = [TextPart(text=message)]
        user_msg = ChatMessage(
            session_id=session.id,
            exchange_id=exchange_id,
            rank=base_rank + seq,
            timestamp=utcnow_dt(),
            role=Role.user,
            channel=Channel.final,
            parts=user_parts,
            metadata=ChatMetadata(),
        )
        all_msgs: List[ChatMessage] = [user_msg]
        await self._emit(callback, user_msg)

        # 2) Stream agent responses from LangGraph
        try:
            agent_msgs = await self._stream_agent_response(
                compiled_graph=agent.get_compiled_graph(),
                input_messages=history_msgs + [HumanMessage(message)],
                session_id=session.id,
                exchange_id=exchange_id,
                agent_name=agent_name,
                user_id=user_id,
                base_rank=base_rank,
                start_seq=seq + 1,
                callback=callback,
            )
            all_msgs.extend(agent_msgs)
        except Exception:
            logger.exception("Agent execution failed")

        # 3) Persist
        session.updated_at = utcnow_dt()
        self.session_store.save(session)
        assert session.user_id == user_id, "Session/user mismatch"
        self.history_store.save(session.id, prior + all_msgs, user_id)
        return session, all_msgs

    # ---------------- internals ----------------

    def _prepare_session_and_history(
        self,
        user_id: str,
        session_id: Optional[str],
        message: str,
        agent_name: str,
        runtime_context: Optional[RuntimeContext] = None,
    ) -> Tuple[SessionSchema, List[BaseMessage], AgentFlow, bool]:
        session, is_new_session = self._get_or_create_session(
            user_id, message, session_id
        )

        # Rebuild minimal LangChain history (user/assistant/system only)
        lc_history: List[BaseMessage] = []
        for m in self.get_session_history(session.id, user_id):
            if m.role == Role.user:
                lc_history.append(HumanMessage(_concat_text_parts(m.parts or [])))
            elif m.role == Role.assistant:
                md = m.metadata.model_dump() if m.metadata else {}
                lc_history.append(AIMessage(content=_concat_text_parts(m.parts or []), response_metadata=md))
            elif m.role == Role.system:
                lc_history.append(SystemMessage(_concat_text_parts(m.parts or [])))
            # We ignore Role.tool in LC history; not needed for a fresh exchange.

        agent = self.agent_manager.get_agent_instance(agent_name, runtime_context)
        return session, lc_history, agent, is_new_session

    def _get_or_create_session(
        self, user_id: str, query: str, session_id: Optional[str]
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
            id=new_session_id, user_id=user_id, title=title, updated_at=utcnow_dt()
        )
        self.session_store.save(session)
        logger.info("Created new session %s for user %s", new_session_id, user_id)
        return session, True

    async def _stream_agent_response(
        self,
        *,
        compiled_graph: CompiledStateGraph,
        input_messages: List[BaseMessage],
        session_id: str,
        exchange_id: str,
        agent_name: str,
        user_id: str,
        base_rank: int,
        start_seq: int,
        callback: CallbackType,
    ) -> List[ChatMessage]:
        """
        Execute the agentic flow and stream v2 ChatMessage dicts via `callback`.
        Returns the collected ChatMessage list. Exactly one assistant/final per exchange.
        """
        config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": get_configuration().ai.recursion.recursion_limit,
        }
        out: List[ChatMessage] = []
        seq = start_seq
        final_sent = False

        async for event in compiled_graph.astream(
            {"messages": input_messages},
            config=config,
            stream_mode="updates",
        ):
            # event like {'node_name': {'messages': [...]}} or {'end': None}
            key = next(iter(event))
            payload = event[key]
            if not isinstance(payload, dict):
                continue
            block = payload.get("messages", []) or []
            if not block:
                continue

            for msg in block:
                raw_md = getattr(msg, "response_metadata", {}) or {}
                usage_raw = getattr(msg, "usage_metadata", {}) or {}

                model_name = raw_md.get("model_name") or raw_md.get("model")
                finish_reason = _coerce_finish_reason(raw_md.get("finish_reason"))
                token_usage = _clean_token_usage(usage_raw)

                # --- TOOL CALLS ---
                tool_calls = _extract_tool_calls(msg)
                if tool_calls:
                    for tc in tool_calls:
                        tc_msg = ChatMessage(
                            session_id=session_id,
                            exchange_id=exchange_id,
                            rank=base_rank + seq,
                            timestamp=utcnow_dt(),
                            role=Role.assistant,
                            channel=Channel.tool_call,
                            parts=[ToolCallPart(
                                call_id=tc["call_id"],
                                name=tc["name"],
                                args=tc["args"],
                            )],
                            metadata=ChatMetadata(
                                model=model_name,
                                token_usage=token_usage,
                                agent_name=agent_name,
                                finish_reason=finish_reason,
                                extras=raw_md.get("extras", {}),
                                sources=raw_md.get("sources") or [],
                            ),
                        )
                        out.append(tc_msg)
                        seq += 1
                        await self._emit(callback, tc_msg)
                    continue  # tool_calls consume this message

                # --- TOOL RESULT ---
                if getattr(msg, "type", "") == "tool":
                    call_id = getattr(msg, "tool_call_id", None) or raw_md.get("tool_call_id") or "t?"
                    content_str = getattr(msg, "content", "")
                    if not isinstance(content_str, str):
                        content_str = json.dumps(content_str)
                    tr_msg = ChatMessage(
                        session_id=session_id,
                        exchange_id=exchange_id,
                        rank=base_rank + seq,
                        timestamp=utcnow_dt(),
                        role=Role.tool,
                        channel=Channel.tool_result,
                        parts=[ToolResultPart(
                            call_id=call_id,
                            ok=True,
                            latency_ms=raw_md.get("latency_ms"),
                            content=content_str,
                        )],
                        metadata=ChatMetadata(agent_name=agent_name, 
                                              extras=raw_md.get("extras") or {},
                                              sources=raw_md.get("sources") or [],),
                    )
                    out.append(tr_msg)
                    seq += 1
                    await self._emit(callback, tr_msg)
                    continue

                # --- ASSISTANT / SYSTEM TEXTUAL MESSAGES ---
                lc_type = getattr(msg, "type", "ai")
                role = {
                    "ai": Role.assistant,
                    "system": Role.system,
                    "human": Role.user,
                    "tool": Role.tool,
                }.get(lc_type, Role.assistant)

                parts = _parts_from_raw_content(getattr(msg, "content", ""))
                
                
                # Thought trace (optional)
                if "thought" in raw_md:
                    thought_txt = raw_md["thought"]
                    if isinstance(thought_txt, (dict, list)):
                        thought_txt = json.dumps(thought_txt, ensure_ascii=False)
                    if str(thought_txt).strip():
                        thought_msg = ChatMessage(
                            session_id=session_id,
                            exchange_id=exchange_id,
                            rank=base_rank + seq,
                            timestamp=utcnow_dt(),
                            role=Role.assistant,
                            channel=Channel.thought,
                            parts=[TextPart(text=str(thought_txt))],
                            metadata=ChatMetadata(agent_name=agent_name, extras=raw_md.get("extras") or {}),
                        )
                        out.append(thought_msg)
                        seq += 1
                        await self._emit(callback, thought_msg)

                # Channel selection
                if role == Role.assistant:
                    ch = Channel.final if (parts and not final_sent) else Channel.observation
                    if ch == Channel.final:
                        final_sent = True
                elif role == Role.system:
                    ch = Channel.system_note
                elif role == Role.user:
                    ch = Channel.final
                else:
                    ch = Channel.observation
                
                if role == "assistant" and ch == "observation":
                    if not parts or all(p.type=="text" and not p.text.strip() for p in parts):
                        continue  # skip sending this is a langgraph intermediary step message

                msg_v2 = ChatMessage(
                    session_id=session_id,
                    exchange_id=exchange_id,
                    rank=base_rank + seq,
                    timestamp=utcnow_dt(),
                    role=role,
                    channel=ch,
                    parts=parts or [TextPart(text="")],
                    metadata=ChatMetadata(
                        model=model_name,
                        token_usage=token_usage,
                        agent_name=agent_name,
                        finish_reason=finish_reason,
                        extras=raw_md.get("extras") or {},
                        sources=raw_md.get("sources") or [],
                    ),
                )
                out.append(msg_v2)
                seq += 1
                await self._emit(callback, msg_v2)

        return out

    # ---------------- misc (unchanged) ----------------

    async def _emit(self, callback: CallbackType, message: ChatMessage) -> None:
        result = callback(message.model_dump())
        if asyncio.iscoroutine(result):
            await result

    def delete_session(self, session_id: str, user_id: str) -> None:
        self.session_store.delete(session_id)

    def get_sessions(self, user_id: str) -> List[SessionWithFiles]:
        sessions = self.session_store.get_for_user(user_id)
        enriched: List[SessionWithFiles] = []
        for session in sessions:
            session_folder = self.get_session_temp_folder(session.id)
            file_names = (
                [f.name for f in session_folder.iterdir() if f.is_file()]
                if session_folder.exists()
                else []
            )
            enriched.append(
                SessionWithFiles(**session.model_dump(), file_names=file_names)
            )
        return enriched

    def get_session_history(
        self, session_id: str, user_id: str
    ) -> List[ChatMessage]:
        return self.history_store.get(session_id) or []

    def get_session_temp_folder(self, session_id: str) -> Path:
        base_temp_dir = Path(tempfile.gettempdir()) / "chatbot_uploads"
        session_folder = base_temp_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        return session_folder

    async def upload_file(
        self, user_id: str, session_id: str, agent_name: str, file: UploadFile
    ) -> dict:
        try:
            session_folder = self.get_session_temp_folder(session_id)
            if file.filename is None:
                raise ValueError("Uploaded file must have a filename.")
            file_path = session_folder / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            if str(file_path) not in self.temp_files[session_id]:
                self.temp_files[session_id].append(str(file_path))
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

    def get_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        return self.history_store.get_metrics(
            start=start,
            end=end,
            precision=precision,
            groupby=groupby,
            agg_mapping=agg_mapping,
            user_id=user_id,
        )
