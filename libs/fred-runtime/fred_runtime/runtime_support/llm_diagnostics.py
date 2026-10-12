# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Per-invocation streaming observations, with no retained messages or chunks."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
from fred_core.model.diagnostics import ModelHttpObservation
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai.chat_models._client_utils import StreamChunkTimeoutError
from openai import APIConnectionError, APIStatusError

Scalar = str | int | float | bool | None

# Pod-local instantaneous counts, never an admission/concurrency control.
_active: dict[tuple[str, str], int] = {}
_active_lock = threading.Lock()


def change_active(model: str, role: str, delta: int) -> int:
    key = (model, role)
    with _active_lock:
        count = _active.get(key, 0) + delta
        if count:
            _active[key] = count
        else:
            _active.pop(key, None)
        return count


def exception_chain(exc: BaseException) -> tuple[list[BaseException], bool]:
    pending = deque([exc])
    seen: set[int] = set()
    result: list[BaseException] = []
    truncated = False
    while pending and len(result) < 16:
        current = pending.popleft()
        if id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(cause)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions[:8])
            truncated |= len(current.exceptions) > 8
    return result, truncated or bool(pending)


def classify_error(exc: BaseException) -> dict[str, Scalar]:
    if isinstance(exc, asyncio.CancelledError):
        return {"error_code": "cancelled"}
    chain, _ = exception_chain(exc)
    for current in chain:
        if isinstance(current, StreamChunkTimeoutError):
            return {
                "error_code": "stream_idle_timeout",
                "exception_type": "StreamChunkTimeoutError",
                "timeout_s": current.timeout_s,
                "sdk_chunks_received": current.chunks_received,
            }
        for cls, code in (
            (httpx.ConnectTimeout, "connect_timeout"),
            (httpx.ReadTimeout, "read_timeout"),
            (httpx.WriteTimeout, "write_timeout"),
            (httpx.PoolTimeout, "pool_timeout"),
            (httpx.RemoteProtocolError, "remote_protocol_error"),
        ):
            if isinstance(current, cls):
                return {"error_code": code, "exception_type": cls.__name__}
        if isinstance(current, (APIStatusError, httpx.HTTPStatusError)):
            status = (
                current.status_code
                if isinstance(current, APIStatusError)
                else current.response.status_code
            )
            return {
                "error_code": "rate_limited"
                if status == 429
                else "provider_http_error",
                "http_status": status,
            }
    # Transport wrappers can hide a more specific cause; check them last.
    if any(isinstance(e, (APIConnectionError, httpx.NetworkError)) for e in chain):
        return {"error_code": "connection_error"}
    if isinstance(exc, asyncio.CancelledError):
        return {"error_code": "cancelled"}
    return {"error_code": "unknown"}


def streaming_selection(
    model: object, settings: dict[str, Any], *, has_tools: bool
) -> bool | None:
    disabled = getattr(model, "disable_streaming", None)
    if disabled is True or (disabled == "tool_calling" and has_tools):
        return False
    if "stream" in settings and not settings["stream"]:
        return False
    fields_set = getattr(model, "model_fields_set", set())
    streaming = getattr(model, "streaming", None)
    if "streaming" in fields_set and streaming is False:
        return False
    if settings.get("stream") or ("streaming" in fields_set and streaming is True):
        return True
    # Graph callbacks can select streaming even with a default-valued False.
    return None


@dataclass
class LlmObservation:
    model: str
    role: str
    streaming: bool | None
    http: ModelHttpObservation = field(default_factory=ModelHttpObservation)
    call_id: str = field(default_factory=lambda: uuid4().hex)
    first: float | None = None
    last: float | None = None
    max_gap_ms: float | None = None
    chunks: int = 0
    run_id: str | None = None
    parent_run_id: str | None = None

    def chunk(self) -> None:
        now = time.monotonic()
        if self.first is None:
            self.first = now
        if self.last is not None:
            self.max_gap_ms = max(self.max_gap_ms or 0, (now - self.last) * 1000)
        self.last = now
        self.chunks += 1

    def fields(self, *, at: float | None = None) -> dict[str, Scalar]:
        now = time.monotonic() if at is None else at
        fields: dict[str, Scalar] = {
            "llm_call_id": self.call_id,
            "model_name": self.model,
            "llm_role": self.role,
            "observed_chunks": self.chunks,
            "elapsed_ms": (now - self.http.started) * 1000,
            "stage": (
                "streaming"
                if self.chunks
                else "before_first_chunk"
                if self.streaming is True
                or self.http.fields.get("response_streaming") is True
                else "non_streaming"
                if self.streaming is False
                else "unknown"
            ),
            **self.http.fields,
        }
        if self.first is not None and self.last is not None:
            fields["first_chunk_ms"] = (self.first - self.http.started) * 1000
            fields["terminal_silence_ms"] = (now - self.last) * 1000
        if self.max_gap_ms is not None:
            fields["max_chunk_gap_ms"] = self.max_gap_ms
        if self.run_id:
            fields["model_run_id"] = self.run_id
        if self.parent_run_id:
            fields["parent_run_id"] = self.parent_run_id
        return fields


class LlmProgressCallback(BaseCallbackHandler):
    # The synchronous callback only updates scalar state; avoid per-token threads.
    run_inline = True

    def __init__(self, observation: LlmObservation) -> None:
        self.observation = observation

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.observation.run_id = str(run_id)
        self.observation.parent_run_id = str(parent_run_id) if parent_run_id else None

    def on_llm_new_token(
        self, token: str | list[str | dict[str, Any]], **kwargs: Any
    ) -> None:
        self.observation.chunk()


@dataclass(frozen=True)
class LlmFailure:
    fields: dict[str, Scalar]


def attach_failure(exc: BaseException, fields: dict[str, Scalar]) -> None:
    setattr(exc, "_fred_llm_failure", LlmFailure(dict(fields)))


def failed_calls(exc: BaseException) -> tuple[list[dict[str, Scalar]], bool]:
    chain, truncated = exception_chain(exc)
    calls: dict[str, dict[str, Scalar]] = {}
    for current in chain:
        failure = getattr(current, "_fred_llm_failure", None)
        if isinstance(failure, LlmFailure):
            calls[str(failure.fields["llm_call_id"])] = failure.fields
    return list(calls.values()), truncated
