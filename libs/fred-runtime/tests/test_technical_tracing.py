# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Offline distributed context, stream lifetime and content-exclusion checks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

import httpx2
import pytest
from fred_core.portable.observability import Tracer, get_tracer, set_tracer
from fred_core.technical_tracing import (
    TechnicalTracer,
    activate_span,
    extract_trace,
    technical_span,
    trace_headers,
)
from fred_runtime.app.technical_tracing import OTLPTracer, TechnicalTracingMiddleware
from fred_runtime.common.mcp_tracing import TracedMCPClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.types import Message, Receive, Scope, Send


@pytest.fixture
def telemetry() -> Iterator[tuple[TechnicalTracer, InMemorySpanExporter]]:
    previous = get_tracer()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    adapter = TechnicalTracer(provider.get_tracer("test"))
    set_tracer(adapter)
    try:
        yield adapter, exporter
    finally:
        set_tracer(previous)
        provider.shutdown()


def test_runtime_parentage_and_content_exclusion(telemetry):
    adapter, exporter = telemetry
    parent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    with technical_span(
        "agent.http", context=extract_trace({"traceparent": parent})
    ) as server:
        agent = adapter.start_span("agent.stream", context={"token": "secret-sentinel"})
        model = adapter.start_span("v2.react.model", parent=agent)
        model.set_io(input="secret-sentinel", output="secret-sentinel")
        model.set_attribute("model_name", "secret-sentinel")
        model.set_attribute("status", "secret-sentinel")
        model.set_attribute("first_chunk_ms", 12.5)
        model.end()
        unknown = adapter.start_span("secret-sentinel")
        unknown.end()
        agent.end()
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert server.span_id is not None
    assert spans["agent.http"].parent.span_id == int("b" * 16, 16)
    assert spans["agent.stream"].parent.span_id == int(server.span_id, 16)
    assert spans["v2.react.model"].parent.span_id == int(agent.span_id, 16)
    assert {span.context.trace_id for span in spans.values()} == {int("a" * 32, 16)}
    assert spans["v2.react.model"].attributes["fred.category"] == "llm"
    assert spans["v2.react.model"].kind is trace.SpanKind.CLIENT
    assert spans["v2.react.model"].attributes["peer.service"] == "llm"
    assert spans["v2.react.model"].attributes["first_chunk_ms"] == 12.5
    assert not adapter.captures_content
    assert "secret-sentinel" not in "".join(span.to_json() for span in spans.values())


