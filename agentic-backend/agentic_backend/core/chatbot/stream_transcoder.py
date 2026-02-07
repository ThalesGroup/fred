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

import inspect
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from fred_core import KeycloakUser, VectorSearchHit
from fred_core.kpi import BaseKPIWriter
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler
from langgraph.types import Command
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
    validate_hitl_payload,
)
from agentic_backend.core.chatbot.message_part import (
    clean_token_usage,
    coerce_finish_reason,
    extract_tool_calls,
    hydrate_fred_parts,
    parts_from_raw_content,
)
from agentic_backend.core.interrupts.base_interrupt_handler import InterruptHandler

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


def _additional_kwargs_emptyish(raw: Any) -> bool:
    """
    Treat provider extras as empty when they only contain falsy values
    (e.g., {'refusal': None}) or are not a dict.
    This allows the fast path to be taken for plain answers.
    """
    if not isinstance(raw, dict):
        return True
    return all(v in (None, "", [], {}, False) for v in raw.values())


class InterruptRaised(Exception):
    """Internal control-flow exception for LangGraph interrupts."""

    def __init__(
        self,
        payload: Dict[str, Any],
        partial_messages: Optional[List["ChatMessage"]] = None,
    ):
        self.payload = payload
        self.partial_messages = partial_messages or []
        super().__init__("LangGraph interrupt")


