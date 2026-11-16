# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Common OTLP observations, checked against the locked Langfuse wire format."""

from __future__ import annotations

import json
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
from fred_runtime.integrations.v2_runtime import adapters
from fred_sdk.contracts.context import PortableContext, PortableEnvironment
from langfuse._client.attributes import (
    create_generation_attributes,
    create_span_attributes,
)
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def context(exchange: str = "exchange-1") -> PortableContext:
    return PortableContext(
        request_id="request-1",
        correlation_id="correlation-1",
        actor="alice",
        tenant="fred",
        environment=PortableEnvironment.DEV,
        session_id="session-1",
        user_id="user-1",
        agent_name="Research",
        baggage={"exchange_id": exchange, "execution_action": "execute"},
    )


@pytest.fixture
def common(monkeypatch) -> Iterator[tuple[module.OTLPTracer, InMemorySpanExporter]]:
    previous = get_tracer()
    exporter = InMemorySpanExporter()
    monkeypatch.setattr(module, "OTLPSpanExporter", lambda **kwargs: exporter)
    monkeypatch.setattr(
        adapters,
        "Langfuse",
        type(
            "NoClient",
            (),
            {
                "create_trace_id": staticmethod(
                    __import__("langfuse").Langfuse.create_trace_id
                ),
                "__init__": lambda self, **kwargs: pytest.fail(
                    "No SDK client in common mode"
                ),
            },
        ),
    )
    tracer = module.OTLPTracer()
    set_tracer(tracer)
    try:
        yield tracer, exporter
    finally:
        set_tracer(previous)
        tracer.shutdown()


@pytest.mark.parametrize("capture", [False, True])
def test_common_observations_match_sdk_attributes(common, capture):
    tracer, exporter = common
    tracer.observations._capture_content = capture
    carrier = {"traceparent": f"00-{'a' * 32}-{'b' * 16}-01"}
    with technical_span("agent.http", context=extract_trace(carrier)):
        agent = tracer.start_span("agent.stream", context=context())
        agent.set_io(input="question", output="answer")
        agent.set_usage(model="demo-model", usage={"total": 8})
        model = tracer.start_span("v2.react.model", context=context(), parent=agent)
        model.set_io(input={"messages": ["question"]}, output="answer")
        model.set_usage(
            model="demo-model", usage={"input": 3, "output": 5}, cost={"total": 0.1}
        )
        model.set_attribute("first_chunk_ms", 12.5)
        model.set_attribute("status", "error")
        model.end()
        model.end()
        agent.end()
    assert tracer.provider.force_flush()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert len(exporter.get_finished_spans()) == 3
    assert {s.context.trace_id for s in spans.values()} == {int("a" * 32, 16)}
    assert (
        spans["v2.react.model"].parent.span_id == spans["agent.stream"].context.span_id
    )
    expected = create_generation_attributes(
        observation_type="generation",
        model="demo-model",
        usage_details={"input": 3, "output": 5},
        cost_details={"total": 0.1},
        metadata={"first_chunk_ms": 12.5, "status": "error"},
        level="ERROR",
        input={"messages": ["question"]} if capture else None,
        output="answer" if capture else None,
    )
    actual = spans["v2.react.model"].attributes
    for key, value in expected.items():
        if key.startswith("langfuse.observation.metadata."):
            assert json.loads(actual["langfuse.observation.metadata"])[
                key.removeprefix("langfuse.observation.metadata.")
            ] == json.loads(value)
        else:
            assert actual[key] == value
    assert actual["first_chunk_ms"] == 12.5
    assert actual["fred.outcome"] == "error"
    assert spans["v2.react.model"].status.status_code is trace.StatusCode.ERROR
    root = spans["agent.stream"].attributes
    assert root["session.id"] == "session-1"
    assert root["user.id"] == "user-1"
    assert root["langfuse.internal.as_root"] is True
    assert root["langfuse.trace.name"] == "Research"
    assert (
        json.loads(root["langfuse.observation.metadata"])["fred_session_id"]
        == "session-1"
    )
    for key, value in create_span_attributes(
        observation_type="agent",
        metadata={"model_name": "demo-model", "usage_total": 8},
    ).items():
        if key.startswith("langfuse.observation.metadata."):
            assert json.loads(root["langfuse.observation.metadata"])[
                key.removeprefix("langfuse.observation.metadata.")
            ] == json.loads(value)
        else:
            assert root[key] == value
    if capture:
        assert root["langfuse.trace.input"] == "question"
        assert root["langfuse.trace.output"] == "answer"
    else:
        assert "question" not in "".join(s.to_json() for s in spans.values())
        assert "langfuse.observation.input" not in actual


