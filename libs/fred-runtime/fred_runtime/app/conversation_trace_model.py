# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Private LangChain snapshots captured on the admitted model invocation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from hashlib import sha256
from itertools import islice
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID, uuid4

from fred_core.conversation_trace import (
    TraceHttpCompleteness,
    TraceModelEvidence,
    TraceModelIndex,
    TraceModelOutputState,
    TraceModelSnapshot,
    TraceNormalization,
)
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from langchain_core.outputs.chat_generation import merge_chat_generation_chunks
from pydantic import BaseModel

from fred_runtime.runtime_support.trace_payloads import serialize_tools

if TYPE_CHECKING:
    from fred_runtime.app.conversation_trace_artifacts import ModelHttpCapture

MODEL_SNAPSHOT_BYTES = 128 * 1024
MODEL_TURN_BYTES = 512 * 1024
_MODEL_MESSAGE_LIMIT = 256
_TOOL_ID_LIMIT = 32
_MAX_DEPTH = 16
_MAX_FIELD_CHARS = 32 * 1024
_PARTIAL_CHUNK_LIMIT = 128
_PARTIAL_CHUNK_BYTES = 64 * 1024
_ROLES = {"human": "user", "ai": "assistant", "AIMessageChunk": "assistant"}
_SnapshotResult = TypeVar("_SnapshotResult")
_SNAPSHOT_WORKERS = 2