class StreamAgentError(Exception):
    """Wraps a streaming failure while preserving already emitted messages."""

    def __init__(self, partial_messages: List[ChatMessage], original: Exception):
        self.partial_messages = partial_messages
        self.original = original
        super().__init__(str(original))


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

    async def _handle_interrupt(
        self,
        *,
        event: Dict[str, Any],
        key: str,
        session_id: str,
        exchange_id: str,
        agent_name: str,
        interrupt_handler: Optional[InterruptHandler],
        checkpointer: Optional[Any],
    ) -> None:
        """
        Normalize LangGraph interrupt payload, enforce checkpoint presence,
        emit awaiting_human via the handler, then raise InterruptRaised to unwind the loop.
        """
        interrupt_payload = event[key]
        logger.info(
            "[TRANSCODER] raw interrupt payload type=%s payload=%s",
            type(interrupt_payload).__name__,
            interrupt_payload,
        )

        payload_obj: Any = None
        checkpoint_obj: Any = None
        checkpoint_id: Optional[str] = None

        # Accept only well-known shapes.
        if isinstance(interrupt_payload, list):
            if not interrupt_payload:
                raise InterruptRaised(
                    {
                        "reason": "interrupt",
                        "error": "invalid_interrupt_format",
                        "detail": "Empty interrupt list",
                    }
                )
            interrupt_payload = interrupt_payload[0]

        if isinstance(interrupt_payload, tuple):
            if len(interrupt_payload) == 2:
                payload_obj, checkpoint_obj = interrupt_payload
                checkpoint_id = getattr(interrupt_payload[1], "id", None) or getattr(
                    interrupt_payload[1], "checkpoint_id", None
                )
            elif len(interrupt_payload) == 1:
                first = interrupt_payload[0]
                payload_obj = getattr(first, "value", first)
                checkpoint_obj = getattr(first, "checkpoint", None)
                checkpoint_id = getattr(first, "id", None) or getattr(
                    first, "interrupt_id", None
                )
                logger.info(
                    "[TRANSCODER] interrupt tuple len=1 attrs=%s dict=%s",
                    dir(first),
                    getattr(first, "__dict__", {}),
                )
            else:
                raise InterruptRaised(
                    {
                        "reason": "interrupt",
                        "error": "invalid_interrupt_format",
                        "detail": f"Unexpected interrupt tuple len={len(interrupt_payload)}",
                    }
                )
        elif isinstance(interrupt_payload, dict):
            payload_obj = interrupt_payload.get("value", interrupt_payload)
            checkpoint_obj = interrupt_payload.get("checkpoint")
            checkpoint_id = (
                interrupt_payload.get("checkpoint_id")
                or interrupt_payload.get("id")
                or interrupt_payload.get("interrupt_id")
            )
            logger.info(
                "[TRANSCODER] interrupt dict keys value_keys=%s checkpoint_keys=%s",
                list(interrupt_payload.get("value", {}).keys())
                if isinstance(interrupt_payload.get("value"), dict)
                else type(interrupt_payload.get("value")).__name__,
                list(interrupt_payload.get("checkpoint", {}).keys())
                if isinstance(interrupt_payload.get("checkpoint"), dict)
                else type(interrupt_payload.get("checkpoint")).__name__,
            )
        else:
            raise InterruptRaised(
                {
                    "reason": "interrupt",
                    "error": "invalid_interrupt_format",
                    "detail": f"Unexpected interrupt payload type={type(interrupt_payload).__name__}",
                }
            )

        logger.info(
            "[TRANSCODER] interrupt normalized payload_type=%s checkpoint_type=%s checkpoint_present=%s checkpoint_id=%s",
            type(payload_obj).__name__,
            type(checkpoint_obj).__name__ if checkpoint_obj is not None else None,
            checkpoint_obj is not None,
            checkpoint_id,
        )

        if checkpoint_obj is None and checkpointer is not None:
            # Attempt to retrieve persisted checkpoint from the checkpointer (best-effort).
            try:
                retrieved = None
                if hasattr(checkpointer, "get"):
                    retrieved = checkpointer.get(
                        {"configurable": {"thread_id": session_id}}
                    )
                elif hasattr(checkpointer, "get_state"):
                    retrieved = checkpointer.get_state(
                        {"configurable": {"thread_id": session_id}}
                    )
                checkpoint_obj = (
                    retrieved.get("checkpoint")
                    if isinstance(retrieved, dict) and "checkpoint" in retrieved
                    else retrieved
                )
                if checkpoint_id is None and isinstance(checkpoint_obj, dict):
                    checkpoint_id = checkpoint_obj.get("id") or checkpoint_obj.get(
                        "checkpoint_id"
                    )
                logger.info(
                    "[TRANSCODER] checkpoint fetched from checkpointer type=%s id=%s keys=%s",
                    type(checkpointer).__name__,
                    checkpoint_id,
                    list(checkpoint_obj.keys())
                    if isinstance(checkpoint_obj, dict)
                    else None,
                )
            except Exception as fetch_err:
                logger.warning(
                    "[TRANSCODER] failed to fetch checkpoint from checkpointer for session=%s: %s",
                    session_id,
                    fetch_err,
                )

        if checkpoint_obj is None and checkpoint_id is None:
            logger.info(
                "[TRANSCODER] No checkpoint found in interrupt payload (agent=%s session=%s). "
                "Assuming server-side persistence via thread_id.",
                agent_name,
                session_id,
            )

        # Enrich payload with checkpoint_id so the client can echo it back on resume.
        if checkpoint_id and isinstance(payload_obj, dict):
            payload_obj = dict(payload_obj)
            payload_obj.setdefault("checkpoint_id", checkpoint_id)

        if interrupt_handler:
            try:
                validated = validate_hitl_payload(payload_obj or {})
            except Exception as ve:
                logger.error(
                    "[TRANSCODER] HITL payload invalid agent=%s session=%s exchange=%s err=%s payload=%s",
                    agent_name,
                    session_id,
                    exchange_id,
                    ve,
                    payload_obj,
                )
                raise ValueError(f"Invalid HITL payload: {ve}") from ve

            logger.info(
                "[TRANSCODER] interrupt_handler_present=True handler=%s",
                interrupt_handler,
            )
            logger.info(
                "[TRANSCODER] emitting awaiting_human via handler session=%s exchange=%s payload_keys=%s checkpoint_keys=%s",
                session_id,
                exchange_id,
                list((validated.model_dump() or {}).keys()),
                list((checkpoint_obj or {}).keys())
                if isinstance(checkpoint_obj, dict)
                else "<non-dict>",
            )
            await interrupt_handler.handle(
                session_id=session_id,
                exchange_id=exchange_id,
                payload=validated.model_dump(exclude_none=True),
                checkpoint=checkpoint_obj or {},
            )

        raise InterruptRaised({"reason": "interrupt", "message": "LangGraph interrupt"})

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
        interrupt_handler: Optional[InterruptHandler] = None,
        resume_payload: Optional[Dict[str, Any]] = None,
        kpi: Optional[BaseKPIWriter] = None,
    ) -> List[ChatMessage]:
        """
        Run a LangGraph compiled graph and transcode its streamed events into ChatMessage objects emitted via the callback.

        This method is key for performance. If it takes too much CPU time, the global agentic performance will be impacted. In the best case
        it should be mostly waiting on the agent's async generator and emitting messages, with minimal processing in between.
        """
        t_first_event: Optional[float] = None
        events_seen = 0
        emit_time_total = 0.0
        emit_count = 0

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[TRANSCODER] start agent=%s session=%s exchange=%s base_rank=%s start_seq=%s interrupt_handler=%s resume=%s",
                agent_name,
                session_id,
                exchange_id,
                base_rank,
                start_seq,
                interrupt_handler is not None,
                resume_payload is not None,
            )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_context.uid,
                "access_token": runtime_context.access_token,
                "refresh_token": runtime_context.refresh_token,
            },
            "recursion_limit": 100,
        }

        # When resuming, clean up the payload but DO NOT set checkpoint_id in config.
        # We rely on thread_id to find the latest interrupted state.
        if resume_payload and isinstance(resume_payload, dict):
            resume_payload.pop("checkpoint_id", None)
            resume_payload.pop("checkpoint", None)

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

        # Determine graph input: Command for resume, or State dict for start
        graph_input: Any
        if resume_payload is not None:
            graph_input = Command(resume=resume_payload)
            logger.debug(
                "[TRANSCODER] resume mode: passing Command(resume=...) as input"
            )
        else:
            graph_input = {"messages": msgs_any}

        try:
            async for event in agent.astream_updates(
                state=graph_input,
                config=config,
            ):
                events_seen += 1
                if t_first_event is None:
                    t_first_event = time.monotonic()
                # Handle LangGraph interrupt events explicitly
                key = next(iter(event))
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "[TRANSCODER] event key=%s session=%s exchange=%s agent=%s",
                        key,
                        session_id,
                        exchange_id,
                        agent_name,
                    )

                # LangGraph can emit "interrupt" or "__interrupt__" depending on source.
                if key in {"interrupt", "__interrupt__"}:
                    await self._handle_interrupt(
                        event=event,
                        key=key,
                        session_id=session_id,
                        exchange_id=exchange_id,
                        agent_name=agent_name,
                        interrupt_handler=interrupt_handler,
                        checkpointer=getattr(agent, "streaming_memory", None),
                    )

                # `event` looks like: {'node_name': {'messages': [...]} } or {'end': None}
                key = next(iter(event))
                payload = event[key]
                if not isinstance(payload, dict):
                    continue

                block = payload.get("messages", []) or []
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
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "[TRANSCODER][TOOL_CALLS] session=%s exchange=%s count=%d calls=%s",
                                session_id,
                                exchange_id,
                                len(tool_calls),
                                [
                                    {"id": tc.get("call_id"), "name": tc.get("name")}
                                    for tc in tool_calls
                                ],
                            )
                        for tc in tool_calls:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER][TOOL_CALLS][MSG] session=%s exchange=%s call_id=%s name=%s",
                                    session_id,
                                    exchange_id,
                                    tc.get("call_id"),
                                    tc.get("name"),
                                )
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
                            emit_start = time.monotonic()
                            await self._emit(callback, tc_msg)
                            emit_time_total += time.monotonic() - emit_start
                            emit_count += 1
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
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "[TRANSCODER][TOOL_RESULT_EVT] session=%s exchange=%s call_id=%s raw_type=%s",
                                session_id,
                                exchange_id,
                                call_id,
                                type(getattr(msg, "content", None)).__name__,
                            )
                        raw_content = getattr(msg, "content", None)
                        new_hits = _extract_vector_search_hits(raw_content)
                        if new_hits is not None:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER] tool_result call_id=%s vector_hits=%d",
                                    call_id,
                                    len(new_hits),
                                )
                            pending_sources_payload = new_hits
                        else:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER] tool_result call_id=%s vector_hits=0 (no parse)",
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
                        emit_start = time.monotonic()
                        await self._emit(callback, tr_msg)
                        emit_time_total += time.monotonic() - emit_start
                        emit_count += 1
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

                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "[TRANSCODER][TEXT] session=%s exchange=%s role=%s channel_candidate=%s content_preview=%s",
                            session_id,
                            exchange_id,
                            role,
                            lc_type,
                            (
                                str(content)[:80].replace("\n", " ")
                                if isinstance(content, str)
                                else type(content).__name__
                            ),
                        )

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
                    if additional_kwargs:
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
                            emit_start = time.monotonic()
                            await self._emit(callback, tmsg)
                            emit_time_total += time.monotonic() - emit_start
                            emit_count += 1

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
                        existing_sources = (
                            len(sources_payload) if sources_payload else 0
                        )
                        pending_sources = (
                            len(pending_sources_payload)
                            if pending_sources_payload is not None
                            else 0
                        )
                        if (
                            existing_sources == 0
                            and pending_sources_payload is not None
                        ):
                            # Some agents put sources in the vector-search tool result, not on the final AIMessage.
                            # In that case, carry the tool-result sources forward into the final message metadata.
                            sources_payload = pending_sources_payload
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER][SOURCES] final: adopted %d pending sources from tool_result",
                                    pending_sources,
                                )
                        elif existing_sources > 0:
                            # Sources already present on the final AIMessage (citations can still appear in text either way).
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER][SOURCES] final: kept %d existing sources (pending_sources=%s)",
                                    existing_sources,
                                    pending_sources
                                    if pending_sources_payload is not None
                                    else "none",
                                )
                        else:
                            # No sources anywhere: neither provided by agent metadata nor parsed from tool results.
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "[TRANSCODER][SOURCES] final: no sources present (pending_sources=%s)",
                                    pending_sources
                                    if pending_sources_payload is not None
                                    else "none",
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
                        emit_start = time.monotonic()
                        await self._emit(callback, msg_v2)
                        emit_time_total += time.monotonic() - emit_start
                        emit_count += 1
        except InterruptRaised as ir:
            # Expected control-flow for HITL; let caller handle without logging an error.
            logger.info(
                "StreamTranscoder: interrupt raised agent=%s session=%s exchange=%s",
                agent_name,
                session_id,
                exchange_id,
            )
            # Attach partial messages so the orchestrator can persist them.
            ir.partial_messages = out
            raise
        except Exception as e:
            # Preserve partial transcript so far; caller decides how to surface the failure.
            logger.exception(
                "[TRANSCODER] stream failure agent=%s session=%s exchange=%s msgs=%d",
                agent_name,
                session_id,
                exchange_id,
                len(out),
            )
            raise StreamAgentError(out, e) from e
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
