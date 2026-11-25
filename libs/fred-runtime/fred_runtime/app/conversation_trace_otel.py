# Copyright Thales 2026
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

from collections.abc import Mapping
from contextvars import ContextVar
from hashlib import sha256

from fred_sdk.contracts.context import PortableContext
from fred_sdk.contracts.runtime import SpanPort, TracerPort
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)

from fred_runtime.app.conversation_trace import current_span_capture

_TRACE_SEED: ContextVar[str | None] = ContextVar("fred_otel_trace_seed", default=None)


class _ExchangeIdGenerator(RandomIdGenerator):
    def generate_trace_id(self) -> int:
        seed = _TRACE_SEED.get()
        if seed:
            return int.from_bytes(sha256(seed.encode()).digest()[:16])
        return super().generate_trace_id()


class _TraceSampler(Sampler):
    """Keep the export decision while recording spans for an admitted capture."""

    def __init__(self, export_sampler: Sampler) -> None:
        self._export = export_sampler

    def should_sample(
        self,
        parent_context,
        trace_id,
        name,
        kind=None,
        attributes=None,
        links=None,
        trace_state=None,
    ) -> SamplingResult:
        result = self._export.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )
        if result.decision == Decision.DROP and current_span_capture() is not None:
            return SamplingResult(Decision.RECORD_ONLY, attributes, result.trace_state)
        return result

    def get_description(self) -> str:
        return f"FredCapture{{{self._export.get_description()}}}"


class _CaptureProcessor(SpanProcessor):
    def on_end(self, span: ReadableSpan) -> None:
        capture = current_span_capture()
        if capture is not None:
            capture.note_otel_span(span)


def build_trace_provider(export_rate: float) -> TracerProvider:
    provider = TracerProvider(
        sampler=None if export_rate == 1 else TraceIdRatioBased(export_rate),
        id_generator=_ExchangeIdGenerator(),
    )
    # Wrap the SDK-selected sampler before creating tracers on this provider.
    provider.sampler = _TraceSampler(provider.sampler)
    provider.add_span_processor(_CaptureProcessor())
    return provider


class _LocalSpan(SpanPort):
    def __init__(self, span: trace.Span, log_span: SpanPort):
        self._span = span
        self._log_span = log_span

    @property
    def span_id(self) -> str:
        return trace.format_span_id(self._span.get_span_context().span_id)

    @property
    def trace_id(self) -> str:
        return trace.format_trace_id(self._span.get_span_context().trace_id)

    def set_attribute(self, key: str, value) -> None:
        self._log_span.set_attribute(key, value)
        if key.startswith("fred.") and isinstance(value, str):
            self._span.set_attribute(key, value)

    def set_usage(self, *, model=None, usage=None, cost=None) -> None:
        self._log_span.set_usage(model=model, usage=usage, cost=cost)

    def set_io(self, *, input=None, output=None) -> None:
        self._log_span.set_io(input=input, output=output)

    def end(self) -> None:
        try:
            self._span.end()
        finally:
            self._log_span.end()


class ManagedCaptureTracer(TracerPort):
    """Create local OTel spans only for admitted captures without Langfuse."""

    def __init__(self, fallback: TracerPort, *, provider: TracerProvider | None = None):
        self._fallback = fallback
        self._tracer = (provider or build_trace_provider(0)).get_tracer("fred.runtime")

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: SpanPort | None = None,
        **kwargs: object,
    ) -> SpanPort:
        log_span = self._fallback.start_span(
            name, context=context, attributes=attributes, parent=parent, **kwargs
        )
        if current_span_capture() is None:
            return log_span
        parent_context = (
            trace.set_span_in_context(parent._span, Context())
            if isinstance(parent, _LocalSpan)
            else Context()
        )
        seed = None
        if isinstance(context, PortableContext):
            seed = (
                context.trace_id
                or context.baggage.get("exchange_id")
                or context.request_id
            )
        token = _TRACE_SEED.set(seed)
        try:
            return _LocalSpan(
                self._tracer.start_span(name, context=parent_context), log_span
            )
        finally:
            _TRACE_SEED.reset(token)
