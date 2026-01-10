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
import inspect
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional, cast

from fred_core import KeycloakUser, VectorSearchHit
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler
from langgraph.graph import MessagesState
from pydantic import TypeAdapter, ValidationError

from agentic_backend.common.rags_utils import ensure_ranks
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    MessagePart,
    Role,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from agentic_backend.core.chatbot.message_part import (
    clean_token_usage,
    coerce_finish_reason,
    extract_tool_calls,
    hydrate_fred_parts,
    parts_from_raw_content,
)

logger = logging.getLogger(__name__)

_VECTOR_SEARCH_HITS = TypeAdapter(List[VectorSearchHit])

# WS callback type (sync or async)
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt():
    """UTC timestamp (seconds precision) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _infer_tool_ok_flag(raw_md: dict, content: str) -> Optional[bool]:
    """
    Best-effort determination of tool_result.ok.
    - Honour explicit metadata provided by the tool (ok / success / status).
    - Detect common error markers when metadata is missing so the UI does not
      show a green “ok” badge for a textual error payload.
    """
    if isinstance(raw_md, dict):
        explicit_ok = raw_md.get("ok")
        if isinstance(explicit_ok, bool):
            return explicit_ok

        success = raw_md.get("success")
        if isinstance(success, bool):
            return success

        status = raw_md.get("status")
        if isinstance(status, str):
            status_lc = status.lower()
            if status_lc in ("ok", "success", "succeeded", "completed"):
                return True
            if status_lc in ("error", "failed", "fail", "exception"):
                return False

        if raw_md.get("error") or raw_md.get("is_error") is True:
            return False
        if raw_md.get("failed") is True:
            return False

    if isinstance(content, str):
        stripped = content.strip()
        lowered = stripped.lower()
        if lowered.startswith("error") or lowered.startswith("exception"):
            return False
        if "toolexception" in lowered or "traceback" in lowered:
            return False

    return None


def _extract_vector_search_hits(raw: Any) -> Optional[List[VectorSearchHit]]:
    if raw is None:
        return None

    payload: Any = raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None

    if isinstance(payload, dict):
        for key in ("result", "data", "hits"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break

    if not isinstance(payload, list):
        return None

    try:
        hits = _VECTOR_SEARCH_HITS.validate_python(payload)
    except ValidationError:
        return None

    ensure_ranks(hits)
    return hits


def _normalize_sources_payload(raw: Any) -> List[VectorSearchHit]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    try:
        hits = _VECTOR_SEARCH_HITS.validate_python(raw)
    except ValidationError:
        return []
    ensure_ranks(hits)
    return hits


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
        input_messages: List[AnyMessage],
        session_id: str,
        exchange_id: str,
        agent_name: str,
        base_rank: int,
        start_seq: int,
        callback: CallbackType,
        user_context: KeycloakUser,
        runtime_context: RuntimeContext,
    ) -> List[ChatMessage]:
        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_context.uid,
                "access_token": runtime_context.access_token,
                "refresh_token": runtime_context.refresh_token,
            },
            "recursion_limit": 100,
        }

        # If Langfuse is configured, add the callback handler
        if os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"):
            logger.info("Langfuse credentials found.")
            langfuse_handler = CallbackHandler()
            config["callbacks"] = [langfuse_handler]

        out: List[ChatMessage] = []
        seq = start_seq
        final_sent = False
        pending_sources_payload: Optional[List[VectorSearchHit]] = None
        msgs_any: list[AnyMessage] = [cast(AnyMessage, m) for m in input_messages]
        state: MessagesState = {"messages": msgs_any}
        try:
            async for event in agent.astream_updates(state=state, config=config):
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
                    additional_kwargs = (
                        getattr(msg, "additional_kwargs", {}) or {}
                    )  # NEW

                    model_name = raw_md.get("model_name") or raw_md.get("model")
                    finish_reason = coerce_finish_reason(raw_md.get("finish_reason"))
                    token_usage = clean_token_usage(usage_raw)

                    sources_payload = _normalize_sources_payload(
                        raw_md.get("sources") or additional_kwargs.get("sources")
                    )

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
                        raw_content = getattr(msg, "content", None)
                        new_hits = _extract_vector_search_hits(raw_content)
                        if new_hits is not None:
                            logger.info(
                                "[Transcoder] tool_result call_id=%s vector_hits=%d",
                                call_id,
                                len(new_hits),
                            )
                            pending_sources_payload = new_hits
                        else:
                            logger.info(
                                "[Transcoder] tool_result call_id=%s vector_hits=0 (no parse)",
                                call_id,
                            )

                        content_str = raw_content or ""
                        if not isinstance(content_str, str):
                            content_str = json.dumps(content_str)
                        ok_flag = _infer_tool_ok_flag(raw_md, content_str)
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
                                    ok=ok_flag,
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

                    if role == Role.assistant and ch == Channel.final:
                        if not sources_payload and pending_sources_payload is not None:
                            sources_payload = pending_sources_payload
                            logger.info(
                                "[Transcoder] attach_sources to final assistant message sources=%d",
                                len(sources_payload),
                            )
                        else:
                            logger.info(
                                "[Transcoder] final assistant message no sources attached pending=%s existing=%d",
                                pending_sources_payload is not None,
                                len(sources_payload) if sources_payload else 0,
                            )
                        pending_sources_payload = None

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
        except asyncio.CancelledError:
            logger.info("StreamTranscoder: stream cancelled")
            raise
        except Exception as e:
            logger.error(
                "StreamTranscoder: Agent execution failed with error: %s",
                e,
                exc_info=True,
            )

            # Heuristic for friendly error messages
            err_text = str(e)
            user_msg = "I encountered an unexpected error. Please try again later."
            error_code = "error"

            if "timeout" in err_text.lower() or "timed out" in err_text.lower():
                user_msg = "The operation timed out because it took too long. Please try reducing the scope of your request or the number of documents."
                error_code = "timeout"
            elif "context length" in err_text.lower():
                user_msg = "The request exceeded the model's context limit. Please try with shorter documents or fewer attachments."
                error_code = "context_length"
            elif "rate limit" in err_text.lower():
                user_msg = "I'm receiving too many requests right now. Please wait a moment and try again."
                error_code = "rate_limit"

            # Emit error message
            err_chat_msg = ChatMessage(
                session_id=session_id,
                exchange_id=exchange_id,
                rank=base_rank + seq,
                timestamp=_utcnow_dt(),
                role=Role.assistant,
                channel=Channel.final,
                parts=[TextPart(text=f"**Error**: {user_msg}")],
                metadata=ChatMetadata(
                    agent_name=agent_name,
                    finish_reason=None,
                    extras={
                        "error": True,
                        "error_code": error_code,
                        "raw_error": err_text,
                    },
                ),
            )
            out.append(err_chat_msg)
            await self._emit(callback, err_chat_msg)

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