@pytest.mark.asyncio
async def test_two_streaming_turns_keep_parent_until_cleanup(telemetry):
    adapter, exporter = telemetry
    arrived = 0
    both_ready = asyncio.Event()
    injected: dict[int, str] = {}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal arrived
        await send({"type": "http.response.start", "status": 200, "headers": []})
        arrived += 1
        if arrived == 2:
            both_ready.set()
        await both_ready.wait()
        with technical_span("control_plane.runtime"):
            headers = trace_headers()
            trace_id = trace.get_current_span().get_span_context().trace_id
            injected[trace_id] = headers["traceparent"]
            assert set(headers) == {"traceparent"}
        await send(
            {
                "type": "http.response.body",
                "body": b"data: final\n\n",
                "more_body": False,
            }
        )
        # Cleanup and history are still inside the server span after the last body.
        with technical_span("history.write"):
            await asyncio.sleep(0)
            assert not any(
                s.name == "agent.http" and s.context.trace_id == trace_id
                for s in exporter.get_finished_spans()
            )

    async def run(digit: str) -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            pass

        parent = f"00-{digit * 32}-{'c' * 16}-01"
        await TechnicalTracingMiddleware(app)(
            {
                "type": "http",
                "headers": [
                    (b"traceparent", parent.encode()),
                    (b"baggage", b"token=secret-sentinel"),
                ],
            },
            receive,
            send,
        )

    await asyncio.gather(run("1"), run("2"))
    for digit in ("1", "2"):
        trace_id = int(digit * 32, 16)
        spans = [
            s for s in exporter.get_finished_spans() if s.context.trace_id == trace_id
        ]
        server = next(s for s in spans if s.name == "agent.http")
        assert len(spans) == 3
        assert all(
            s.parent.span_id == server.context.span_id for s in spans if s is not server
        )
        assert injected[trace_id].split("-")[1] == digit * 32
        assert all(s.end_time <= server.end_time for s in spans)
    assert not trace.get_current_span().get_span_context().is_valid


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect_at", ["streaming", "final_send", "after_body"])
@pytest.mark.parametrize("http_status", [200, 503])
async def test_disconnect_classification_tracks_response_completion(
    telemetry, disconnect_at, http_status
):
    _, exporter = telemetry
    receive_message = None

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal receive_message
        receive_message = receive
        await send(
            {"type": "http.response.start", "status": http_status, "headers": []}
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"data: partial\n\n",
                "more_body": True,
            }
        )
        if disconnect_at == "streaming":
            await receive()
            return
        # ASGI defaults more_body to false when omitted.
        await send({"type": "http.response.body", "body": b""})
        if disconnect_at == "after_body":
            await receive()
        # A late disconnect must not shorten the span's cleanup coverage.
        with technical_span("history.write"):
            assert not exporter.get_finished_spans()

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if (
            disconnect_at == "final_send"
            and message["type"] == "http.response.body"
            and not message.get("more_body", False)
        ):
            assert receive_message is not None
            await receive_message()
            await asyncio.sleep(0)

    await TechnicalTracingMiddleware(app)(
        {"type": "http", "headers": []}, receive, send
    )
    span = next(s for s in exporter.get_finished_spans() if s.name == "agent.http")
    expected = (
        "cancelled"
        if disconnect_at == "streaming"
        else "error"
        if http_status >= 400
        else None
    )
    assert span.attributes.get("fred.outcome") == expected
    assert span.attributes["http.response.status_code"] == http_status
    assert span.status.status_code == (
        trace.StatusCode.ERROR if expected else trace.StatusCode.UNSET
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_failed_final_send_is_not_response_completion(telemetry, failure):
    _, exporter = telemetry

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise failure("secret-sentinel")

    with pytest.raises(failure):
        await TechnicalTracingMiddleware(app)(
            {"type": "http", "headers": []}, receive, send
        )
    (span,) = exporter.get_finished_spans()
    assert span.attributes["fred.outcome"] == (
        "cancelled" if failure is asyncio.CancelledError else "error"
    )
    assert span.status.status_code == trace.StatusCode.ERROR
    assert "secret-sentinel" not in span.to_json()


@pytest.mark.asyncio
async def test_cancelled_sse_ends_span_without_exception_content(telemetry):
    _, exporter = telemetry

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise asyncio.CancelledError("secret-sentinel")

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        pass

    with pytest.raises(asyncio.CancelledError):
        await TechnicalTracingMiddleware(app)(
            {"type": "http", "headers": []}, receive, send
        )
    (span,) = exporter.get_finished_spans()
    assert span.attributes["fred.outcome"] == "cancelled"
    assert not span.events
    assert "secret-sentinel" not in span.to_json()
    assert not trace.get_current_span().get_span_context().is_valid


@pytest.mark.asyncio
async def test_mcp_transport_covers_body_and_parents_tool(telemetry, monkeypatch):
    adapter, exporter = telemetry
    headers: dict[str, str] = {}

    class Stream(httpx2.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"secret-sentinel"

    async def handle(self, request):
        headers.update(request.headers)
        return httpx2.Response(200, stream=Stream())

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle)
    with technical_span("agent.http"):
        tool = adapter.start_span("tool.invoke")
        with activate_span(tool):
            async with TracedMCPClient(trust_env=False) as client:
                response = await client.send(
                    httpx2.Request(
                        "POST",
                        "https://mcp.invalid/secret-sentinel",
                        headers={"Authorization": "secret-sentinel"},
                    ),
                    stream=True,
                )
                assert not any(
                    s.name == "mcp.http" for s in exporter.get_finished_spans()
                )
                assert await response.aread() == b"secret-sentinel"
                await response.aclose()
        tool.end()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    mcp = spans["mcp.http"]
    assert mcp.parent.span_id == int(tool.span_id, 16)
    assert headers["traceparent"].split("-")[2] == trace.format_span_id(
        mcp.context.span_id
    )
    assert spans["tool.invoke"].attributes["fred.category"] == "tool"
    assert mcp.attributes["fred.category"] == "mcp"
    assert mcp.attributes["peer.service"] == "mcp"
    assert "secret-sentinel" not in "".join(s.to_json() for s in spans.values())


def test_explicit_diagnostic_backend_ignores_environment(telemetry, monkeypatch):
    from fred_runtime.app import technical_tracing as module
    from fred_runtime.app.config import PodObservabilityConfig
    from fred_runtime.app.observability_factory import _build_tracer
    from fred_runtime.integrations.v2_runtime import adapters

    monkeypatch.setenv("OTEL_SERVICE_NAME", "fred-runtime")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "secret=secret-sentinel")
    monkeypatch.setattr(
        module, "OTLPSpanExporter", lambda **kwargs: InMemorySpanExporter()
    )
    tracer = _build_tracer(
        PodObservabilityConfig.model_validate(
            {
                "tracer": "diagnostic",
                "diagnostic": {"collector_endpoint": "http://127.0.0.1:4318/v1/traces"},
            }
        )
    )
    assert isinstance(tracer, OTLPTracer)
    try:
        assert dict(tracer.provider.resource.attributes) == {
            "service.name": "fred-agents"
        }
        set_tracer(tracer)
        monkeypatch.setattr(
            adapters,
            "build_langfuse_tracer",
            lambda: pytest.fail("Langfuse must not override explicit OTel"),
        )
        assert adapters.build_default_tracer() is tracer
    finally:
        tracer.shutdown()


