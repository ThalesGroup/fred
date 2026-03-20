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

from fred_core import KeycloakUser
from fred_core.kpi import BaseKPIWriter
from fred_core.store import VectorSearchHit
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler
from langgraph.types import Command
from pydantic import TypeAdapter, ValidationError

from agentic_backend.common.rags_utils import ensure_ranks
from agentic_backend.core.agents.agent_factory import RuntimeAgentInstance
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.checkpoints import (
    AsyncCheckpointReader,
    load_checkpoint,
)
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    MessagePart,
    Role,
    TextPart,
    TokenUsageSource,
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
from agentic_backend.core.chatbot.tool_result_contract import (
    coerce_latency_ms as _coerce_latency_ms,
)
from agentic_backend.core.chatbot.tool_result_contract import (
    normalize_tool_result_contract,
)
from agentic_backend.core.interrupts.base_interrupt_handler import InterruptHandler

logger = logging.getLogger(__name__)

_VECTOR_SEARCH_HITS = TypeAdapter(List[VectorSearchHit])

# WS callback type (sync or async)
CallbackType = Callable[[dict], None] | Callable[[dict], Awaitable[None]]


def _utcnow_dt():
    """UTC timestamp (seconds precision) for ISO-8601 serialization."""
    return datetime.now(timezone.utc).replace(microsecond=0)


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


def _extract_fred_parts_from_tool_content(raw: Any) -> List[MessagePart]:
    """
    Best-effort extraction of structured frontend parts returned by tools.
    Accepts:
      - {"type": "link" | "geo", ...}
      - {"fred_parts": [{...}, ...]}
      - [{...}, ...]
      - JSON string of one of the above
    """
    if raw is None:
        return []

    payload: Any = raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return []

    candidates: List[dict] = []
    if isinstance(payload, dict):
        part_type = payload.get("type")
        if part_type in {"link", "geo"}:
            candidates = [payload]
        else:
            raw_parts = payload.get("fred_parts")
            if isinstance(raw_parts, list):
                candidates = [p for p in raw_parts if isinstance(p, dict)]
            elif isinstance(raw_parts, dict):
                candidates = [raw_parts]
    elif isinstance(payload, list):
        candidates = [p for p in payload if isinstance(p, dict)]

    if not candidates:
        return []
    return hydrate_fred_parts({"fred_parts": candidates})


def _extract_fred_parts_from_tool_payload(
    raw_content: Any,
    *,
    raw_metadata: Any,
    additional_kwargs: Any,
) -> List[MessagePart]:
    parts = _extract_fred_parts_from_tool_content(raw_content)
    if parts:
        return parts
    if isinstance(raw_metadata, dict):
        parts = hydrate_fred_parts(raw_metadata)
        if parts:
            return parts
    if isinstance(additional_kwargs, dict):
        return hydrate_fred_parts(additional_kwargs)
    return []


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


def _split_stream_event_mode(raw_event: Any) -> tuple[str, Any]:
    """
    LangGraph shape:
      - single mode: event payload directly
      - multi mode: (mode_name, payload)
    """
    if (
        isinstance(raw_event, tuple)
        and len(raw_event) == 2
        and isinstance(raw_event[0], str)
    ):
        return raw_event[0], raw_event[1]
    return "updates", raw_event


