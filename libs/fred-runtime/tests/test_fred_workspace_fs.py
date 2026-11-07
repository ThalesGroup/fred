# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The workspace port transports admitted context, conditional writes and preview identity."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fred_runtime.common.outbound_credentials import (
    OutboundCredentialProvider,
    OutboundCredentials,
)
from fred_runtime.integrations.v2_runtime import adapters
from fred_runtime.integrations.v2_runtime.adapters import FredWorkspaceFs
from fred_sdk.contracts.context import BoundRuntimeContext


@pytest_asyncio.fixture
async def workspace(monkeypatch):
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"current_content_id": "before"})
        return httpx.Response(200, json={"document_id": "file", "content_id": "after"})

    provider = cast(
        OutboundCredentialProvider,
        SimpleNamespace(
            credentials=AsyncMock(
                return_value=OutboundCredentials(
                    authorization="Bearer fixture",
                    delegated=True,
                    parameters={
                        "person": "alice",
                        "run": "admitted-run",
                        "agent": "instance",
                    },
                )
            )
        ),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        config = SimpleNamespace(
            control_plane_url="http://control-plane-backend:8222/control-plane/v1",
            control_plane_http_client=client,
        )
        monkeypatch.setattr(
            adapters, "get_runtime_context", lambda: SimpleNamespace(config=config)
        )
        writer = FredWorkspaceFs(
            binding=cast(
                BoundRuntimeContext,
                SimpleNamespace(
                    runtime_context=SimpleNamespace(
                        session_id="conversation", space_id="space"
                    )
                ),
            ),
            credentials=provider,
        )
        yield writer, requests


@pytest.mark.asyncio
async def test_workspace_snapshots_before_write_and_returns_catalogue_identity(
    workspace,
):
    writer, requests = workspace
    expected = await writer.snapshot("outputs/conversation/deck.pptx")
    artifact = await writer.write(
        "outputs/conversation/deck.pptx", b"\x00\xff", expected_content_id=expected
    )
    assert requests[0].url.path.endswith("/files/write-target")
    assert requests[1].url.host == "control-plane-backend"
    assert requests[1].url.params["expected_content_id"] == "before"
    assert requests[1].url.params["person"] == "alice"
    assert requests[1].url.params["run"] == "admitted-run"
    assert requests[1].url.params["agent"] == "instance"
    assert requests[1].headers["authorization"] == "Bearer fixture"
    assert requests[1].headers["idempotency-key"]
    assert b"\x00\xff" in requests[1].content
    assert artifact.document_uid == artifact.key == "file"
    assert artifact.content_id == "after"
    assert (
        artifact.href
        == "/control-plane/v1/spaces/space/sessions/conversation/files/file/content"
    )
    assert artifact.size == 2


@pytest.mark.asyncio
async def test_lost_response_replays_the_same_attempt(workspace, monkeypatch):
    writer, requests = workspace
    client = adapters.get_runtime_context().config.control_plane_http_client
    assert client is not None
    send = client.send
    calls = 0

    async def lose_first_response(*args, **kwargs):
        nonlocal calls
        response = await send(*args, **kwargs)
        calls += 1
        if calls == 1:
            raise httpx.ReadError("response lost", request=response.request)
        return response

    monkeypatch.setattr(client, "send", lose_first_response)
    key = "9e911123-1b42-434c-8421-22f9f72c3bc2"
    for _ in range(2):
        artifact = await writer.write(
            "outputs/conversation/deck.pptx",
            b"deck bytes",
            expected_content_id="before",
            request_key=key,
        )
        assert artifact.content_id == "after"
    assert len(requests) == 3
    for request in requests:
        assert request.method == "POST"
        assert request.headers["idempotency-key"] == key
        assert request.url.params["expected_content_id"] == "before"
        assert b"deck bytes" in request.content


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [409, 422, 503])
async def test_business_failure_is_not_retried(workspace, monkeypatch, status):
    writer, requests = workspace
    client = adapters.get_runtime_context().config.control_plane_http_client
    assert client is not None
    send = client.send

    async def fail(*args, **kwargs):
        response = await send(*args, **kwargs)
        return httpx.Response(status, request=response.request)

    monkeypatch.setattr(client, "send", fail)
    with pytest.raises(httpx.HTTPStatusError):
        await writer.write(
            "outputs/conversation/deck.pptx", b"deck", expected_content_id=None
        )
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_transport_replay_is_bounded(workspace, monkeypatch):
    writer, requests = workspace
    client = adapters.get_runtime_context().config.control_plane_http_client
    assert client is not None
    send = client.send

    async def fail(*args, **kwargs):
        response = await send(*args, **kwargs)
        raise httpx.ReadError("response lost", request=response.request)

    monkeypatch.setattr(client, "send", fail)
    with pytest.raises(httpx.ReadError):
        await writer.write(
            "outputs/conversation/deck.pptx", b"deck", expected_content_id=None
        )
    assert len(requests) == 2
    assert (
        requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]
    )


