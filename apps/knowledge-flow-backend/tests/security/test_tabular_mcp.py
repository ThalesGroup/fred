# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""MCP discovery and calls preserve the authenticated document envelope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx2
import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.security import mcp_delegation, oidc
from fred_core.security.delegation import AssertedUser, DelegationGrant
from fred_core.security.structure import KeycloakUser

from knowledge_flow_backend import mcp_mount
from knowledge_flow_backend.features.document_scope import declare_document_context_openapi
from knowledge_flow_backend.features.tabular import controller
from knowledge_flow_backend.security.weaver_admission import delegated_person
from tests.security.test_mcp_v2_mount import _META

PERSON = AssertedUser(uid="alice", client_id="native-agent", run_id="run", agent_id="agent")
SPACE, FOLDER, CONVERSATION, ATTACHMENT = [UUID(int=i) for i in range(1, 5)]


@pytest.mark.asyncio
async def test_tabular_mcp_initializes_and_forwards_only_outer_document_scope(monkeypatch):
    seen = []

    def service(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(list_documents=AsyncMock(return_value=[]))

    monkeypatch.setattr(controller, "TabularService", service)

    async def authenticate(request, token):
        reset = mcp_delegation._verified_grant.set(DelegationGrant(person="alice", run="run", agent="agent"))
        try:
            yield PERSON
        finally:
            mcp_delegation._verified_grant.reset(reset)

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    app, router = FastAPI(), APIRouter()
    controller.TabularController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: PERSON
    declare_document_context_openapi(app)
    mcp_mount.mount_fastapi_tools(app, path="/mcp/tabular", name="Tabular", description="test", tags={"Tabular"})
    headers = {"Authorization": "Bearer workload", "MCP-Protocol-Version": "2026-07-28", "Accept": "application/json, text/event-stream"}
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            listing = await client.post("/mcp/tabular", headers={**headers, "Mcp-Method": "tools/list"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": _META}})
            tools = listing.json()["result"]["tools"]
            assert {tool["name"] for tool in tools} == {"list_tabular_documents", "describe_tabular_documents", "search_tabular_values", "query_tabular_documents"}
            for tool in tools:
                assert DOCUMENT_CONTEXT_HEADER not in tool["inputSchema"].get("properties", {})
                assert DOCUMENT_CONTEXT_HEADER not in tool["inputSchema"].get("required", [])
                assert "space_id" not in tool["inputSchema"].get("properties", {})
                assert "document_scope" not in tool["inputSchema"].get("properties", {})
                assert "conversation_id" not in tool["inputSchema"].get("properties", {})
                assert "attachment_ids" not in tool["inputSchema"].get("properties", {})
            assert not seen  # Greeting initialization needs neither datasets nor a database read.
            for scope in (DocumentScope.from_ids([str(FOLDER)]), DocumentScope.from_ids([], [])):
                payload = DocumentAccessContext(space_id=SPACE, document_scope=scope, conversation_id=CONVERSATION, attachment_ids=(ATTACHMENT,)).model_dump_json()
                response = await client.post(
                    "/mcp/tabular",
                    headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "list_tabular_documents", DOCUMENT_CONTEXT_HEADER: payload},
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"_meta": _META, "name": "list_tabular_documents", "arguments": {}}},
                )
                assert response.status_code == 200
                assert not response.json()["result"].get("isError", False)
                assert seen[-1] == {"context": DocumentAccessContext.model_validate_json(payload)}
            assert len(seen) == 2


@pytest.mark.parametrize("raw", [None, "null", "{}", '{"space_id":"bad","document_scope":{}}'])
def test_missing_or_malformed_context_fails_closed(raw):
    app, router = FastAPI(), APIRouter()
    controller.TabularController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: PERSON
    with TestClient(app) as client:
        response = client.get("/tabular/documents", headers={DOCUMENT_CONTEXT_HEADER: raw} if raw is not None else {})
    assert response.status_code == (403 if raw is None else 400)


def test_person_token_cannot_assert_the_document_envelope():
    app, router = FastAPI(), APIRouter()
    controller.TabularController(router)
    app.include_router(router)
    app.dependency_overrides[oidc.authenticate_request] = lambda: KeycloakUser(uid="alice", username="alice", roles=[])
    with TestClient(app) as client:
        response = client.get("/tabular/documents", headers={DOCUMENT_CONTEXT_HEADER: DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope()).model_dump_json()})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inner_tool_request_cannot_replace_the_verified_header(monkeypatch):
    from fastmcp.server import dependencies

    outer = Request({"type": "http", "headers": [(b"authorization", b"Bearer workload"), (DOCUMENT_CONTEXT_HEADER.encode(), b"trusted")]})
    monkeypatch.setattr(dependencies, "get_http_request", lambda: outer)
    for grant, expected in [(None, None), (DelegationGrant(person="alice", run="run", agent="agent"), "trusted")]:
        monkeypatch.setattr(mcp_mount, "verified_grant", lambda: grant)
        request = httpx2.Request("GET", "http://kf/tabular/documents", headers={DOCUMENT_CONTEXT_HEADER: "from-tool"})
        await mcp_mount._forward_verified_identity(request)
        assert request.headers.get(DOCUMENT_CONTEXT_HEADER) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("delegated", [False, True])
async def test_mcp_forwarding_discards_model_header_and_uses_only_verified_outer_context(monkeypatch, delegated):
    from fastmcp.server import dependencies

    context = DocumentAccessContext(space_id=SPACE, document_scope=DocumentScope.from_ids([], []), conversation_id=CONVERSATION, attachment_ids=(ATTACHMENT,))
    outer = SimpleNamespace(headers={DOCUMENT_CONTEXT_HEADER: context.model_dump_json()})
    monkeypatch.setattr(dependencies, "get_http_request", lambda: outer)
    grant = DelegationGrant(person="alice", run="turn", agent="agent") if delegated else None
    monkeypatch.setattr(mcp_mount, "verified_grant", lambda: grant)
    request = httpx2.Request("GET", "http://internal/tabular/documents", headers={DOCUMENT_CONTEXT_HEADER: '{"attachment_ids":["injected"]}'})
    await mcp_mount._forward_verified_identity(request)
    assert request.headers.get(DOCUMENT_CONTEXT_HEADER) == (context.model_dump_json() if delegated else None)
