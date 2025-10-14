# chat/stream_transcoder.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, List, cast

from fred_core import KeycloakUser
from langchain_core.messages import AnyMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState

from app.core.agents.agent_flow import AgentFlow
from app.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    MessagePart,
    Role,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from app.core.chatbot.message_part import (
    clean_token_usage,
    coerce_finish_reason,
    extract_tool_calls,
    hydrate_fred_parts,
    parts_from_raw_content,
)

logger = logging.getLogger(__name__)

# WS callback type (sync or async)
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt():
    """UTC timestamp (seconds precision) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


class StreamTranscoder:
    """
    Purpose:
      Run a LangGraph compiled graph and convert its streamed events into
      Chat Protocol v2 `ChatMessage` objects, emitting each via the provided callback.

    Responsibilities:
      - Execute `CompiledStateGraph.astream(...)`
      - Transcode LangChain messages into v2 parts (text, tool_call/result, fred_parts)
      - Decide assistant `final` vs `observation`
      - Emit optional `thought` channel if provided by response metadata

    Non-Responsibilities:
      - Session lifecycle, KPI, persistence (owned by SessionOrchestrator)
    """

    async def stream_agent_response(
        self,
        *,
        agent: AgentFlow,
        input_messages: List[BaseMessage],
        session_id: str,
        exchange_id: str,
        agent_name: str,
        base_rank: int,
        start_seq: int,
        callback: CallbackType,
        user_context: KeycloakUser,
    ) -> List[ChatMessage]:
        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_context.uid,
            },
            "recursion_limit": 40,
        }

        out: List[ChatMessage] = []
        seq = start_seq
        final_sent = False
        msgs_any: list[AnyMessage] = [cast(AnyMessage, m) for m in input_messages]
        state: MessagesState = {"messages": msgs_any}
        async for event in agent.astream_updates(
            state=state,
            config=config,
        ):
            # `event` looks like: {'node_name': {'messages': [...]}} or {'end': None}
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
                additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}  # NEW

                model_name = raw_md.get("model_name") or raw_md.get("model")
                finish_reason = coerce_finish_reason(raw_md.get("finish_reason"))
                token_usage = clean_token_usage(usage_raw)

                sources_payload = (
                    raw_md.get("sources") or additional_kwargs.get("sources") or []
                )  # NEW

                # ---------- TOOL CALLS ----------
                tool_calls = extract_tool_calls(msg)
                if tool_calls:
                    for tc in tool_calls:
                        tc_msg = ChatMessage(
                            session_id=session_id,
                            exchange_id=exchange_id,
                            rank=base_rank + seq,
                            timestamp=_utcnow_dt(),
                            role=Role.assistant,
                            channel=Channel.tool_call,
                            parts=[
                                ToolCallPart(
                                    call_id=tc["call_id"],
                                    name=tc["name"],
                                    args=tc["args"],
                                )
                            ],
                            metadata=ChatMetadata(
                                model=model_name,
                                token_usage=token_usage,
                                agent_name=agent_name,
                                finish_reason=finish_reason,
                                extras=raw_md.get("extras", {}),
                                sources=sources_payload,  # Use synthesized sources if any],
                            ),
                        )
                        out.append(tc_msg)
                        seq += 1
                        await self._emit(callback, tc_msg)
                    # A message with tool_calls doesn't carry user-visible text
                    # in our protocol; continue to next msg.
                    continue

                # ---------- TOOL RESULT ----------
                if getattr(msg, "type", "") == "tool":
                    call_id = (
                        getattr(msg, "tool_call_id", None)
                        or raw_md.get("tool_call_id")
                        or "t?"
                    )
                    content_str = getattr(msg, "content", "")
                    if not isinstance(content_str, str):
                        content_str = json.dumps(content_str)
                    tr_msg = ChatMessage(
                        session_id=session_id,
                        exchange_id=exchange_id,
                        rank=base_rank + seq,
                        timestamp=_utcnow_dt(),
                        role=Role.tool,
                        channel=Channel.tool_result,
                        parts=[
                            ToolResultPart(
                                call_id=call_id,
                                ok=True,
                                latency_ms=raw_md.get("latency_ms"),
                                content=content_str,
                            )
                        ],
                        metadata=ChatMetadata(
                            agent_name=agent_name,
                            extras=raw_md.get("extras") or {},
                            sources=sources_payload,
                        ),
                    )
                    out.append(tr_msg)
                    seq += 1
                    await self._emit(callback, tr_msg)
                    continue

                # ---------- TEXTUAL / SYSTEM ----------
                lc_type = getattr(msg, "type", "ai")
                role = {
                    "ai": Role.assistant,
                    "system": Role.system,
                    "human": Role.user,
                    "tool": Role.tool,
                }.get(lc_type, Role.assistant)

                content = getattr(msg, "content", "")

                # CRITICAL FIX: Check msg.parts for structured content first.
                lc_parts = getattr(msg, "parts", []) or []
                parts: List[MessagePart] = []

                if lc_parts:
                    # 1. Use structured parts (e.g., LinkPart, TextPart list) from the agent's AIMessage.
                    parts.extend(lc_parts)
                elif content:
                    # 2. If no structured parts, fall back to parsing the raw content string.
                    parts.extend(parts_from_raw_content(content))

                # Append any structured UI payloads (LinkPart/GeoPart...)
                additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
                parts.extend(hydrate_fred_parts(additional_kwargs))

                # Optional thought trace (developer-facing, not part of final answer)
                if "thought" in raw_md:
                    thought_txt = raw_md["thought"]
                    if isinstance(thought_txt, (dict, list)):
                        thought_txt = json.dumps(thought_txt, ensure_ascii=False)
                    if str(thought_txt).strip():
                        tmsg = ChatMessage(
                            session_id=session_id,
                            exchange_id=exchange_id,
                            rank=base_rank + seq,
                            timestamp=_utcnow_dt(),
                            role=Role.assistant,
                            channel=Channel.thought,
                            parts=[TextPart(text=str(thought_txt))],
                            metadata=ChatMetadata(
                                agent_name=agent_name,
                                extras=raw_md.get("extras") or {},
                            ),
                        )
                        out.append(tmsg)
                        seq += 1
                        await self._emit(callback, tmsg)

                # Channel selection
                if role == Role.assistant:
                    ch = (
                        Channel.final
                        if (parts and not final_sent)
                        else Channel.observation
                    )
                    if ch == Channel.final:
                        final_sent = True
                elif role == Role.system:
                    ch = Channel.system_note
                elif role == Role.user:
                    ch = Channel.final
                else:
                    ch = Channel.observation

                # Skip empty intermediary assistant observations (keeps UI clean)
                if role == Role.assistant and ch == Channel.observation:
                    if not parts or all(
                        getattr(p, "type", "") == "text"
                        and not getattr(p, "text", "").strip()
                        for p in parts
                    ):
                        continue

                msg_v2 = ChatMessage(
                    session_id=session_id,
                    exchange_id=exchange_id,
                    rank=base_rank + seq,
                    timestamp=_utcnow_dt(),
                    role=role,
                    channel=ch,
                    parts=parts or [TextPart(text="")],
                    metadata=ChatMetadata(
                        model=model_name,
                        token_usage=token_usage,
                        agent_name=agent_name,
                        finish_reason=finish_reason,
                        extras=raw_md.get("extras") or {},
                        sources=sources_payload,
                    ),
                )
                out.append(msg_v2)
                seq += 1
                await self._emit(callback, msg_v2)

        return out

    async def _emit(self, callback: CallbackType, message: ChatMessage) -> None:
        """
        Support sync OR async callbacks uniformly.
        - If the callback returns an awaitable, await it.
        - If it returns None, just return.
        """
        result = callback(message.model_dump())
        if inspect.isawaitable(result):
            await result