def test_disabled_tracing_and_invalid_remote_context(telemetry):
    _, exporter = telemetry
    with technical_span(
        "agent.http", context=extract_trace({"traceparent": "secret-sentinel"})
    ):
        assert trace.get_current_span().get_span_context().is_valid
    previous = get_tracer()
    set_tracer(Tracer())
    try:
        with technical_span("history.write"):
            assert trace_headers() == {}
    finally:
        set_tracer(previous)
    (span,) = exporter.get_finished_spans()
    assert span.parent is None
    assert "secret-sentinel" not in json.dumps(span.attributes.copy())


def test_unsampled_parent_remains_unsampled(telemetry):
    _, exporter = telemetry
    parent = {"traceparent": f"00-{'7' * 32}-{'a' * 16}-00"}
    with technical_span("agent.http", context=extract_trace(parent)):
        with technical_span("control_plane.runtime"):
            assert trace_headers()["traceparent"].endswith("-00")
    assert not exporter.get_finished_spans()


@pytest.mark.asyncio
async def test_reused_mcp_transport_injects_current_turn(telemetry, monkeypatch):
    _, exporter = telemetry
    parents: list[str] = []

    async def handle(self, request):
        parents.append(request.headers["traceparent"])
        return httpx2.Response(204, stream=httpx2.ByteStream(b""))

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle)
    async with TracedMCPClient(trust_env=False) as client:
        for digit in ("3", "4"):
            carrier = {"traceparent": f"00-{digit * 32}-{'a' * 16}-01"}
            with technical_span("agent.http", context=extract_trace(carrier)):
                response = await client.send(
                    httpx2.Request("POST", "https://mcp.invalid"), stream=True
                )
                await response.aclose()
    assert [parent.split("-")[1] for parent in parents] == ["3" * 32, "4" * 32]
    assert len([s for s in exporter.get_finished_spans() if s.name == "mcp.http"]) == 2


@pytest.mark.asyncio
async def test_mcp_factory_preserves_environment_proxy_and_no_proxy(
    telemetry, monkeypatch
):
    from fred_runtime.common.mcp_utils import _mcp_http_client_factory

    adapter, exporter = telemetry
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", "direct.invalid")
    set_tracer(Tracer())
    try:
        baseline = _mcp_http_client_factory(timeout=httpx2.Timeout(5))
    finally:
        set_tracer(adapter)
    seen: list[tuple[str, str]] = []

    async def handle(self, request):
        seen.append((type(self._pool).__name__, request.headers["traceparent"]))
        return httpx2.Response(204, stream=httpx2.ByteStream(b""))

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle)
    async with baseline, _mcp_http_client_factory(timeout=httpx2.Timeout(5)) as traced:
        assert isinstance(traced, TracedMCPClient)
        for url, pool_type in (
            ("https://mcp.invalid", "AsyncHTTPProxy"),
            ("http://mcp.invalid", "AsyncHTTPProxy"),
            ("https://direct.invalid", "AsyncConnectionPool"),
        ):
            original_pool = getattr(
                baseline._transport_for_url(httpx2.URL(url)), "_pool"
            )
            traced_pool = getattr(traced._transport_for_url(httpx2.URL(url)), "_pool")
            assert (
                type(original_pool).__name__ == type(traced_pool).__name__ == pool_type
            )
            assert original_pool._max_connections == traced_pool._max_connections
            assert (
                original_pool._max_keepalive_connections
                == traced_pool._max_keepalive_connections
            )
            assert (
                original_pool._ssl_context.verify_mode
                == traced_pool._ssl_context.verify_mode
            )
        for digit in ("8", "9"):
            carrier = {"traceparent": f"00-{digit * 32}-{'a' * 16}-01"}
            with technical_span("agent.http", context=extract_trace(carrier)):
                await traced.post("https://mcp.invalid")
                await traced.post("https://direct.invalid")
    assert [pool for pool, _ in seen] == ["AsyncHTTPProxy", "AsyncConnectionPool"] * 2
    assert [parent.split("-")[1] for _, parent in seen] == ["8" * 32] * 2 + [
        "9" * 32
    ] * 2
    assert len([s for s in exporter.get_finished_spans() if s.name == "mcp.http"]) == 4


