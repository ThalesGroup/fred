# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import asyncio
import gzip
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import httpx2
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_model
from fred_core.model.http_capture import HttpRequest, HttpResponse, active_http_capture
from google.auth.credentials import Credentials
from langchain_google_genai import ChatGoogleGenerativeAI

_MESSAGE = "A message to capture"
_ERROR = b"literal provider error"
_GEMINI = b'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]}}]}\r\n\r\n'
_MAAS = b'data: {"choices":[{"delta":{"role":"assistant","content":"ok"}}]}\r\n\r\ndata: [DONE]\r\n\r\n'
_NDJSON = (
    b'{"model":"fake","message":{"role":"assistant","content":"ok"},"done":true}\r\n'
)
_ANTHROPIC = (
    b'event: message_start\r\ndata: {"type":"message_start","message":{"id":"msg_mock","type":"message","role":"assistant","model":"fake","content":[],"stop_reason":null,"usage":{"input_tokens":1,"output_tokens":0}}}\r\n\r\n'
    b'event: content_block_start\r\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":"ok"}}\r\n\r\n'
    b'event: content_block_stop\r\ndata: {"type":"content_block_stop","index":0}\r\n\r\n'
    b'event: message_stop\r\ndata: {"type":"message_stop"}\r\n\r\n'
)


class _Credentials(Credentials):
    def __init__(self) -> None:
        super().__init__()
        self.refreshes = 0

    def refresh(self, request: Any) -> None:
        self.refreshes += 1
        self.token = f"test-token-{self.refreshes}"


@dataclass
class _Attempt:
    request: HttpRequest
    response: HttpResponse | None = None
    body: bytearray = field(default_factory=bytearray)
    frames: bytearray = field(default_factory=bytearray)
    completion: bool | None = None
    error: Exception | None = None
    normalizing: bool | None = None
    sse_finished: bool = False

    @property
    def remaining_budget(self) -> int:
        return 8192 - len(self.body)

    def headers(self, response: HttpResponse) -> None:
        self.response = response

    def chunk(self, data: bytes) -> None:
        self.body.extend(data)

    def finish(
        self,
        *,
        body_complete: bool,
        failed: bool = False,
        error: Exception | None = None,
    ) -> None:
        if self.completion is None:
            self.completion = body_complete
            self.error = error

    def sse_chunk(self, data: bytes) -> None:
        if (
            self.response
            and self.response.headers["content-type"] == "text/event-stream"
        ):
            self.frames.extend(data)

    def finish_sse(self, error: Exception | None = None) -> None:
        self.sse_finished = True

    def normalization_started(self, *, enabled: bool) -> None:
        self.normalizing = enabled

    def normalization_rewrites(
        self, frame_index: int, changes: list[tuple[int, int, str]]
    ) -> None:
        raise AssertionError("SDK-owned providers do not use Fred's normalizer")


@dataclass
class _Capture:
    attempts: list[_Attempt] = field(default_factory=list)

    def begin(self, request: HttpRequest) -> _Attempt:
        attempt = _Attempt(request)
        self.attempts.append(attempt)
        return attempt


@pytest.fixture
def capture() -> Iterator[_Capture]:
    capture = _Capture()
    token = active_http_capture.set(capture)
    try:
        yield capture
    finally:
        active_http_capture.reset(token)


class _Body(
    httpx.AsyncByteStream,
    httpx.SyncByteStream,
    httpx2.AsyncByteStream,
    httpx2.SyncByteStream,
):
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self) -> Iterator[bytes]:
        yield self.data[:13]
        yield self.data[13:]

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self:
            yield chunk


