"""MCP v2 requests keep Knowledge Flow's grant and error boundaries."""

from __future__ import annotations

from contextlib import AsyncExitStack

import httpx2
import pytest
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fred_core.logs.context import current_context
from fred_core.logs.http import RequestLoggingMiddleware
from fred_core.logs.propagation import (
    CONTEXT_HEADER,
    admit_delegated_log_context,
    decode_log_context,
)
from fred_core.security import mcp_delegation
from fred_core.security.delegation import DelegationGrant

from knowledge_flow_backend import mcp_mount

_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


async def _request(
    client: httpx2.AsyncClient,
    method: str,
    params: dict | None = None,
) -> httpx2.Response:
    headers = {
        "Authorization": "Bearer test",
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": method,
        "Accept": "application/json, text/event-stream",
    }
    if method == "tools/call":
        headers["Mcp-Name"] = str((params or {})["name"])
    return await client.post(
        "/mcp-test",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {"_meta": _META, **(params or {})},
        },
    )


def _app() -> FastAPI:
    app = FastAPI()

    async def grant_parameters(
        person: str | None = Query(None),
        run: str | None = Query(None),
        agent: str | None = Query(None),
    ) -> None:
        pass

    @app.get("/echo", tags=["Selected"], operation_id="echo", dependencies=[Depends(grant_parameters)])
    async def echo(
        request: Request,
        person: str | None = None,
        run: str | None = None,
        agent: str | None = None,
    ) -> dict:
        return {
            "person": person,
            "run": run,
            "agent": agent,
            "authorization": request.headers.get("authorization"),
        }

    @app.get("/refused", tags=["Selected"], operation_id="refused")
    async def refused() -> None:
        raise HTTPException(403, detail="private receiver body")

    @app.get("/other", tags=["Unselected"], operation_id="other")
    async def other() -> str:
        return "other"

    mcp_mount.mount_fastapi_tools(
        app,
        path="/mcp-test",
        name="Test tools",
        description="Selected test tools",
        tags={"Selected"},
    )
    return app


@pytest.mark.asyncio
async def test_v2_mount_is_stateless_and_uses_only_verified_grant(monkeypatch) -> None:
    async def authenticate(request: Request, token: str):
        assert token == "test"
        reset = mcp_delegation._verified_grant.set(DelegationGrant(person="trusted", run="run-1", agent="agent-1"))
        try:
            yield None
        finally:
            mcp_delegation._verified_grant.reset(reset)

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    apps = [_app(), _app()]
    async with AsyncExitStack() as stack:
        for app in apps:
            await stack.enter_async_context(app.router.lifespan_context(app))
        clients = [
            await stack.enter_async_context(
                httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    base_url="http://test",
                )
            )
            for app in apps
        ]

        listing = await _request(clients[0], "tools/list")
        assert listing.status_code == 200
        assert "Mcp-Session-Id" not in listing.headers
        assert listing.json()["result"]["ttlMs"] == 300_000
        assert listing.json()["result"]["cacheScope"] == "private"
        tools = listing.json()["result"]["tools"]
        assert {tool["name"] for tool in tools} == {"echo", "refused"}
        assert not {"person", "run", "agent"} & set(tools[0]["inputSchema"].get("properties", {}))

        called = await _request(
            clients[1],
            "tools/call",
            {
                "name": "echo",
                "arguments": {"person": "spoofed", "run": "spoofed", "agent": "spoofed"},
            },
        )
        assert called.status_code == 200
        assert "Mcp-Session-Id" not in called.headers
        result = called.json()["result"]
        assert result["structuredContent"] == {
            "person": "trusted",
            "run": "run-1",
            "agent": "agent-1",
            "authorization": "Bearer test",
        }


