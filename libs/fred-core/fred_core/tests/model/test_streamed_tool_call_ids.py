# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from contextlib import aclosing, closing
from typing import cast

import httpx
import pytest
from fred_core.common import ModelConfiguration
from fred_core.model import http_clients
from fred_core.model.factory import get_model
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from openai import _base_client as openai_client


def _event(delta: dict[str, object], finish_reason: str | None = None) -> bytes:
    chunk = {
        "id": "test-completion",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"


def _call(index: int, arguments: str, **fields: str) -> dict[str, object]:
    name = fields.pop("name", None)
    function = {"arguments": arguments}
    if name is not None:
        function["name"] = name
    return {"index": index, "function": function, **fields}


def _tool_event(*calls: dict[str, object]) -> bytes:
    return _event({"tool_calls": calls})


_ROUND_56 = (
    _tool_event(_call(0, "", id="call_first", name="lookup", type="function")),
    _tool_event(_call(0, '{"city":"', id="null", name="")),
    _tool_event(_call(0, "Évry", id="null")),
    _tool_event(_call(0, '"}')),
    _event({}, "tool_calls"),
    b"data: [DONE]\n\n",
)


class _WireStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, parts: tuple[bytes, ...]) -> None:
        self.parts = parts
        self.reads = 0
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for part in self.parts:
            self.reads += 1
            yield part

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for part in self:
            yield part

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.close()


class _Upstream(httpx.MockTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.parts: tuple[bytes, ...] = _ROUND_56
        self.status = 200
        self.content_type = "text/event-stream"
        self.headers: dict[str, str] = {}
        self.stream_factory = _WireStream
        self.streams: list[_WireStream] = []
        super().__init__(self.respond)

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        payload = json.loads(request.content)
        if payload["messages"][-1]["role"] == "tool":
            parts = (_event({"content": "Found it."}, "stop"), _ROUND_56[-1])
        elif payload.get("model") == "literal-id-model":
            parts = tuple(part.replace(b"call_first", b"null") for part in _ROUND_56)
        else:
            parts = self.parts
        stream = self.stream_factory(parts)
        self.streams.append(stream)
        return httpx.Response(
            self.status,
            headers={
                "content-type": self.content_type,
                "x-request-id": "test-id",
                **self.headers,
            },
            stream=stream,
        )


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Upstream]:
    transport = _Upstream()
    monkeypatch.setattr(openai_client, "get_platform", lambda: "Linux")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: transport)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: transport)
    for key in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.upper(), raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(http_clients, "_SHARED_TUNING", None)
    monkeypatch.setattr(http_clients, "_SYNC_CLIENT", None)
    monkeypatch.setattr(http_clients, "_ASYNC_CLIENT", None)
    try:
        yield transport
    finally:
        http_clients.shutdown_shared_clients()


def _model(name: str = "mistral-medium-test", **settings: object) -> ChatOpenAI:
    return cast(
        ChatOpenAI,
        get_model(
            ModelConfiguration(
                provider="openai",
                name=name,
                settings={"base_url": "https://gateway.example/v1", **settings},
            )
        ),
    )


def _assert_repaired(chunk: AIMessageChunk) -> None:
    assert chunk.tool_calls == [
        {
            "name": "lookup",
            "args": {"city": "Évry"},
            "id": "call_first",
            "type": "tool_call",
        }
    ]
    assert chunk.invalid_tool_calls == []


def test_factory_stream_repairs_continuation_and_pairs_tool_result(
    upstream: _Upstream,
) -> None:
    model = _model()
    message = HumanMessage(content="Look up Évry.")
    with closing(cast(Generator[AIMessageChunk], model.stream([message]))) as stream:
        chunk = next(stream)
        assert upstream.streams[-1].reads == 1
        for part in stream:
            chunk += part
    _assert_repaired(cast(AIMessageChunk, chunk))
    result = ToolMessage(content="Done", tool_call_id="call_first")
    assert (
        "".join(str(part.content) for part in model.stream([message, chunk, result]))
        == "Found it."
    )
    history = json.loads(upstream.requests[-1].content)["messages"]
    assert (
        history[-2]["tool_calls"][0]["id"]
        == history[-1]["tool_call_id"]
        == "call_first"
    )


