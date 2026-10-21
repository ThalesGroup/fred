"""MCPAdapter calls use the current run's credentials on v2 HTTP."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx2
import pytest
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from fastmcp.utilities.asgi_transport import StreamingASGITransport
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration
from starlette.responses import JSONResponse

from fred_runtime.common import mcp_utils
from fred_runtime.common.outbound_credentials import PersonCredentialProvider


@pytest.mark.asyncio
async def test_adapter_uses_live_bearer_and_retries_one_expired_token(monkeypatch) -> None:
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

    catalog_server = MCPServerConfiguration(
        id="token-test",
        name="Token test",
        transport="streamable_http",
        url="http://test/mcp",
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
        assert tools[0].metadata[mcp_utils.MCP_SERVER_ID_METADATA_KEY] == "token-test"

        state["token"] = "expired"
        result = await tools[0].ainvoke({})

    assert "Bearer renewed" in str(result)
    assert state["refreshes"] == 1
    assert "Bearer expired" in seen
    assert "Bearer renewed" in seen


@pytest.mark.asyncio
async def test_adapter_lists_and_calls_v2_stdio_tools() -> None:
    catalog_server = MCPServerConfiguration(
        id="stdio-test",
        name="Stdio test",
        transport="stdio",
        command=sys.executable,
        args=[str(Path(__file__).with_name("fixtures") / "mcp_v2_stdio.py")],
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
    async with adapters[0]:
        assert adapters[0].client.protocol_version == "2026-07-28"
    assert tools[0].metadata[mcp_utils.MCP_SERVER_ID_METADATA_KEY] == "stdio-test"
    assert "Bearer stdio-token" in str(await tools[0].ainvoke({}))