@pytest.mark.asyncio
async def test_v2_mount_redacts_receiver_refusal(monkeypatch) -> None:
    async def authenticate(request: Request, token: str):
        yield None

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    app = _app()
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            response = await _request(client, "tools/call", {"name": "refused", "arguments": {}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {"cause": "authority_lost"}
    assert "private receiver body" not in response.text


@pytest.mark.asyncio
async def test_v2_inner_request_uses_admitted_context_and_fresh_request_id(monkeypatch) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/inside", tags=["Selected"], operation_id="inside")
    async def inside(request: Request) -> dict:
        admit_delegated_log_context(
            request.headers.get(CONTEXT_HEADER),
            user_id="person-a",
            run_id="run-a",
            agent_id="agent-a",
        )
        return {
            "headers": dict(request.headers),
            "context": current_context(),
            "query": dict(request.query_params),
        }

    mcp_mount.mount_fastapi_tools(app, path="/mcp-test", name="Context test", description="Context test", tags={"Selected"})

    async def authenticate(request: Request, token: str):
        reset = mcp_delegation._verified_grant.set(DelegationGrant(person="person-a", run="run-a", agent="agent-a"))
        try:
            yield None
        finally:
            mcp_delegation._verified_grant.reset(reset)

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            response = await _request(client, "tools/call", {"name": "inside", "arguments": {"person": "model-person"}})
    assert response.status_code == 200
    payload = response.json()["result"]["structuredContent"]
    assert payload["query"] == {"person": "person-a", "run": "run-a", "agent": "agent-a"}
    forwarded = decode_log_context(payload["headers"][CONTEXT_HEADER.lower()])[0]
    assert forwarded is not None
    assert payload["context"]["correlation_id"] == forwarded["correlation_id"]
    assert payload["context"]["user_id"] == "person-a"
    assert payload["context"]["request_id"] != response.headers["x-request-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "marked", "authority_lost"),
    [(403, False, True), (503, True, True), (503, False, False)],
)
async def test_v2_mount_classifies_only_receiver_authority_refusals(monkeypatch, status: int, marked: bool, authority_lost: bool) -> None:
    app = FastAPI()

    @app.get("/protected", tags=["Selected"], operation_id="read_protected")
    async def protected() -> None:
        raise HTTPException(
            status_code=status,
            detail="synthetic-identifier",
            headers={"X-Fred-Denial-Cause": "account_status_unavailable"} if marked else None,
        )

    mcp_mount.mount_fastapi_tools(app, path="/mcp-test", name="Protected test", description="Protected test", tags={"Selected"})

    async def authenticate(request: Request, token: str):
        yield None

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            response = await _request(client, "tools/call", {"name": "read_protected", "arguments": {}})
    result = response.json()["result"]
    assert result["isError"] is True
    assert (result.get("structuredContent") == {"cause": "authority_lost"}) is authority_lost
    assert "synthetic-identifier" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "status", "body", "expected_detail"),
    [
        ("read_query", 400, '{"detail":"Unknown column amount_typo","internal":"private"}', "Unknown column amount_typo"),
        ("another_tool", 400, '{"detail":"private"}', None),
        ("read_query", 500, '{"detail":"private"}', None),
        ("read_query", 400, "private", None),
    ],
)
async def test_v2_mount_keeps_only_curated_sql_400_detail(monkeypatch, tool_name: str, status: int, body: str, expected_detail: str | None) -> None:
    app = FastAPI()

    @app.get("/query", tags=["Selected"], operation_id=tool_name)
    async def query(sql: str) -> Response:
        assert sql == "SELECT amount_typo FROM d_sales"
        return Response(body, status_code=status, media_type="application/json")

    mcp_mount.mount_fastapi_tools(app, path="/mcp-test", name="Query test", description="Query test", tags={"Selected"})

    async def authenticate(request: Request, token: str):
        yield None

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            response = await _request(
                client,
                "tools/call",
                {"name": tool_name, "arguments": {"sql": "SELECT amount_typo FROM d_sales"}},
            )
    result = response.json()["result"]
    assert result["isError"] is True
    assert "private" not in response.text
    if expected_detail is None:
        assert "Tool request failed." in response.text
    else:
        assert expected_detail in response.text
