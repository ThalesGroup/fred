# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Explicit, bounded OTLP tracing for agent requests, including SSE cleanup."""

from __future__ import annotations

import asyncio

from fred_core.portable.observability import get_tracer
from fred_core.technical_tracing import (
    TechnicalTracer,
    extract_trace,
    technical_span,
)
from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ParentBased
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class OTLPTracer(TechnicalTracer):
    """Developer diagnostics: technical fields only, sampled incoming requests only."""

    def __init__(self, *, collector_endpoint: str) -> None:
        self.provider = TracerProvider(
            sampler=ParentBased(ALWAYS_OFF),
            resource=Resource({"service.name": "fred-agents"}),
            span_limits=SpanLimits(max_attributes=16, max_attribute_length=2048),
        )
        self.provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=collector_endpoint, timeout=3),
                max_queue_size=2048,
                max_export_batch_size=256,
                schedule_delay_millis=1000,
                export_timeout_millis=3000,
            )
        )
        super().__init__(self.provider.get_tracer("fred"))

    def shutdown(self) -> None:
        # Locked SDK bounds the batch worker join at 30 s. Our queue holds at
        # most eight batches plus one in flight, each with a 3 s export budget.
        # Keep the public shutdown API; do not abandon a to_thread worker.
        self.provider.shutdown()


async def shutdown_technical_tracing() -> None:
    tracer = get_tracer()
    if isinstance(tracer, OTLPTracer):
        await asyncio.to_thread(tracer.shutdown)


class TechnicalTracingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", ())
            if key == b"traceparent"
        }
        if not isinstance(get_tracer(), TechnicalTracer):
            from fred_runtime.integrations.v2_runtime.adapters import (
                LangfuseTracerAdapter,
            )

            # LF-only retains its exporter and observation tree, but now accepts
            # W3C parents without fabricating an additional HTTP observation.
            if isinstance(get_tracer(), LangfuseTracerAdapter):
                token = otel_context.attach(extract_trace(headers))
                try:
                    await self.app(scope, receive, send)
                finally:
                    otel_context.detach(token)
            else:
                await self.app(scope, receive, send)
            return
        with technical_span("agent.http", context=extract_trace(headers)) as span:
            response_complete = False
            disconnected = False

            async def traced_receive() -> Message:
                nonlocal disconnected
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                return message

            async def traced_send(message: Message) -> None:
                nonlocal response_complete
                if message["type"] == "http.response.start":
                    status = message["status"]
                    span.set_attribute("http.response.status_code", status)
                    if status >= 400:
                        span.set_attribute("status", "error")
                await send(message)
                if message["type"] == "http.response.body" and not message.get(
                    "more_body", False
                ):
                    response_complete = True

            try:
                await self.app(scope, traced_receive, traced_send)
            finally:
                # ASGI may report disconnect after normal completion, including
                # while the final send is returning. Classify after cleanup;
                # only a successfully sent final body establishes completion.
                if disconnected and not response_complete:
                    span.set_attribute("status", "cancelled")
