"""Delegated MCP v2 activation and per-request authority checks."""

from __future__ import annotations

import httpx2
import pytest
from conftest import StaticWorkloadTokens, admitted_provider
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fred_runtime.common import mcp_utils
from fred_runtime.common.mcp_http_auth import MCPHTTPAuth
from fred_runtime.common.outbound_credentials import OutboundCredentialProvider
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration


def _server(
    auth_mode: str, transport: str = "streamable_http"
) -> MCPServerConfiguration:
    return MCPServerConfiguration.model_validate(
        {
            "id": "kf-mcp",
            "name": "kf",
            "transport": transport,
            "url": "http://kf.invalid/mcp",
            "command": "test-server" if transport == "stdio" else None,
            "enabled": True,
            "auth_mode": auth_mode,
        }
    )


async def _discover(monkeypatch, server, credentials: OutboundCredentialProvider):
    class Adapter:
        def __init__(self, client):
            self.client = client

        async def list_tools(self):
            return []

    monkeypatch.setattr(mcp_utils, "MCPAdapter", Adapter)
    return await mcp_utils.get_connected_mcp_client_for_agent(
        "agent-a", [server], RuntimeContext(), credentials=credentials
    )


@pytest.mark.asyncio
async def test_delegated_server_carries_grant_in_http_url_and_m2m_auth(
    monkeypatch,
) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    adapters, _ = await _discover(monkeypatch, _server("delegated"), provider)
    client = adapters[0].client
    assert isinstance(client, Client)
    transport = client.transport
    assert isinstance(transport, StreamableHttpTransport)
    assert "person=alice" in transport.url
    assert "run=run-7" in transport.url
    assert "agent=agent-a" in transport.url
    assert isinstance(transport.auth, MCPHTTPAuth)

    seen = []

    async def receive(request: httpx2.Request) -> httpx2.Response:
        seen.append((str(request.url), request.headers.get("authorization")))
        return httpx2.Response(200)

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(receive), auth=transport.auth
    ) as client:
        await client.post(transport.url, json={"method": "tools/list"})
    assert seen == [(transport.url, "Bearer workload-token")]


@pytest.mark.asyncio
async def test_delegation_refuses_user_token_server(monkeypatch) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    with pytest.raises(DelegationUnavailableError):
        await _discover(monkeypatch, _server("user_token"), provider)


@pytest.mark.asyncio
async def test_no_token_server_stays_anonymous_during_delegation(monkeypatch) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    adapters, _ = await _discover(monkeypatch, _server("no_token"), provider)
    client = adapters[0].client
    assert isinstance(client, Client)
    transport = client.transport
    assert isinstance(transport, StreamableHttpTransport)
    assert transport.url == "http://kf.invalid/mcp"
    assert transport.auth is None


@pytest.mark.asyncio
async def test_delegation_refuses_stdio_server(monkeypatch) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    with pytest.raises(DelegationUnavailableError):
        await _discover(monkeypatch, _server("delegated", "stdio"), provider)


@pytest.mark.asyncio
async def test_ended_run_cannot_send_another_mcp_request(monkeypatch) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    adapters, _ = await _discover(monkeypatch, _server("delegated"), provider)
    client = adapters[0].client
    assert isinstance(client, Client)
    transport = client.transport
    assert isinstance(transport, StreamableHttpTransport)
    provider._runtime.records.mark_terminal("run-7")
    calls = 0

    async def receive(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200)

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(receive), auth=transport.auth
    ) as client:
        with pytest.raises(DelegationUnavailableError):
            await client.post(transport.url, json={"method": "tools/call"})
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_receiver_refusal_loses_authority(monkeypatch, status: int) -> None:
    provider = admitted_provider(StaticWorkloadTokens())
    adapters, _ = await _discover(monkeypatch, _server("delegated"), provider)
    client = adapters[0].client
    assert isinstance(client, Client)
    transport = client.transport
    assert isinstance(transport, StreamableHttpTransport)
    calls = 0

    async def receive(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(status, text="private receiver body")

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(receive), auth=transport.auth
    ) as client:
        with pytest.raises(AuthorityLostError) as raised:
            await client.post(transport.url, json={"method": "tools/call"})
    assert calls == (2 if status == 401 else 1)
    assert "private receiver body" not in str(raised.value)


def test_mcp_http_client_refuses_redirects() -> None:
    client = mcp_utils._mcp_http_client_factory(follow_redirects=True)
    assert not client.follow_redirects
    assert client.max_redirects == 1