class SnapshotWork:
    """Drop diagnostic copies under pressure without queueing mutable live values."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=_SNAPSHOT_WORKERS, thread_name_prefix="fred-trace-snapshot"
        )
        self._active: set[asyncio.Future[Any]] = set()
        self._closed = False

    async def run(
        self, copy: Callable[..., _SnapshotResult], *args: object
    ) -> _SnapshotResult | None:
        if self._closed or len(self._active) >= _SNAPSHOT_WORKERS:
            return None
        future = asyncio.get_running_loop().run_in_executor(self._pool, copy, *args)
        self._active.add(future)

        def settled(done: asyncio.Future[Any]) -> None:
            self._active.discard(done)
            if not done.cancelled():
                done.exception()

        future.add_done_callback(settled)
        return await asyncio.shield(future)

    def close(self) -> None:
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)


@dataclass(slots=True)
class _JsonBudget:
    remaining: int
    partial: bool = False

    def take(self, amount: int) -> bool:
        if self.remaining < amount:
            self.partial = True
            return False
        self.remaining -= amount
        return True

    def copy(self, value: object, depth: int = 0) -> object:
        if depth >= _MAX_DEPTH:
            self.partial = True
            return None
        if isinstance(value, str):
            length = min(len(value), _MAX_FIELD_CHARS, max(0, self.remaining - 2))
            prefix = value[:length]
            encoded = len(json.dumps(prefix, ensure_ascii=False).encode("utf-8"))
            if encoded > self.remaining:
                length = max(0, (self.remaining - 2) // 6)
                prefix = value[:length]
                encoded = len(json.dumps(prefix, ensure_ascii=False).encode("utf-8"))
            self.partial |= len(prefix) < len(value)
            return prefix if self.take(encoded) else None
        if isinstance(value, BaseModel):
            value = vars(value)
        if isinstance(value, dict):
            if not self.take(4):
                return None
            result: dict[str, object] = {}
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 128:
                    self.partial = True
                    if not self.take(1):
                        break
                    continue
                if not self.take(
                    len(json.dumps(key, ensure_ascii=False).encode("utf-8")) + 8
                ):
                    break
                result[key] = self.copy(child, depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            if not self.take(4):
                return None
            items: list[object] = []
            for child in value:
                if not self.take(5):
                    break
                items.append(self.copy(child, depth + 1))
            return items
        if value is None or isinstance(value, bool):
            return value if self.take(5) else None
        if isinstance(value, int) and value.bit_length() <= 256:
            return value if self.take(2 + len(str(value))) else None
        if isinstance(value, float) and isfinite(value):
            return value if self.take(28) else None
        self.partial = True
        return None


def retain_json(value: object, capacity: int) -> tuple[object, int, bool]:
    budget = _JsonBudget(capacity)
    retained = budget.copy(value)
    return retained, capacity - budget.remaining, budget.partial


def _message(message: BaseMessage) -> dict[str, object]:
    result: dict[str, object] = {
        "role": _ROLES.get(message.type, message.type),
        "id": message.id,
        "name": message.name,
    }
    if isinstance(message, AIMessage):
        result["tool_calls"] = message.tool_calls
        result["invalid_tool_calls"] = message.invalid_tool_calls
        result["usage_metadata"] = message.usage_metadata
    if isinstance(message, AIMessageChunk) and message.tool_call_chunks:
        result["tool_call_chunks"] = message.tool_call_chunks
    if (tool_call_id := getattr(message, "tool_call_id", None)) is not None:
        result["tool_call_id"] = tool_call_id
        result["status"] = getattr(message, "status", None)
    if message.response_metadata:
        result["response_metadata"] = message.response_metadata
    if message.additional_kwargs:
        result["additional_kwargs"] = message.additional_kwargs
    result["content"] = message.content
    return result


def _limit_items(
    items: Sequence[object], budget: _JsonBudget, *, limit: int
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in islice(items, limit):
        if budget.remaining < 32:
            budget.partial = True
            break
        copied = budget.copy(item)
        if isinstance(copied, dict):
            result.append(copied)
    budget.partial |= len(items) > limit
    return result


def capture_snapshot(
    messages: Sequence[BaseMessage],
    tools: Sequence[object],
    capacity: int,
    partial_chunks: Sequence[ChatGenerationChunk] = (),
) -> tuple[TraceModelSnapshot | None, int]:
    if capacity < 256:
        return None, 0
    if not messages and partial_chunks:
        # Prefer the callback aggregate when supplied by LangChain.
        aggregate = None
        with suppress(Exception):
            aggregate = merge_chat_generation_chunks(list(partial_chunks))
        messages = (
            [aggregate.message]
            if aggregate is not None
            else [chunk.message for chunk in partial_chunks]
        )
    budget = _JsonBudget(min(capacity, MODEL_SNAPSHOT_BYTES) - 128)
    initial = budget.remaining
    # Leave room for tool definitions when messages fill their share of the budget.
    tool_budget = _JsonBudget(budget.remaining // 4 if tools else 0)
    initial_tools = tool_budget.remaining
    bound_tools: list[object] = []
    for tool in islice(tools, _TOOL_ID_LIMIT):
        if isinstance(tool, dict):
            bound_tools.append(tool)
        else:
            bound_tools.extend(serialize_tools([tool]))
    tool_payload = _limit_items(bound_tools, tool_budget, limit=_TOOL_ID_LIMIT)
    budget.remaining -= initial_tools - tool_budget.remaining
    count = min(len(messages), _MODEL_MESSAGE_LIMIT)
    payload = _limit_items(
        [_message(message) for message in messages[:count]],
        budget,
        limit=_MODEL_MESSAGE_LIMIT,
    )
    return TraceModelSnapshot(
        messages=payload,
        tools=tool_payload,
        partial=budget.partial
        or tool_budget.partial
        or len(messages) > count
        or len(tools) > len(bound_tools),
    ), initial - budget.remaining + 128


def _chunk_cost(value: object, remaining: int, depth: int = 0) -> int:
    """Bound retained content without copying or serializing every token."""
    if remaining < 0 or depth == _MAX_DEPTH:
        return remaining + 1
    if isinstance(value, str):
        return 4 * len(value) + 16
    if isinstance(value, (dict, list, tuple)):
        items = (
            (part for pair in value.items() for part in pair)
            if isinstance(value, dict)
            else value
        )
        cost = 16
        for item in items:
            cost += _chunk_cost(item, remaining - cost, depth + 1)
            if cost > remaining:
                break
        return cost
    if isinstance(value, int):
        return value.bit_length() // 8 + 24
    if value is None or isinstance(value, float):
        return 24
    return remaining + 1


def _call_key(call: object, *, malformed: bool) -> str | None:
    if not isinstance(call, dict):
        return None
    identity = call.get("id")
    if isinstance(identity, str) and identity and identity.lower() != "null":
        return f"id:{identity}" if len(identity) <= 255 else None
    # A placeholder alone cannot identify a call across invocations.
    name, args = call.get("name"), call.get("args")
    if malformed and isinstance(args, str) and 0 < len(args) <= 4096:
        return "invalid:" + json.dumps(
            [name if isinstance(name, str) and len(name) <= 255 else None, args]
        )
    return None


def _tool_keys(messages: list[dict[str, object]]) -> tuple[set[str], set[str]]:
    related: set[str] = set()
    invalid: set[str] = set()
    for message in messages:
        for key, malformed in (("tool_calls", False), ("invalid_tool_calls", True)):
            calls = message.get(key)
            for call in calls if isinstance(calls, list) else []:
                identity = _call_key(call, malformed=malformed)
                if identity is not None:
                    related.add(identity)
                    if malformed:
                        invalid.add(identity)
    return related, invalid


def matched_tool_ids(payload: TraceModelEvidence) -> set[str]:
    keys: set[str] = set()
    for snapshot in (payload.input, payload.output):
        if snapshot is not None:
            keys.update(_tool_keys(snapshot.messages)[0])
    return {key.removeprefix("id:") for key in keys if key.startswith("id:")}


def retain_tool_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    return _limit_items(
        results, _JsonBudget(MODEL_SNAPSHOT_BYTES), limit=_TOOL_ID_LIMIT
    )


@dataclass(slots=True)
class RecordedModelCall:
    call_id: str
    model: str | None
    ref: str = field(default_factory=lambda: uuid4().hex)
    started: float = field(default_factory=monotonic)
    input: TraceModelSnapshot | None = None
    output: TraceModelSnapshot | None = None
    output_state: TraceModelOutputState = TraceModelOutputState.UNAVAILABLE

    def evidence(self, normalization: list[TraceNormalization]) -> TraceModelEvidence:
        return TraceModelEvidence(
            input=self.input,
            output=self.output,
            output_state=self.output_state,
            normalization=normalization,
        )

    def index(
        self,
        evidence: TraceModelEvidence,
        *,
        stored: bool,
        session_id: str,
        observed_through_rank: int | None,
    ) -> TraceModelIndex:
        related: set[str] = set()
        invalid: set[str] = set()
        for snapshot in (evidence.input, evidence.output):
            if snapshot is not None:
                seen, malformed = _tool_keys(snapshot.messages)
                related.update(seen)
                invalid.update(malformed)
        for attempt in evidence.normalization:
            for rewrite in attempt.rewrites:
                if rewrite.tool_call_id is not None:
                    identity = f"id:{rewrite.tool_call_id}"
                    invalid.add(identity)
                    related.add(identity)

        def fingerprints(items: set[str]) -> list[str]:
            return [
                sha256(f"{session_id}\0{key}".encode("utf-8")).hexdigest()
                for key in sorted(items)[:_TOOL_ID_LIMIT]
            ]

        partial = (
            evidence.input is None
            or evidence.input.partial
            or evidence.output_state
            in (TraceModelOutputState.PARTIAL, TraceModelOutputState.UNAVAILABLE)
            or any(attempt.partial for attempt in evidence.normalization)
        )
        return TraceModelIndex(
            ref=self.ref,
            call_id=self.call_id,
            model=self.model,
            observed_through_rank=observed_through_rank,
            completeness=(
                TraceHttpCompleteness.UNAVAILABLE
                if not stored
                else TraceHttpCompleteness.PARTIAL
                if partial
                else TraceHttpCompleteness.COMPLETE
            ),
            related_tools=fingerprints(related),
            observed_invalid_tools=fingerprints(invalid),
        )


class ModelSnapshotCallback(BaseCallbackHandler):
    """Observe the final LC invocation and its assembled success/error generations."""

    run_inline = True

    def __init__(self, capture: ModelHttpCapture) -> None:
        self._capture = capture
        self._run_id: UUID | None = None
        self._chunks: list[ChatGenerationChunk] = []
        self._chunk_remaining = _PARTIAL_CHUNK_BYTES
        self._chunk_seen = False
        self._chunk_limit_reached = False

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        invocation_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if self._run_id is not None or not messages:
            return
        with suppress(Exception):
            self._run_id = run_id
            tools = (invocation_params or {}).get("tools")
            await self._capture.input_snapshot(
                messages[0], tools if isinstance(tools, (list, tuple)) else ()
            )

    def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: object = None,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        if (
            self._run_id != run_id
            or self._chunk_limit_reached
            or not isinstance(chunk, ChatGenerationChunk)
        ):
            return
        self._chunk_seen = True
        cost = _chunk_cost(_message(chunk.message), self._chunk_remaining)
        if cost > self._chunk_remaining or len(self._chunks) >= _PARTIAL_CHUNK_LIMIT:
            self._chunk_limit_reached = True
            return
        self._chunk_remaining -= cost
        self._chunks.append(chunk)

    async def on_llm_end(
        self, response: LLMResult, *, run_id: UUID, **kwargs: Any
    ) -> None:
        if self._run_id == run_id:
            await self._output(response, partial=False)

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        if self._run_id == run_id:
            response = kwargs.get("response")
            await self._output(
                response if isinstance(response, LLMResult) else None, partial=True
            )

    async def _output(self, response: LLMResult | None, *, partial: bool) -> None:
        with suppress(Exception):
            # LC adds a synthetic non-chunk generation with HTTP error metadata.
            generation_type = ChatGenerationChunk if partial else ChatGeneration
            messages: list[BaseMessage] = []
            for batch in islice(
                response.generations if response is not None else [],
                _MODEL_MESSAGE_LIMIT,
            ):
                for generation in islice(batch, _MODEL_MESSAGE_LIMIT - len(messages)):
                    if isinstance(generation, generation_type):
                        messages.append(generation.message)
            await self._capture.output_snapshot(
                messages,
                partial=partial,
                had_chunks=self._chunk_seen,
                partial_chunks=tuple(self._chunks) if partial and not messages else (),
            )
        self._chunks.clear()
