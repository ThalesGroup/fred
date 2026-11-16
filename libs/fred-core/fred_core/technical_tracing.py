# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Content-free technical tracing through the existing portable tracing port.

Only the explicitly configured OTel adapter records these scopes. The SDK and
exporter belong to the application; core needs only the context/trace API.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable, Coroutine, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from fred_core.portable.observability import Span, Tracer, get_tracer

# Names and string attributes are closed vocabularies, never request/model data.
_CATEGORIES = {
    "agent.invoke": "runtime",
    "agent.stream": "runtime",
    "v2.graph.await_human": "runtime",
    "v2.graph.model": "llm",
    "v2.graph.structured_model": "llm",
    "v2.react.model": "llm",
    "v2.graph.tool": "tool",
    "v2.graph.runtime_tool": "tool",
    "v2.react.runtime_tool": "tool",
    "tool.invoke": "tool",
    "artifact.publish": "tool",
    "resource.fetch": "tool",
    "agent.http": "runtime",
    "pod_authz": "auth",
    "runtime_binding": "control_plane",
    "runtime_binding_internal": "control_plane",
    "control_plane.runtime": "control_plane",
    "auth.jwt.verify": "auth",
    "auth.m2m.acquire": "auth",
    "iam.jwks.http": "keycloak",
    "iam.token.initial": "keycloak",
    "iam.token.renewal": "keycloak",
    "mcp.http": "mcp",
    "history.write": "persistence",
    "checkpoint.operation": "persistence",
}
_PEERS = {
    "v2.react.model": "llm",
    "v2.graph.model": "llm",
    "v2.graph.structured_model": "llm",
    "control_plane.runtime": "control-plane",
    "iam.jwks.http": "keycloak",
    "iam.token.initial": "keycloak",
    "iam.token.renewal": "keycloak",
    "mcp.http": "mcp",
}
_NUMERIC_ATTRIBUTES = frozenset(
    {"first_chunk_ms", "duration_ms", "http.response.status_code"}
)
_PROPAGATOR = TraceContextTextMapPropagator()
ROOT_TRACE_ID: ContextVar[int | None] = ContextVar("fred_root_trace_id", default=None)
P = ParamSpec("P")
R = TypeVar("R")


class TechnicalSpan(Span):
    def __init__(self, span: trace.Span):
        self.otel_span = span

    @property
    def span_id(self) -> str:
        return trace.format_span_id(self.otel_span.get_span_context().span_id)

    def set_attribute(self, key: str, value: Any) -> None:
        if key == "status" and value in ("ok", "success", "error", "cancelled"):
            self.otel_span.set_attribute("fred.outcome", value)
            if value in ("error", "cancelled"):
                self.otel_span.set_status(trace.StatusCode.ERROR)
        elif (
            key in _NUMERIC_ATTRIBUTES
            and type(value) in (int, float)
            and math.isfinite(value)
            and value >= 0
        ):
            self.otel_span.set_attribute(key, value)

    def end(self) -> None:
        self.otel_span.end()


class TechnicalTracer(Tracer):
    """Portable adapter: ignore identities, IO, errors and arbitrary attributes."""

    def __init__(self, tracer: trace.Tracer):
        self.otel_tracer = tracer

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: Span | None = None,
        **kwargs: object,
    ) -> Span:
        # A portable context is business data, never a trusted tracing context.
        otel_context = (
            trace.set_span_in_context(parent.otel_span)
            if isinstance(parent, TechnicalSpan)
            else None
        )
        span = self.open_span(name, context=otel_context)
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        return span

    def open_span(
        self,
        name: str,
        *,
        context: Context | None = None,
        start_time: int | None = None,
    ) -> TechnicalSpan:
        # Unknown dynamic names cannot carry user content into an export.
        safe_name = name if name in _CATEGORIES else "runtime.operation"
        attributes = {
            "fred.category": _CATEGORIES.get(name, "runtime"),
            "fred.operation": safe_name,
        }
        peer = _PEERS.get(name)
        if peer:
            attributes["peer.service"] = peer
        kind = (
            trace.SpanKind.CLIENT
            if peer
            else trace.SpanKind.SERVER
            if name == "agent.http"
            else trace.SpanKind.INTERNAL
        )
        return TechnicalSpan(
            self.otel_tracer.start_span(
                safe_name,
                context=context,
                kind=kind,
                attributes=attributes,
                start_time=start_time,
            )
        )


@contextmanager
def activate_span(span: Span | None) -> Iterator[None]:
    otel_span = getattr(span, "otel_span", None)
    if isinstance(otel_span, trace.Span):
        with trace.use_span(
            otel_span, record_exception=False, set_status_on_exception=False
        ):
            yield
    else:
        yield


@contextmanager
def technical_span(name: str, *, context: Context | None = None) -> Iterator[Span]:
    tracer = get_tracer()
    span = (
        tracer.open_span(name, context=context)
        if isinstance(tracer, TechnicalTracer)
        else Span()
    )
    with activate_span(span):
        try:
            yield span
        except asyncio.CancelledError:
            span.set_attribute("status", "cancelled")
            raise
        except BaseException:
            span.set_attribute("status", "error")
            raise
        finally:
            span.end()


def trace_async(
    name: str,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]
]:
    def decorate(
        fn: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(fn)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with technical_span(name):
                return await fn(*args, **kwargs)

        return wrapped

    return decorate


def trace_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if trace.get_current_span().get_span_context().is_valid:
        # Deliberately omit tracestate/baggage: only the W3C parent crosses Fred.
        _PROPAGATOR.inject(headers)
    return {key: value for key, value in headers.items() if key == "traceparent"}


def extract_trace(headers: Mapping[str, str]) -> Context:
    return _PROPAGATOR.extract(
        {"traceparent": headers.get("traceparent", "")}, context=Context()
    )


def record_timed_operation(name: str, seconds: float, outcome: str) -> None:
    """Bridge the existing completed M2M observer, without changing token code.

    The observed monotonic duration is anchored at the observer's wall-clock end.
    Concurrent waiters get acquire spans; the shared network refresh emits once.
    """
    tracer = get_tracer()
    if (
        not isinstance(tracer, TechnicalTracer)
        or not trace.get_current_span().get_span_context().is_valid
        or not math.isfinite(seconds)
        or seconds < 0
    ):
        return
    end = time.time_ns()
    span = tracer.open_span(name, start_time=end - int(seconds * 1_000_000_000))
    span.set_attribute("status", outcome)
    span.otel_span.end(end_time=end)