@pytest.mark.parametrize(
    ("provider", "name", "family", "body", "content_type", "auth_header"),
    [
        (
            "anthropic",
            "claude-sonnet-4-5",
            None,
            _ANTHROPIC,
            "text/event-stream",
            "x-api-key",
        ),
        (
            "vertex-ai-model-garden",
            "claude-sonnet-4-5",
            "anthropic",
            _ANTHROPIC,
            "text/event-stream",
            "authorization",
        ),
        (
            "vertex-ai-model-garden",
            "mistral-small-2503",
            "mistral",
            _MAAS,
            "text/event-stream",
            "authorization",
        ),
        (
            "vertex-ai-model-garden",
            "meta/llama-3.3-70b-instruct-maas",
            "llama",
            _MAAS,
            "text/event-stream",
            "authorization",
        ),
        ("ollama", "fake", None, _NDJSON, "application/x-ndjson", "authorization"),
        (
            "vertex-ai",
            "gemini-2.5-flash",
            None,
            _GEMINI,
            "text/event-stream",
            "authorization",
        ),
    ],
    ids=[
        "anthropic",
        "vertex-anthropic",
        "vertex-mistral",
        "vertex-llama",
        "ollama",
        "gemini-httpx",
    ],
)
@pytest.mark.asyncio
async def test_sdk_owned_httpx_streams(
    monkeypatch: pytest.MonkeyPatch,
    capture: _Capture,
    provider: str,
    name: str,
    family: str | None,
    body: bytes,
    content_type: str,
    auth_header: str,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-native-key")
    credentials = _Credentials()
    settings: dict[str, Any] = {}
    if provider.startswith("vertex-ai"):
        settings.update(
            project="fixture-project", location="us-central1", credentials=credentials
        )
    if family is not None:
        settings["model_family"] = family
    if family == "anthropic":
        # The pinned Anthropic Messages API rejects legacy sampling keywords.
        settings.update(access_token="mock-vertex-anthropic-token", temperature=None)
    elif provider == "ollama":
        settings["base_url"] = "http://local-user:local-password@127.0.0.1:11434"
    elif provider == "vertex-ai":
        # This SDK setting selects its HTTPX fallback even when aiohttp is installed.
        settings["client_args"] = {
            "transport": httpx.MockTransport(lambda _: httpx.Response(599))
        }

    backend: Any = httpx2 if provider == "anthropic" or family == "anthropic" else httpx
    wire_body = gzip.compress(body)
    requests: list[HttpRequest] = []

    def handler(request: HttpRequest) -> HttpResponse:
        requests.append(request)
        return backend.Response(
            200,
            headers={
                "Content-Type": content_type,
                "Content-Encoding": "gzip",
                "X-Request-Id": "upstream-123",
            },
            stream=_Body(wire_body),
        )

    transport = backend.MockTransport(handler)
    monkeypatch.setattr(backend.AsyncClient, "_transport_for_url", lambda *_: transport)
    model = get_model(
        ModelConfiguration(provider=provider, name=name, settings=settings)
    )
    if family in {"mistral", "llama"}:
        credentials.token = ""  # The original static token is now expired.
    try:
        async with asyncio.timeout(5):
            chunks = [chunk async for chunk in model.astream(_MESSAGE)]
        assert chunks
        assert len(requests) == 1
        (attempt,) = capture.attempts
        request = requests[0]
        assert attempt.request.content == request.content
        assert _MESSAGE in request.content.decode()
        assert request.headers[auth_header]
        if family in {"mistral", "llama"}:
            assert (
                request.headers[auth_header]
                == f"Bearer test-token-{credentials.refreshes}"
            )
            assert credentials.refreshes >= 2
        if family == "anthropic":
            assert request.headers[auth_header] == "Bearer mock-vertex-anthropic-token"
        assert attempt.response is not None
        assert attempt.response.headers["x-request-id"] == "upstream-123"
        assert attempt.body == wire_body
        # These SDKs return at [DONE] without reading the transport to EOF.
        assert attempt.completion is (family not in {"mistral", "llama"})
        assert attempt.frames == (body if content_type == "text/event-stream" else b"")
        assert attempt.normalizing is (False if attempt.frames else None)
        assert attempt.sse_finished == bool(attempt.frames)
    finally:
        if isinstance(model, ChatGoogleGenerativeAI):
            await model.aclose()


@pytest.mark.parametrize("failed_to_connect", [False, True])
@pytest.mark.asyncio
async def test_native_anthropic_early_failure(
    monkeypatch: pytest.MonkeyPatch, capture: _Capture, failed_to_connect: bool
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-native-key")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if failed_to_connect:
            raise httpx2.ConnectError("mock connection failure", request=request)
        return httpx2.Response(
            400, headers={"Content-Type": "text/plain"}, stream=_Body(_ERROR)
        )

    transport = httpx2.MockTransport(handler)
    monkeypatch.setattr(httpx2.AsyncClient, "_transport_for_url", lambda *_: transport)
    model = get_model(
        ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5")
    )
    from anthropic import APIConnectionError, BadRequestError

    with pytest.raises(APIConnectionError if failed_to_connect else BadRequestError):
        async for _ in model.astream(_MESSAGE):
            pytest.fail("a provider failure must not produce an answer")
    (attempt,) = capture.attempts
    assert _MESSAGE in attempt.request.content.decode()
    assert attempt.body == (b"" if failed_to_connect else _ERROR)
    if failed_to_connect:
        assert isinstance(attempt.error, httpx2.ConnectError)
    else:
        assert attempt.response is not None and attempt.response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vertex_gemini_sdk_owned_aiohttp(
    capture: _Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langchain_google_genai.chat_models import GoogleInvalidRequestError

    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    sent: list[bytes] = []
    seen_auth: list[str] = []
    responses: list[tuple[int, bytes]] = [
        (200, _GEMINI),
        (400, _ERROR),
        (400, b""),
        (200, _GEMINI),
    ]

    async def handle(request: web.Request) -> web.StreamResponse:
        seen_auth.append(request.headers["Authorization"])
        sent.append(await request.read())
        status, body = responses.pop(0)
        if status == 400:
            return web.Response(
                status=status,
                body=body,
                headers={"X-Goog-Request-Id": "upstream-400"},
                content_type="text/plain",
            )
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "X-Goog-Request-Id": "upstream-200",
            }
        )
        await response.prepare(request)
        await response.write(body[:15])
        await response.write(body[15:])
        return response

    app = web.Application()
    app.router.add_post("/{tail:.*}", handle)
    async with TestServer(app) as server:
        model = get_model(
            ModelConfiguration(
                provider="vertex-ai",
                name="gemini-2.5-flash",
                settings={
                    "project": "fixture-project",
                    "location": "us-central1",
                    "base_url": str(server.make_url("/")),
                    "credentials": _Credentials(),
                },
            )
        )
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert model.client is not None
        assert model.client._api_client._use_aiohttp()
        try:
            chunks = [chunk async for chunk in model.astream(_MESSAGE)]
            assert "ok" in [chunk.content for chunk in chunks]
            for _ in range(2):
                with pytest.raises(GoogleInvalidRequestError):
                    async for _ in model.astream(_MESSAGE):
                        pytest.fail("a provider failure must not produce an answer")
            token = active_http_capture.set(None)
            try:
                assert [chunk async for chunk in model.astream(_MESSAGE)]
            finally:
                active_http_capture.reset(token)
        finally:
            await model.aclose()

    assert seen_auth == ["Bearer test-token-1"] * 4
    assert len(capture.attempts) == 3
    assert [attempt.request.content for attempt in capture.attempts] == sent[:3]
    assert all(attempt.completion for attempt in capture.attempts)
    assert all(attempt.response is not None for attempt in capture.attempts)
    success, error, empty = capture.attempts
    assert success.body == success.frames == _GEMINI
    assert error.body == _ERROR and error.frames == b""
    assert empty.body == empty.frames == b""
    assert success.response is not None and success.response.status_code == 200
    assert (
        error.response is not None
        and error.response.headers["x-goog-request-id"] == "upstream-400"
    )
    assert empty.response is not None and empty.response.status_code == 400
