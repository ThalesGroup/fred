"""MCPAdapter calls use the current run's credentials on v2 HTTP."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx2
import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.utilities.asgi_transport import StreamingASGITransport
from fred_runtime.common import mcp_utils
from fred_runtime.common.mcp_http_auth import MCPHTTPAuth
from fred_runtime.common.outbound_credentials import (
    OutboundCredentials,
    PersonCredentialProvider,
)
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration
from langchain.mcp import MCPAdapter
from mcp.shared._httpx_utils import request_within_origin
from starlette.responses import JSONResponse


@pytest.mark.asyncio
async def test_http_factory_allows_one_expiry_retry_without_following_redirects() -> (
    None
):
    state = {"token": "expired", "refreshes": 0}
    seen: list[tuple[str, str]] = []

    async def token() -> str:
        return state["token"]

    async def refresh() -> str:
        state["refreshes"] += 1
        state["token"] = "renewed"
        return "renewed"

    async def receive(request: httpx2.Request) -> httpx2.Response:
        seen.append((str(request.url), request.headers.get("authorization", "")))
        if request.url.path == "/redirect":
            return httpx2.Response(307, headers={"Location": "/elsewhere"})
        if request.headers.get("authorization") == "Bearer expired":
            return httpx2.Response(
                401,
                headers={"WWW-Authenticate": "Bearer token expired"},
            )
        return httpx2.Response(200)

    client = mcp_utils._mcp_http_client_factory(
        auth=MCPHTTPAuth(PersonCredentialProvider(token), refresh=refresh)
    )
    client._transport = httpx2.MockTransport(receive)
    async with client:
        response = await client.post(
            "http://test.invalid/mcp", json={"method": "tools/call"}
        )
        with pytest.raises(httpx2.TooManyRedirects, match="redirect refused"):
            await request_within_origin(client, "GET", "http://test.invalid/redirect")

    assert response.status_code == 200
    assert state["refreshes"] == 1
    assert seen == [
        ("http://test.invalid/mcp", "Bearer expired"),
        ("http://test.invalid/mcp", "Bearer renewed"),
        ("http://test.invalid/redirect", "Bearer renewed"),
    ]


@pytest.mark.asyncio
async def test_sdk_catalog_cache_reuses_tools_only_for_same_principal() -> None:
    server = FastMCP("Cache test", cache_ttl=300, cache_scope="private")
    listed = 0

    class CountListings(Middleware):
        async def on_list_tools(self, context: MiddlewareContext, call_next):
            nonlocal listed
            listed += 1
            return await call_next(context)

    @server.tool
    def ping() -> str:
        return "ok"

    server.add_middleware(CountListings())
    catalog_server = MCPServerConfiguration.model_validate(
        {
            "id": "cache-test",
            "name": "Cache test",
            "transport": "streamable_http",
            "url": "http://cache-test/mcp",
        }
    )

    for token, expected_listings in (("first", 1), ("first", 1), ("second", 2)):
        cache = mcp_utils._catalog_cache_config(
            catalog_server, OutboundCredentials(authorization=f"Bearer {token}")
        )
        adapter = MCPAdapter(Client(server, cache=cache))
        assert [tool.name for tool in await adapter.list_tools()] == ["ping"]
        assert listed == expected_listings

    no_hint_server = FastMCP("No cache hint")

    @no_hint_server.tool
    def ping_without_hint() -> str:
        return "ok"

    no_hint_server.add_middleware(CountListings())
    no_hint_catalog = catalog_server.model_copy(update={"id": "no-hint"})
    for expected_listings in (3, 4):
        cache = mcp_utils._catalog_cache_config(
            no_hint_catalog, OutboundCredentials(authorization="Bearer first")
        )
        adapter = MCPAdapter(Client(no_hint_server, cache=cache))
        assert [tool.name for tool in await adapter.list_tools()] == [
            "ping_without_hint"
        ]
        assert listed == expected_listings


@pytest.mark.asyncio
async def test_adapter_uses_live_bearer_and_retries_one_expired_token(
    monkeypatch,
) -> None:
    server = FastMCP("Token test")

    @server.tool
    async def current_bearer() -> str:
        return get_http_request().headers["authorization"]

    app = server.http_app(path="/mcp", stateless_http=True, json_response=True)
    seen: list[str] = []

    class AuthenticatedApp:
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope["headers"])
                bearer = headers.get(b"authorization", b"").decode()
                seen.append(bearer)
                if bearer == "Bearer expired":
                    response = JSONResponse(
                        {"detail": "token expired"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer token expired"},
                    )
                    await response(scope, receive, send)
                    return
            await app(scope, receive, send)

    def client_factory(**kwargs):
        kwargs["follow_redirects"] = False
        return httpx2.AsyncClient(
            transport=StreamingASGITransport(AuthenticatedApp()), **kwargs
        )

    monkeypatch.setattr(mcp_utils, "_mcp_http_client_factory", client_factory)
    state = {"token": "initial", "refreshes": 0}

    async def token() -> str:
        return state["token"]

    async def refresh() -> str:
        state["refreshes"] += 1
        state["token"] = "renewed"
        return "renewed"

    catalog_server = MCPServerConfiguration.model_validate(
        {
            "id": "token-test",
            "name": "Token test",
            "transport": "streamable_http",
            "url": "http://test/mcp",
        }
    )
    async with app.lifespan(app):
        _, tools = await mcp_utils.get_connected_mcp_client_for_agent(
            "agent",
            [catalog_server],
            RuntimeContext(),
            credentials=PersonCredentialProvider(token),
            refresh_token_cb=refresh,
        )
        assert [tool.name for tool in tools] == ["current_bearer"]
        assert tools[0].metadata is not None
        assert tools[0].metadata[mcp_utils.MCP_SERVER_ID_METADATA_KEY] == "token-test"

        state["token"] = "expired"
        result = await tools[0].ainvoke({})

    assert "Bearer renewed" in str(result)
    assert state["refreshes"] == 1
    assert "Bearer expired" in seen
    assert "Bearer renewed" in seen


@pytest.mark.asyncio
async def test_adapter_lists_and_calls_v2_stdio_tools() -> None:
    catalog_server = MCPServerConfiguration.model_validate(
        {
            "id": "stdio-test",
            "name": "Stdio test",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("fixtures") / "mcp_v2_stdio.py")],
        }
    )

    async def token() -> str:
        return "stdio-token"

    adapters, tools = await mcp_utils.get_connected_mcp_client_for_agent(
        "agent",
        [catalog_server],
        RuntimeContext(),
        credentials=PersonCredentialProvider(token),
    )

    assert [tool.name for tool in tools] == ["current_bearer"]
    assert isinstance(adapters[0].client, Client)
    assert adapters[0].client.transport.keep_alive is False
    async with adapters[0]:
        assert adapters[0].client.protocol_version == "2026-07-28"
    assert tools[0].metadata is not None
    assert tools[0].metadata[mcp_utils.MCP_SERVER_ID_METADATA_KEY] == "stdio-test"
    assert "Bearer stdio-token" in str(await tools[0].ainvoke({}))


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["sse", "websocket"])
async def test_unsupported_catalog_transports_fail_before_discovery(
    transport: str,
) -> None:
    catalog_server = MCPServerConfiguration.model_validate(
        {
            "id": "unsupported-test",
            "name": "Unsupported test",
            "transport": transport,
            "url": "http://test/mcp",
        }
    )
    with pytest.raises(mcp_utils.UnsupportedTransportError):
        await mcp_utils.get_connected_mcp_client_for_agent(
            "agent", [catalog_server], RuntimeContext()
        )