def test_explicit_parent_wins_active_context_and_seed(common):
    tracer, exporter = common
    root = tracer.start_span("agent.stream", context=context())
    with technical_span(
        "agent.http",
        context=extract_trace(
            {
                "traceparent": f"00-{'c' * 32}-{'d' * 16}-01",
            }
        ),
    ):
        child = tracer.start_span("tool.invoke", context=context("other"), parent=root)
        with activate_span(child):
            with technical_span("mcp.http"):
                pass
        child.end()
    root.end()
    resumed = tracer.start_span("agent.stream", context=context())
    resumed.end()
    tracer.provider.force_flush()
    spans = exporter.get_finished_spans()
    roots = [s for s in spans if s.name == "agent.stream"]
    child_span = next(s for s in spans if s.name == "tool.invoke")
    assert roots[0].context.trace_id == roots[1].context.trace_id
    assert roots[0].parent is None and roots[1].parent is None
    assert child_span.parent.span_id == roots[0].context.span_id
    assert child_span.context.trace_id == roots[0].context.trace_id
    assert (
        next(s for s in spans if s.name == "mcp.http").parent.span_id
        == child_span.context.span_id
    )


def test_common_preserves_unsampled_parent(common):
    tracer, exporter = common
    with technical_span(
        "agent.http",
        context=extract_trace(
            {
                "traceparent": f"00-{'e' * 32}-{'f' * 16}-00",
            }
        ),
    ):
        agent = tracer.start_span("agent.stream", context=context())
        with activate_span(agent):
            assert trace.get_current_span().get_span_context().trace_id == int(
                "e" * 32, 16
            )
        child = tracer.start_span("v2.react.model", parent=agent)
        child.end()
        agent.end()
    tracer.provider.force_flush()
    assert not exporter.get_finished_spans()


@pytest.mark.parametrize(
    "backend, expected",
    [(TracerBackend.null, Tracer), (TracerBackend.logging, LoggingTracer)],
)
def test_disabled_keeps_configured_backend(monkeypatch, backend, expected):
    monkeypatch.delenv("FRED_OTEL_ENABLED", raising=False)
    assert type(_build_tracer(PodObservabilityConfig(tracer=backend))) is expected


def test_common_with_langfuse_config_uses_one_exporter(common, monkeypatch):
    _, exporter = common
    monkeypatch.setenv("FRED_OTEL_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    tracer = _build_tracer(PodObservabilityConfig(tracer=TracerBackend.langfuse))
    try:
        assert isinstance(tracer, module.OTLPTracer)
        span = tracer.start_span("agent.stream", context=context())
        span.end()
        tracer.provider.force_flush()
        assert len(exporter.get_finished_spans()) == 1
    finally:
        tracer.shutdown()


@pytest.mark.allow_hosts(["127.0.0.1"])
def test_unavailable_collector_does_not_fail_turn_or_unbound_shutdown(monkeypatch):
    # Reserve a local non-listening port: no real service can receive the spans.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            f"http://127.0.0.1:{reserved.getsockname()[1]}/v1/traces",
        )
        tracer = module.OTLPTracer()
        started = time.monotonic()
        span = tracer.start_span("agent.stream", context=context())
        span.end()
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
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        f"http://127.0.0.1:{server.server_port}/v1/traces",
    )
    tracer = module.OTLPTracer()
    try:
        tracer.start_span("agent.stream", context=context()).end()
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


def test_implicit_model_child_cannot_replace_business_trace_io(common):
    tracer, exporter = common
    tracer.observations._capture_content = True
    root = tracer.start_span("agent.stream", context=context())
    root.set_io(input="user question", output="agent answer")
    with activate_span(root):
        model = tracer.start_span("v2.graph.model", context=context())
        model.set_io(input="model prompt", output="model answer")
        model.end()
    root.end()
    tracer.provider.force_flush()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "langfuse.trace.input" not in spans["v2.graph.model"].attributes
    assert spans["agent.stream"].attributes["langfuse.trace.input"] == "user question"
