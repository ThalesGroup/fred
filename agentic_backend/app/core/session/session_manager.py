# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

import asyncio
import logging
import secrets
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union, cast
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
    ChatMessageMetadata,
    ChatMessagePayload,
    MessageSubtype,
    MessageType,
    Sender,
    SessionSchema,
    SessionWithFiles,
    ToolCall,
)
from app.core.chatbot.metric_structures import MetricsResponse

# ⬇️ Structured-content helpers
from app.core.session.langchain_to_payload_utils import (
    coerce_finish_reason,
    coerce_blocks,
    coerce_content,
    coerce_sender,
    coerce_sources,
    coerce_token_usage,
    enrich_chat_message_payloads_with_latencies,
    extract_tool_call,
    infer_subtype,
)
from app.core.session.stores.base_session_store import BaseSessionStore
from app.core.session.attachement_processing import AttachementProcessing

logger = logging.getLogger(__name__)

# Type for callback functions (synchronous or asynchronous)
CallbackType = Union[Callable[[Dict], None], Callable[[Dict], Awaitable[None]]]


def utcnow_dt() -> datetime:
    """UTC timestamp (seconds resolution) for pydantic to serialize as ISO-8601."""
    return datetime.now(timezone.utc).replace(microsecond=0)


class SessionManager:
    """
    Manages user sessions and interactions with the chatbot.
    Clean, typed implementation (no legacy/back-compat branches).
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
    ) -> Tuple[SessionSchema, List[ChatMessagePayload]]:
        logger.info(
            "chat_ask_websocket user_id=%s session_id=%s agent=%s",
            user_id,
            session_id,
            agent_name,
        )

        session, history, agent, _is_new_session = self._prepare_session_and_history(
            user_id=user_id,
            session_id=session_id,
            message=message,
            agent_name=agent_name,
            runtime_context=runtime_context,
        )
        exchange_id = client_exchange_id or str(uuid4())
        base_rank = len(history)

        # 1) User message (always final)
        #    - We generate both 'content' (string) and 'blocks' (structured).
        user_blocks = coerce_blocks(message)          # -> [TextBlock(text=...)]
        user_content = coerce_content(message)        # -> string flattening of blocks

        user_payload = ChatMessagePayload(
            exchange_id=exchange_id,
            type=MessageType.human,
            sender=Sender.user,
            content=user_content,
            blocks=user_blocks or None,
            timestamp=utcnow_dt(),
            session_id=session.id,
            rank=base_rank,
            subtype=MessageSubtype.final,
            user_id=user_id,
            metadata=ChatMessageMetadata(),  # empty, but present for consistency
        )
        all_payloads: List[ChatMessagePayload] = [user_payload]

        # 2) Stream agent responses
        try:
            agent_payloads = await self._stream_agent_response(
                compiled_graph=agent.get_compiled_graph(),
                input_messages=history,
                session_id=session.id,
                callback=callback,
                exchange_id=exchange_id,
                base_rank=base_rank,
                user_id=user_id,
                agent_name=agent_name,
            )
            all_payloads.extend(agent_payloads)
        except Exception:
            logger.exception("Agent execution failed")

        # 3) Latency enrichment + persist
        all_payloads = enrich_chat_message_payloads_with_latencies(all_payloads)
        session.updated_at = utcnow_dt()
        self.session_store.save(session)
        self.history_store.save(session.id, all_payloads, user_id)
        return session, all_payloads

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

        history: List[BaseMessage] = []
        if not is_new_session:
            # Rebuild history for LangGraph (AI messages carry response_metadata for context)
            for msg in self.get_session_history(session.id, user_id):
                if msg.type == MessageType.human:
                    history.append(HumanMessage(content=msg.content))
                elif msg.type == MessageType.ai:
                    md = (
                        msg.metadata.model_dump()
                        if isinstance(msg.metadata, ChatMessageMetadata)
                        else (msg.metadata or {})
                    )
                    history.append(AIMessage(content=msg.content, response_metadata=md))
                elif msg.type == MessageType.system:
                    history.append(SystemMessage(content=msg.content))

        # Append the new user question to LangChain history (string is fine)
        history.append(HumanMessage(message))
        agent = self.agent_manager.get_agent_instance(agent_name, runtime_context)
        return session, history, agent, is_new_session

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
        compiled_graph: CompiledStateGraph,
        input_messages: List[BaseMessage],
        session_id: str,
        callback: CallbackType,
        exchange_id: str,
        base_rank: int,
        user_id: str,
        agent_name: str,
    ) -> List[ChatMessagePayload]:
        """
        Execute the agentic flow and stream responses via callback.
        Returns the collected ChatMessagePayloads (assistant/system/tool).
        """
        config: RunnableConfig = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": get_configuration().ai.recursion.recursion_limit,
        }
        out: List[ChatMessagePayload] = []
        seq = 0  # running index across all stream events

        async for event in compiled_graph.astream(
            {"messages": input_messages},
            config=config,
            stream_mode="updates",
        ):
            # Each 'event' is typically {'node_name': {'messages': [...]}} or {'end': None}
            key = next(iter(event))
            payload = event[key]

            if not isinstance(payload, dict):
                continue
            block = payload.get("messages", []) or []
            if not block:
                continue

            for msg in block:
                # Raw metadata from the LLM/tool
                raw_md = getattr(msg, "response_metadata", {}) or {}
                usage_raw = getattr(msg, "usage_metadata", {}) or {}

                # ---- Build typed metadata ----
                md = ChatMessageMetadata()
                md.agent_name = agent_name
                md.model = raw_md.get("model_name") or raw_md.get("model")
                md.finish_reason = coerce_finish_reason(raw_md.get("finish_reason"))
                md.token_usage = coerce_token_usage(usage_raw)

                # sources (typed)
                if isinstance(raw_md.get("sources"), list):
                    md.sources = coerce_sources(raw_md.get("sources"))

                # Thought/plans if your agent emits them
                if "thought" in raw_md:
                    md.thought = raw_md["thought"]

                # Tool call (OpenAI-style function call)
                tc = extract_tool_call(msg)
                if tc and tc.get("name"):
                    md.tool_call = ToolCall(name=str(tc["name"]), args=tc.get("args"))

                # ---- Content & blocks ----
                # LangChain may give str or list-of-blocks in msg.content.
                raw_content: Any = getattr(msg, "content", "")
                blocks = coerce_blocks(raw_content)          # -> List[MessageBlock]
                content_str = coerce_content(raw_content)    # -> String for indexing/previews

                # ---- Core typing & subtype ----
                mtype_str: str = getattr(msg, "type", "ai")  # "ai" | "system" | "tool"
                mtype_enum: MessageType = MessageType(mtype_str)
                subtype = infer_subtype(md.finish_reason, mtype_enum, md.thought)

                enriched = ChatMessagePayload(
                    exchange_id=exchange_id,
                    type=mtype_enum,
                    sender=coerce_sender(msg),     # "assistant" | "system"
                    content=content_str,
                    blocks=blocks or None,
                    timestamp=utcnow_dt(),
                    rank=base_rank + 1 + seq,       # strictly increasing
                    session_id=session_id,
                    metadata=md,
                    subtype=subtype,
                    user_id=user_id,
                )
                out.append(enriched)
                seq += 1

                # Emit to the stream immediately
                result = callback(enriched.model_dump())
                if asyncio.iscoroutine(result):
                    await result

        return out

    # ---------------- misc (unchanged) ----------------

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
    ) -> List[ChatMessagePayload]:
        return self.history_store.get(session_id)

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
