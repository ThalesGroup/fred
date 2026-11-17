# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Diagnostic configuration, request sampling and content-free export."""

from __future__ import annotations

import socket
import time
from collections.abc import Iterator

import pytest
from fred_core.portable.observability import (
    LoggingTracer,
    Tracer,
    get_tracer,
    set_tracer,
)
from fred_core.technical_tracing import activate_span, extract_trace, technical_span
from fred_runtime.app import technical_tracing as module
from fred_runtime.app.config import PodObservabilityConfig, TracerBackend
from fred_runtime.app.observability_factory import _build_tracer
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError


def sampled_parent():
    return {"traceparent": f"00-{'a' * 32}-{'b' * 16}-01"}


def parent_context():
    return trace.get_current_span(extract_trace(sampled_parent())).get_span_context()


@pytest.fixture
def common(monkeypatch) -> Iterator[tuple[module.OTLPTracer, InMemorySpanExporter]]:
    previous = get_tracer()
    exporter = InMemorySpanExporter()
    monkeypatch.setattr(module, "OTLPSpanExporter", lambda **kwargs: exporter)
    # A stale shell setting must not activate background traces or payload capture.
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    monkeypatch.setenv("LANGFUSE_CAPTURE_CONTENT", "true")
    tracer = _build_tracer(
        PodObservabilityConfig.model_validate(
            {
                "tracer": "diagnostic",
                "diagnostic": {"collector_endpoint": "http://127.0.0.1:4318/v1/traces"},
            }
        )
    )
    assert isinstance(tracer, module.OTLPTracer)
    set_tracer(tracer)
    try:
        yield tracer, exporter
    finally:
        set_tracer(previous)
        tracer.shutdown()


@pytest.mark.parametrize(
    "carrier",
    [{}, {"traceparent": "invalid"}, {"traceparent": f"00-{'a' * 32}-{'b' * 16}-00"}],
)
def test_only_sampled_requests_record(common, carrier):
    tracer, exporter = common
    with technical_span("agent.http", context=extract_trace(carrier)):
        agent = tracer.start_span("agent.stream")
        with activate_span(agent):
            tracer.start_span("v2.react.model", parent=agent).end()
        agent.end()
    tracer.provider.force_flush()
    assert not exporter.get_finished_spans()


def test_diagnostic_exports_only_technical_fields_and_parents(common):
    tracer, exporter = common
    assert not tracer.captures_content
    with technical_span("agent.http", context=extract_trace(sampled_parent())):
        agent = tracer.start_span("agent.stream", context={"user": "private"})
        agent.set_io(input="private question", output="private answer")
        model = tracer.start_span("v2.react.model", parent=agent)
        model.set_usage(model="private-model", usage={"total": 8})
        model.set_attribute("first_chunk_ms", 12.5)
        model.set_attribute("status", "error")
        model.set_attribute("secret", "private")
        with activate_span(model):
            with technical_span("mcp.http"):
                pass
        model.end()
        agent.end()
    tracer.provider.force_flush()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert len(spans) == 4
    assert {s.context.trace_id for s in spans.values()} == {int("a" * 32, 16)}
    assert spans["agent.http"].parent.span_id == int("b" * 16, 16)
    assert spans["agent.stream"].parent.span_id == spans["agent.http"].context.span_id
    assert (
        spans["v2.react.model"].parent.span_id == spans["agent.stream"].context.span_id
    )
    assert spans["mcp.http"].parent.span_id == spans["v2.react.model"].context.span_id
    assert spans["v2.react.model"].attributes["first_chunk_ms"] == 12.5
    assert spans["v2.react.model"].status.status_code is trace.StatusCode.ERROR
    exported = "".join(s.to_json() for s in spans.values())
    assert "private" not in exported
    assert "langfuse" not in exported


@pytest.mark.parametrize(
    "backend, expected",
    [
        (TracerBackend.null, Tracer),
        (TracerBackend.logging, LoggingTracer),
    ],
)
def test_yaml_selects_backend(common, backend, expected):
    assert type(_build_tracer(PodObservabilityConfig(tracer=backend))) is expected


@pytest.mark.parametrize(
    "config",
    [
        {"tracer": "diagnostic"},
        {"tracer": "diagnostic", "diagnostic": {"collector_endpoint": "not-a-url"}},
    ],
)
def test_diagnostic_requires_valid_endpoint(config):
    with pytest.raises(ValidationError):
        PodObservabilityConfig.model_validate(config)


@pytest.mark.allow_hosts(["127.0.0.1"])
def test_unavailable_collector_does_not_fail_turn_or_unbound_shutdown(monkeypatch):
    # Reserve a local non-listening port: no real service can receive the spans.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        tracer = module.OTLPTracer(
            collector_endpoint=f"http://127.0.0.1:{reserved.getsockname()[1]}/v1/traces"
        )
        started = time.monotonic()
        with trace.use_span(trace.NonRecordingSpan(parent_context())):
            tracer.start_span("agent.stream").end()
        tracer.shutdown()
        assert time.monotonic() - started < 6


@pytest.mark.allow_hosts(["127.0.0.1"])
def test_stalled_collector_has_bounded_shutdown(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    arrived = threading.Event()
    release = threading.Event()

    class StalledReceiver(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            arrived.set()
            release.wait(10)

        def log_message(self, format: str, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), StalledReceiver)
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    tracer = module.OTLPTracer(
        collector_endpoint=f"http://127.0.0.1:{server.server_port}/v1/traces"
    )
    try:
        with trace.use_span(trace.NonRecordingSpan(parent_context())):
            tracer.start_span("agent.stream").end()
        started = time.monotonic()
        tracer.shutdown()
        elapsed = time.monotonic() - started
        assert arrived.is_set()
        assert elapsed < 6
        print(f"Stalled collector: shutdown completed in {elapsed:.2f}s")
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()