@pytest.mark.asyncio
async def test_factory_astream_interleaves_calls_and_pairs_tool_results(
    upstream: _Upstream,
) -> None:
    model = _model("unclassified-wire-alias")
    upstream.parts = (
        _tool_event(
            _call(0, "", id="call_first", name="lookup", type="function"),
            _call(1, "", id="call_second", name="count", type="function"),
        ),
        _tool_event(_call(0, '{"city":"Év', id="null")),
        _tool_event(_call(1, '{"text":"null"}', id="null", name="")),
        _tool_event(_call(0, 'ry"}')),
        *_ROUND_56[-2:],
    )
    # Split CRLF delimiters and the UTF-8 city name across network reads.
    upstream.parts = tuple(
        bytes((byte,))
        for part in upstream.parts
        for byte in part.replace(b"\n", b"\r\n")
    )
    message = HumanMessage(content="Look up and count.")
    async with aclosing(
        cast(AsyncGenerator[AIMessageChunk], model.astream([message]))
    ) as stream:
        chunk = await anext(stream)
        assert upstream.streams[-1].reads < len(upstream.parts)
        async for part in stream:
            chunk += part
    repaired = cast(AIMessageChunk, chunk)
    assert repaired.invalid_tool_calls == []
    assert [
        (call["id"], call["name"], call["args"]) for call in repaired.tool_calls
    ] == [
        ("call_first", "lookup", {"city": "Évry"}),
        ("call_second", "count", {"text": "null"}),
    ]
    results = [
        ToolMessage(content="Done", tool_call_id=call_id)
        for call_id in ("call_first", "call_second")
    ]
    assert [
        part.content
        async for part in model.astream([message, chunk, *results])
        if part.content
    ] == ["Found it."]
    history = json.loads(upstream.requests[-1].content)["messages"]
    assert [call["id"] for call in history[-3]["tool_calls"]] == [
        result["tool_call_id"] for result in history[-2:]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("opt_out_first", [True, False])
async def test_shared_pool_keeps_concurrent_response_state_and_opt_out_local(
    upstream: _Upstream, opt_out_first: bool
) -> None:
    if opt_out_first:
        disabled = _model(
            normalize_streamed_tool_call_ids=False, default_headers={"X-Test": "keep"}
        )
        enabled = _model()
    else:
        enabled = _model()
        disabled = _model(
            normalize_streamed_tool_call_ids=False, default_headers={"X-Test": "keep"}
        )
    literal = _model("literal-id-model")
    assert disabled.http_client is enabled.http_client is literal.http_client
    assert (
        disabled.http_async_client
        is enabled.http_async_client
        is literal.http_async_client
    )

    async def consume(model: ChatOpenAI) -> AIMessageChunk:
        async with aclosing(
            cast(AsyncGenerator[AIMessageChunk], model.astream("Look up Évry."))
        ) as stream:
            chunk = await anext(stream)
            await asyncio.sleep(0)
            async for part in stream:
                chunk += part
        return cast(AIMessageChunk, chunk)

    repaired, unchanged, valid_literal = await asyncio.wait_for(
        asyncio.gather(consume(enabled), consume(disabled), consume(literal)), timeout=3
    )
    _assert_repaired(repaired)
    assert [call["id"] for call in unchanged.tool_calls] == ["null"]
    assert [call["id"] for call in unchanged.invalid_tool_calls] == ["call_first"]
    assert valid_literal.invalid_tool_calls == []
    assert valid_literal.tool_calls[0]["id"] == "null"
    assert valid_literal.tool_calls[0]["args"] == {"city": "Évry"}
    assert all(
        "x-fred-skip-tool-call-id-normalization" not in request.headers
        for request in upstream.requests
    )
    assert [request.headers.get("x-test") for request in upstream.requests].count(
        "keep"
    ) == 1
    assert all(stream.closed for stream in upstream.streams)


def test_factory_stream_early_close_releases_upstream(upstream: _Upstream) -> None:
    with closing(
        cast(Generator[AIMessageChunk], _model().stream("Look up Évry."))
    ) as stream:
        next(stream)
        assert not upstream.streams[-1].closed
    assert upstream.streams[-1].closed


@pytest.mark.asyncio
async def test_factory_astream_cancel_releases_upstream(upstream: _Upstream) -> None:
    stalled = asyncio.Event()

    class StalledStream(_WireStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield self.parts[0]
            stalled.set()
            await asyncio.Future()

    upstream.stream_factory = StalledStream
    model = _model()

    async def consume() -> None:
        async with aclosing(
            cast(AsyncGenerator[AIMessageChunk], model.astream("Look up Évry."))
        ) as stream:
            async for _ in stream:
                pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(stalled.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert upstream.streams[-1].closed


@pytest.mark.parametrize(
    "path,status,content_type",
    [
        ("/v1/chat/completions", 400, "text/event-stream"),
        ("/v1/chat/completions", 200, "application/json"),
        ("/v1/responses", 200, "text/event-stream"),
        ("/v1/embeddings", 200, "text/event-stream"),
    ],
)
def test_shared_transport_passes_other_responses_through(
    upstream: _Upstream, path: str, status: int, content_type: str
) -> None:
    model = _model()
    assert model.http_client is not None
    upstream.status = status
    upstream.content_type = content_type
    response = model.http_client.post(
        f"https://gateway.example{path}", json={"messages": [{"role": "user"}]}
    )
    assert response.status_code == status
    assert response.headers["content-type"] == content_type
    assert response.content == b"".join(_ROUND_56)


def test_shared_transport_decodes_compressed_sse_and_keeps_metadata(
    upstream: _Upstream,
) -> None:
    upstream.parts = (gzip.compress(b"".join(_ROUND_56)),)
    upstream.headers = {
        "content-encoding": "gzip",
        "content-length": str(len(upstream.parts[0])),
    }
    model = _model(request_timeout=7, timeout={"pool": 5})
    assert model.http_client is not None
    with model.http_client.stream(
        "POST",
        "https://gateway.example/v1/chat/completions",
        json={"messages": [{"role": "user"}]},
    ) as response:
        assert "content-encoding" not in response.headers
        assert "content-length" not in response.headers
        assert response.headers["x-request-id"] == "test-id"
        assert b'"id":null' in response.read()
    _assert_repaired(
        cast(
            AIMessageChunk,
            sum(_model().stream("Look up Évry."), AIMessageChunk(content="")),
        )
    )
    assert upstream.requests[0].extensions["timeout"]["pool"] == 5
    assert upstream.requests[1].extensions["timeout"]["pool"] == 5
    with closing(
        cast(Generator[AIMessageChunk], model.stream("Look up Évry."))
    ) as stream:
        next(stream)
    assert upstream.requests[-1].extensions["timeout"]["pool"] == 7


def test_shared_transport_forwards_oversized_frame_and_resumes(
    upstream: _Upstream,
) -> None:
    large = _event({"content": "x" * (300 * 1024)})
    upstream.parts = (
        *_ROUND_56[:1],
        large[:100],
        large[100:-1],
        large[-1:],
        *_ROUND_56[1:],
        *_ROUND_56,
    )
    model = _model()
    assert model.http_client is not None
    body = model.http_client.post(
        "https://gateway.example/v1/chat/completions",
        json={"messages": [{"role": "user"}]},
    ).content
    prefix = _ROUND_56[0] + large + b"".join(_ROUND_56[1:])
    assert body.startswith(prefix)
    assert body[len(prefix) :].count(b'"id":null') == 2


@pytest.mark.asyncio
async def test_environment_proxy_and_no_proxy_mounts_normalize_sse(
    upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes: list[tuple[str, str | None]] = []

    def transport(proxy: str | None = None, **kwargs: object) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            routes.append((request.url.host, proxy))
            return upstream.respond(request)

        return httpx.MockTransport(handle)

    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", ".internal.example,localhost,127.0.0.1,::1")
    direct = _model(base_url="https://llm.internal.example/v1")
    proxied = _model()
    _assert_repaired(sum(direct.stream("Look up Évry."), AIMessageChunk(content="")))
    _assert_repaired(
        sum(
            [part async for part in proxied.astream("Look up Évry.")],
            AIMessageChunk(content=""),
        )
    )
    assert routes == [
        ("llm.internal.example", None),
        ("gateway.example", "http://proxy.example:8080"),
    ]


def test_mixed_multiline_sse_preserves_event_delimiters(upstream: _Upstream) -> None:
    multiline = _ROUND_56[1].replace(b'"delta": {', b'"delta":\rdata: {', 1)
    upstream.parts = (_ROUND_56[0], multiline, *_ROUND_56[2:])
    _assert_repaired(sum(_model().stream("Look up Évry."), AIMessageChunk(content="")))


@pytest.mark.asyncio
async def test_astream_drains_http11_after_done_for_connection_reuse(
    upstream: _Upstream,
) -> None:
    upstream.parts = (*_ROUND_56, b": trailing comment\n\n")
    chunks = [part async for part in _model().astream("Look up Évry.")]
    _assert_repaired(sum(chunks, AIMessageChunk(content="")))
    assert upstream.streams[-1].reads == len(upstream.parts)
    assert upstream.streams[-1].closed