@pytest.mark.asyncio
async def test_preview_names_the_exact_source_and_uses_same_logical_path(workspace):
    writer, requests = workspace
    artifact = await writer.write(
        "outputs/conversation/deck.pptx",
        b"pdf",
        expected_content_id=None,
        source_content_id="primary",
        title="deck.pdf",
        content_type="application/pdf",
    )
    assert requests[0].url.params["source_content_id"] == "primary"
    assert requests[0].url.params["path"] == "deck.pptx"
    assert artifact.href.endswith("/file/preview")
    assert artifact.file_name == "deck.pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "outputs/other/deck.pptx",
        "shared/deck.pptx",
        "/teams/t/outputs/conversation/deck.pptx",
        "outputs/deck.pptx",
    ],
)
async def test_outputs_cannot_choose_a_different_owner(workspace, path):
    writer, requests = workspace
    with pytest.raises(PermissionError):
        await writer.write(path, b"secret", expected_content_id=None)
    assert requests == []


@pytest.mark.asyncio
async def test_read_returns_identity_from_the_byte_response_and_admitted_scope(
    workspace, monkeypatch
):
    writer, _ = workspace
    client = adapters.get_runtime_context().config.control_plane_http_client
    content_id = "d7ce08d0-e6ba-4917-8e21-6d3fd6e366f8"
    requests = []

    async def send(request, **kwargs):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-content-id": content_id},
            content=b"old bytes",
            request=request,
        )

    monkeypatch.setattr(client, "send", send)
    result = await writer.read("file", max_bytes=100)
    assert result.content == b"old bytes"
    assert result.content_id == content_id
    assert len(requests) == 1
    assert requests[0].url.path.endswith(
        "/spaces/space/sessions/conversation/files/file/content"
    )
    assert requests[0].url.params["person"] == "alice"
    assert requests[0].url.params["run"] == "admitted-run"
    assert requests[0].url.params["agent"] == "instance"


@pytest.mark.asyncio
async def test_read_stops_oversized_chunked_response(workspace, monkeypatch):
    writer, _ = workspace
    client = adapters.get_runtime_context().config.control_plane_http_client
    consumed = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b"1234", b"5678", b"must not read"]:
                consumed.append(chunk)
                yield chunk

    async def send(request, **kwargs):
        return httpx.Response(200, stream=Chunks(), request=request)

    monkeypatch.setattr(client, "send", send)
    with pytest.raises(ValueError, match="byte limit"):
        await writer.read("file", max_bytes=5)
    assert consumed == [b"1234", b"5678"]


@pytest.mark.asyncio
async def test_list_and_reads_reject_unbounded_requests_before_transport(workspace):
    writer, requests = workspace
    for limit, offset in [(0, 0), (101, 0), (1, -1), (1, 10001)]:
        with pytest.raises(ValueError):
            await writer.list(limit=limit, offset=offset)
    for size in [0, 32 * 1024 * 1024 + 1]:
        with pytest.raises(ValueError):
            await writer.read("file", max_bytes=size)
    assert not requests