def _extract_chunk_text(raw_chunk: Any) -> str:
    content = getattr(raw_chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                txt = item.get("text") or item.get("input_text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "".join(parts)
    return ""


def _is_assistant_stream_chunk(raw_chunk: Any) -> bool:
    """
    Accept assistant chunks across LangChain variants.

    Observed values:
      - AIMessage            -> type == "ai"
      - AIMessageChunk       -> type == "AIMessageChunk"
    """
    raw_type = getattr(raw_chunk, "type", None)
    if isinstance(raw_type, str) and raw_type.lower() in {"ai", "aimessagechunk"}:
        return True
    return type(raw_chunk).__name__ == "AIMessageChunk"


def _extract_chunk_metadata(raw_messages_event: Any) -> dict[str, Any]:
    """
    `messages` mode usually yields (message_chunk, metadata).
    Keep this tolerant across runtime versions.
    """
    if (
        isinstance(raw_messages_event, tuple)
        and len(raw_messages_event) >= 2
        and isinstance(raw_messages_event[1], dict)
    ):
        return raw_messages_event[1]
    return {}


def _token_usage_log_payload(token_usage: Any) -> dict[str, Any] | None:
    if token_usage is None:
        return None
    if isinstance(token_usage, dict):
        return {
            "input_tokens": token_usage.get("input_tokens"),
            "output_tokens": token_usage.get("output_tokens"),
            "total_tokens": token_usage.get("total_tokens"),
        }
    model_dump = getattr(token_usage, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return {
                "input_tokens": dumped.get("input_tokens"),
                "output_tokens": dumped.get("output_tokens"),
                "total_tokens": dumped.get("total_tokens"),
            }
    return {"raw": str(token_usage)}


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
        agent_id: str,
        interrupt_handler: Optional[InterruptHandler],
        checkpointer: AsyncCheckpointReader | None,
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
                checkpoint_obj = await load_checkpoint(
                    checkpointer,
                    thread_id=session_id,
                    checkpoint_id=checkpoint_id,
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
                agent_id,
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
                    agent_id,
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
        agent: RuntimeAgentInstance,
        input_messages: List[AnyMessage],
        session_id: str,
        exchange_id: str,
        agent_id: str,
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
                agent_id,
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

        # When resuming, preserve an explicit checkpoint_id in config when present.
        # This keeps v2 runtimes transport-agnostic: WebSocket and Temporal can
        # both resume a durable checkpoint explicitly instead of relying only on
        # process-local state or "latest by thread_id" semantics.
        if resume_payload and isinstance(resume_payload, dict):
            checkpoint_id = resume_payload.get("checkpoint_id")
            if checkpoint_id is not None:
                config["configurable"]["checkpoint_id"] = str(checkpoint_id)
            resume_payload.pop("checkpoint_id", None)
            resume_payload.pop("checkpoint", None)

        # If Langfuse is configured, add the callback handler
        if os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"):
            logger.info("Langfuse credentials found.")
            langfuse_handler = CallbackHandler()
            config["callbacks"] = [langfuse_handler]

        out: List[ChatMessage] = []
        seq = start_seq
        tool_activity_seen = False
        pending_assistant_final: Optional[ChatMessage] = None
        partial_stream_rank: Optional[int] = None
        partial_stream_text = ""
        pending_stream_token_usage = None
        token_usage_seen_from_messages = False
        token_usage_seen_from_updates = False
        pending_final_token_source: Optional[TokenUsageSource] = None
        post_tool_stream_node: Optional[str] = None
        pending_sources_payload: Optional[List[VectorSearchHit]] = None
        pending_fred_parts: List[MessagePart] = []
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
            async for raw_event in agent.astream_updates(
                state=graph_input,
                config=config,
                stream_mode=["updates", "messages"],
            ):
                mode, event = _split_stream_event_mode(raw_event)
                events_seen += 1
                if t_first_event is None:
                    t_first_event = time.monotonic()

                if mode == "messages":
                    # Token/chunk stream (best-effort): enabled until we detect tool activity.
                    chunk_obj = (
                        event[0] if isinstance(event, tuple) and event else event
                    )
                    chunk_meta = _extract_chunk_metadata(event)
                    # Stream only assistant/model chunks.
                    # Tool chunks must not be surfaced as assistant final partials.
                    if not _is_assistant_stream_chunk(chunk_obj):
                        continue
                    if tool_activity_seen:
                        # After tool activity, lock streaming to a single LangGraph node
                        # selected dynamically at runtime (first visible assistant chunk).
                        # This avoids hardcoded node names and prevents mixed-node chunking.
                        langgraph_node = chunk_meta.get("langgraph_node")
                        if isinstance(langgraph_node, str) and langgraph_node:
                            # Skip chunks from the tool-execution node. Those come from
                            # inner LLM calls made *inside* tool functions (e.g. batch
                            # generation helpers) and must never surface as assistant text.
                            if langgraph_node == "tools":
                                continue
                            if post_tool_stream_node is None:
                                post_tool_stream_node = langgraph_node
                                if logger.isEnabledFor(logging.DEBUG):
                                    logger.debug(
                                        "[TRANSCODER][STREAM_NODE] selected session=%s exchange=%s agent=%s node=%s",
                                        session_id,
                                        exchange_id,
                                        agent_id,
                                        post_tool_stream_node,
                                    )
                            elif langgraph_node != post_tool_stream_node:
                                continue
                        elif post_tool_stream_node is not None:
                            continue
                    if extract_tool_calls(chunk_obj):
                        continue
                    chunk_md = getattr(chunk_obj, "response_metadata", {}) or {}
                    chunk_additional_kwargs = (
                        getattr(chunk_obj, "additional_kwargs", {}) or {}
                    )
                    chunk_usage = (
                        clean_token_usage(
                            getattr(chunk_obj, "usage_metadata", {}) or {}
                        )
                        or clean_token_usage(chunk_md.get("usage_metadata"))
                        or clean_token_usage(chunk_md.get("token_usage"))
                        or clean_token_usage(chunk_md.get("usage"))
                        or clean_token_usage(chunk_additional_kwargs.get("token_usage"))
                        or clean_token_usage(chunk_additional_kwargs.get("usage"))
                    )
                    if chunk_usage is not None:
                        pending_stream_token_usage = chunk_usage
                        if not token_usage_seen_from_messages:
                            logger.info(
                                "[TRANSCODER][TOKEN_USAGE][CAPTURE] session=%s exchange=%s agent=%s source=messages usage=%s",
                                session_id,
                                exchange_id,
                                agent_id,
                                _token_usage_log_payload(chunk_usage),
                            )
                            token_usage_seen_from_messages = True
                    if "thought" in chunk_md:
                        continue
                    if getattr(chunk_obj, "tool_call_id", None):
                        continue
                    chunk_text = _extract_chunk_text(chunk_obj)
                    if not chunk_text:
                        continue
                    partial_stream_text += chunk_text
                    if not partial_stream_text.strip():
                        continue
                    if partial_stream_rank is None:
                        partial_stream_rank = base_rank + seq
                    partial_msg = ChatMessage(
                        session_id=session_id,
                        exchange_id=exchange_id,
                        rank=partial_stream_rank,
                        timestamp=_utcnow_dt(),
                        role=Role.assistant,
                        channel=Channel.final,
                        parts=[TextPart(text=partial_stream_text)],
                        metadata=ChatMetadata(
                            agent_id=agent_id,
                            extras={"streaming_partial": True},
                        ),
                    )
                    emit_start = time.monotonic()
                    await self._emit(callback, partial_msg)
                    emit_time_total += time.monotonic() - emit_start
                    emit_count += 1
                    continue

                if mode != "updates":
                    continue

                # Handle LangGraph interrupt events explicitly
                key = next(iter(event))
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "[TRANSCODER] event key=%s session=%s exchange=%s agent=%s",
                        key,
                        session_id,
                        exchange_id,
                        agent_id,
                    )

                # LangGraph can emit "interrupt" or "__interrupt__" depending on source.
                if key in {"interrupt", "__interrupt__"}:
                    await self._handle_interrupt(
                        event=event,
                        key=key,
                        session_id=session_id,
                        exchange_id=exchange_id,
                        agent_id=agent_id,
                        interrupt_handler=interrupt_handler,
                        checkpointer=cast(
                            AsyncCheckpointReader | None, agent.streaming_memory
                        ),
                    )

                # `event` looks like: {'node_name': {'messages': [...]} } or {'end': None}
                key = next(iter(event))
                node_name = key
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
                    # Token usage can come from different wrappers/providers.
                    token_usage = (
                        clean_token_usage(usage_raw)
                        or clean_token_usage(raw_md.get("usage_metadata"))
                        or clean_token_usage(raw_md.get("token_usage"))
                        or clean_token_usage(raw_md.get("usage"))
                        or clean_token_usage(additional_kwargs.get("token_usage"))
                        or clean_token_usage(additional_kwargs.get("usage"))
                    )
                    if token_usage is not None and not token_usage_seen_from_updates:
                        logger.info(
                            "[TRANSCODER][TOKEN_USAGE][CAPTURE] session=%s exchange=%s agent=%s source=updates node=%s msg_type=%s usage=%s",
                            session_id,
                            exchange_id,
                            agent_id,
                            node_name,
                            getattr(msg, "type", None),
                            _token_usage_log_payload(token_usage),
                        )
                        token_usage_seen_from_updates = True
                    latency_ms = _coerce_latency_ms(raw_md.get("latency_ms"))

                    sources_payload = _normalize_sources_payload(
                        raw_md.get("sources") or additional_kwargs.get("sources")
                    )

                    # ---------- TOOL CALLS ----------
                    tool_calls = extract_tool_calls(msg)
                    if tool_calls:
                        tool_activity_seen = True
                        post_tool_stream_node = None
                        pending_assistant_final = None
                        partial_stream_rank = None
                        partial_stream_text = ""
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
                                    agent_id=agent_id,
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
                        tool_activity_seen = True
                        post_tool_stream_node = None
                        pending_assistant_final = None
                        partial_stream_rank = None
                        partial_stream_text = ""
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
                        if new_hits is None and sources_payload:
                            # Some runtimes attach normalized sources directly
                            # on the tool message metadata instead of leaving
                            # them only in the rendered tool content.
                            new_hits = sources_payload
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

                        tool_fred_parts = _extract_fred_parts_from_tool_payload(
                            raw_content,
                            raw_metadata=raw_md,
                            additional_kwargs=additional_kwargs,
                        )
                        if tool_fred_parts:
                            pending_fred_parts.extend(tool_fred_parts)

                        content_str = raw_content or ""
                        if not isinstance(content_str, str):
                            content_str = json.dumps(content_str)
                        ok_flag, tool_latency_ms, tool_extras = (
                            normalize_tool_result_contract(
                                raw_metadata=raw_md,
                                content=content_str,
                                source_count=len(sources_payload),
                            )
                        )
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
                                    latency_ms=tool_latency_ms,
                                    content=content_str,
                                ),
                                *tool_fred_parts,
                            ],
                            metadata=ChatMetadata(
                                agent_id=agent_id,
                                latency_ms=tool_latency_ms,
                                extras=tool_extras,
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

                    # Carry structured parts emitted by tool outputs to the next assistant message.
                    if role == Role.assistant and pending_fred_parts:
                        if not any(getattr(p, "type", None) == "link" for p in parts):
                            parts.extend(pending_fred_parts)
                        pending_fred_parts = []

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
                                    agent_id=agent_id,
                                    extras=raw_md.get("extras") or {},
                                ),
                            )
                            out.append(tmsg)
                            seq += 1
                            emit_start = time.monotonic()
                            await self._emit(callback, tmsg)
                            emit_time_total += time.monotonic() - emit_start
                            emit_count += 1

                    # Assistant textual output handling:
                    # keep only one pending final candidate and emit once at end-of-run,
                    # so late metadata (token usage, finish reason, etc.) can be preserved.
                    if role == Role.assistant:
                        if not parts or all(
                            getattr(p, "type", "") == "text"
                            and not getattr(p, "text", "").strip()
                            for p in parts
                        ):
                            continue
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

                        candidate_token_usage = (
                            token_usage or pending_stream_token_usage
                        )
                        candidate_token_source = (
                            TokenUsageSource.updates
                            if token_usage is not None
                            else TokenUsageSource.messages
                            if pending_stream_token_usage is not None
                            else TokenUsageSource.unavailable
                        )
                        candidate_final = ChatMessage(
                            session_id=session_id,
                            exchange_id=exchange_id,
                            rank=base_rank + seq,
                            timestamp=_utcnow_dt(),
                            role=role,
                            channel=Channel.final,
                            parts=parts or [TextPart(text="")],
                            metadata=ChatMetadata(
                                model=model_name,
                                token_usage=candidate_token_usage,
                                token_usage_source=candidate_token_source,
                                agent_id=agent_id,
                                latency_ms=latency_ms,
                                finish_reason=finish_reason,
                                extras=raw_md.get("extras") or {},
                                sources=sources_payload,
                            ),
                        )
                        pending_assistant_final = candidate_final
                        if pending_final_token_source != candidate_token_source:
                            logger.info(
                                "[TRANSCODER][TOKEN_USAGE][PENDING_FINAL] session=%s exchange=%s agent=%s source=%s usage=%s",
                                session_id,
                                exchange_id,
                                agent_id,
                                candidate_token_source.value,
                                _token_usage_log_payload(candidate_token_usage),
                            )
                            pending_final_token_source = candidate_token_source
                        continue
        except InterruptRaised as ir:
            # Expected control-flow for HITL; let caller handle without logging an error.
            logger.info(
                "StreamTranscoder: interrupt raised agent=%s session=%s exchange=%s",
                agent_id,
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
                agent_id,
                session_id,
                exchange_id,
                len(out),
            )
            raise StreamAgentError(out, e) from e

        if pending_assistant_final is not None:
            final_token_source = (
                pending_final_token_source or TokenUsageSource.unavailable
            )
            if (
                pending_assistant_final.metadata.token_usage is None
                and pending_stream_token_usage is not None
            ):
                pending_assistant_final = pending_assistant_final.model_copy(
                    update={
                        "metadata": pending_assistant_final.metadata.model_copy(
                            update={
                                "token_usage": pending_stream_token_usage,
                                "token_usage_source": TokenUsageSource.messages_backfill,
                            }
                        )
                    }
                )
                final_token_source = TokenUsageSource.messages_backfill
            elif pending_assistant_final.metadata.token_usage is None:
                pending_assistant_final = pending_assistant_final.model_copy(
                    update={
                        "metadata": pending_assistant_final.metadata.model_copy(
                            update={"token_usage_source": TokenUsageSource.unavailable}
                        )
                    }
                )
                final_token_source = TokenUsageSource.unavailable
            logger.info(
                "[TRANSCODER][TOKEN_USAGE][FINAL] session=%s exchange=%s agent=%s source=%s from_messages=%s from_updates=%s usage=%s",
                session_id,
                exchange_id,
                agent_id,
                final_token_source.value,
                token_usage_seen_from_messages,
                token_usage_seen_from_updates,
                _token_usage_log_payload(pending_assistant_final.metadata.token_usage),
            )
            # Final answer is emitted once, at end-of-run.
            # Reuse the partial-stream rank when present so the UI replaces the
            # streaming partial instead of showing two assistant final rows.
            final_rank = (
                partial_stream_rank
                if partial_stream_rank is not None
                else base_rank + seq
            )
            final_to_emit = pending_assistant_final.model_copy(
                update={
                    "rank": final_rank,
                    "timestamp": _utcnow_dt(),
                }
            )
            out.append(final_to_emit)
            seq += 1
            emit_start = time.monotonic()
            await self._emit(callback, final_to_emit)
            emit_time_total += time.monotonic() - emit_start
            emit_count += 1
        else:
            logger.info(
                "[TRANSCODER][TOKEN_USAGE][FINAL] session=%s exchange=%s agent=%s source=%s reason=no_final_message from_messages=%s from_updates=%s usage=%s",
                session_id,
                exchange_id,
                agent_id,
                TokenUsageSource.unavailable.value,
                token_usage_seen_from_messages,
                token_usage_seen_from_updates,
                None,
            )

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