@pytest.mark.asyncio
async def test_graph_observe_parents_mcp_and_records_cancellation(
    telemetry, monkeypatch
):
    from fred_runtime.graph.node_context import NodeContext, _observe
    from fred_sdk.contracts.context import (
        BoundRuntimeContext,
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
    )
    from fred_sdk.contracts.runtime import RuntimeServices

    adapter, exporter = telemetry
    context = NodeContext(
        binding=BoundRuntimeContext(
            runtime_context=RuntimeContext(),
            portable_context=PortableContext(
                request_id="test",
                correlation_id="test",
                actor="test",
                tenant="test",
                environment=PortableEnvironment.DEV,
            ),
        ),
        services=RuntimeServices(tracer=adapter),
        model=None,
        graph_agent_id="graph",
        node_id="node",
        allowed_tool_refs=frozenset(),
        runtime_tools={},
        tuning_values={},
        sink=lambda event: None,
    )

    async def handle(self, request):
        return httpx2.Response(204, stream=httpx2.ByteStream(b""))

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", handle)
    with technical_span("agent.http"):
        async with TracedMCPClient(trust_env=False) as client:
            with _observe(context, "v2.graph.runtime_tool", {}):
                await client.post("https://mcp.invalid")
            with pytest.raises(asyncio.CancelledError):
                with _observe(context, "v2.graph.runtime_tool", {}):
                    raise asyncio.CancelledError("secret-sentinel")
    spans = exporter.get_finished_spans()
    tools = [s for s in spans if s.name == "v2.graph.runtime_tool"]
    mcp = next(s for s in spans if s.name == "mcp.http")
    assert mcp.parent.span_id == tools[0].context.span_id
    assert tools[1].attributes["fred.outcome"] == "cancelled"
    assert tools[1].status.status_code is trace.StatusCode.ERROR
    assert "secret-sentinel" not in "".join(s.to_json() for s in spans)
    assert not trace.get_current_span().get_span_context().is_valid


@pytest.mark.asyncio
async def test_m2m_network_observer_does_not_label_cache_as_network(
    telemetry, monkeypatch
):
    import httpx
    from fred_core.security.auth_metrics import observe_m2m
    from fred_pod.security import backend_to_backend_auth as auth

    _, exporter = telemetry
    monkeypatch.setattr(auth, "_token_observer", observe_m2m)
    monkeypatch.setenv("OTEL_TEST_SECRET", "secret-sentinel")
    calls = 0

    async def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"access_token": "secret-sentinel", "expires_in": 300}
        )

    provider = auth.M2MTokenProvider(
        auth.M2MAuthConfig(
            keycloak_realm_url="https://iam.invalid/realms/test",
            client_id="test",
            secret_env="OTEL_TEST_SECRET",
        ),
        transport=httpx.MockTransport(respond),
    )
    for digit in ("5", "6"):
        carrier = {"traceparent": f"00-{digit * 32}-{'a' * 16}-01"}
        with technical_span("agent.http", context=extract_trace(carrier)):
            assert await provider.get_token() == "secret-sentinel"
    spans = exporter.get_finished_spans()
    network = [s for s in spans if s.name == "iam.token.initial"]
    assert calls == len(network) == 1
    assert network[0].context.trace_id == int("5" * 32, 16)
    assert len([s for s in spans if s.name == "auth.m2m.acquire"]) == 2
    assert "secret-sentinel" not in "".join(s.to_json() for s in spans)


def test_jwks_fetch_and_local_jwt_rejection_are_distinct(telemetry, monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException
    from fred_core.security import oidc
    from jwt import PyJWKClient

    _, exporter = telemetry
    monkeypatch.setattr(PyJWKClient, "fetch_data", lambda self: {"keys": []})
    with technical_span("agent.http"):
        assert oidc._ObservedJWKClient("https://iam.invalid/jwks").fetch_data() == {
            "keys": []
        }
        monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
        monkeypatch.setattr(oidc, "JWT_CACHE_ENABLED", False)
        monkeypatch.setattr(
            oidc,
            "_get_jwks_client",
            lambda: SimpleNamespace(
                get_signing_key_from_jwt=lambda token: SimpleNamespace(key="test-key")
            ),
        )
        with pytest.raises(HTTPException):
            oidc.decode_jwt("secret-sentinel")
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["iam.jwks.http"].attributes["fred.category"] == "keycloak"
    assert spans["auth.jwt.verify"].attributes["fred.category"] == "auth"
    assert spans["auth.jwt.verify"].status.status_code is trace.StatusCode.ERROR
    assert "secret-sentinel" not in "".join(s.to_json() for s in spans.values())
