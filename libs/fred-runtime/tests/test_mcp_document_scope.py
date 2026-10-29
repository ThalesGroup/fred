# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The native Agent Pod sends its server-bound scope outside MCP arguments."""

from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from conftest import StaticWorkloadTokens, admitted_provider
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_runtime.common.mcp_http_auth import MCPHTTPAuth
from fred_runtime.integrations.v2_runtime.adapters import _McpRuntimeAgentShim
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding

A, D1, OUTSIDE = [str(UUID(int=i)) for i in (201, 101, 999)]


def binding(documents=None):
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            user_id="alice",
            session_id="s-1",
            team_id="team-1",
            space_id=SPACE_ID,
            agent_instance_id=INSTANCE_ID,
            selected_document_uids=documents,
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="alice",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest.mark.asyncio
async def test_refresh_and_rebind_do_not_widen_server_agent_scope():
    authority = TurnAuthority(turn_binding("agent-1", session="s-1"), None)
    with RunScope.open() as run:
        run.turn_authority = authority
        authority.start(run)
        shim = _McpRuntimeAgentShim(
            binding=binding([D1]),
            settings=SimpleNamespace(),
            document_scope=DocumentScope.from_ids([A]),
        )
        provider = admitted_provider(StaticWorkloadTokens())
        auth = MCPHTTPAuth(provider, document_context=shim.document_context)
        seen = []

        async def receive(request):
            seen.append(
                DocumentAccessContext.model_validate_json(
                    request.headers[DOCUMENT_CONTEXT_HEADER]
                )
            )
            return httpx2.Response(401 if len(seen) == 1 else 200)

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(receive), auth=auth
        ) as client:
            await client.post(
                "https://kf.invalid/mcp",
                headers={DOCUMENT_CONTEXT_HEADER: "spoofed"},
                json={"arguments": {"document_scope": {}, "space_id": OUTSIDE}},
            )
            assert len(seen) == 2
            assert seen[0] == seen[1]
            expected = DocumentScope.from_ids([A]).intersect(
                DocumentScope.from_ids(document_ids=[D1])
            )
            assert seen[0].document_scope == expected
            assert str(seen[0].space_id) == SPACE_ID
            shim.rebind(binding([]))
            await client.post("https://kf.invalid/mcp")
            assert seen[-1].document_scope.is_empty
            shim.rebind(binding(None))
            await client.post("https://kf.invalid/mcp")
            assert seen[-1].document_scope == DocumentScope.from_ids([A])
            assert not seen[-1].document_scope.covers(UUID(OUTSIDE), None)
            provider._runtime.records.mark_terminal(provider.run_id)
            from fred_runtime.runtime_support.authority import (
                DelegationUnavailableError,
            )

            with pytest.raises(DelegationUnavailableError):
                await client.post("https://kf.invalid/mcp")
            assert len(seen) == 4


@pytest.mark.asyncio
async def test_document_pack_mcp_activation_carries_scope_before_any_tool_call(
    monkeypatch,
):
    from fred_runtime.common import mcp_utils
    from fred_sdk.contracts.models import MCPServerConfiguration

    provider = admitted_provider(StaticWorkloadTokens())
    payload = DocumentAccessContext(
        space_id=UUID(SPACE_ID), document_scope=DocumentScope.from_ids([A])
    ).model_dump_json()
    seen = []

    class Adapter:
        def __init__(self, client):
            self.client = client

        async def list_tools(self):
            transport = self.client.transport

            async def receive(request):
                seen.append(request.headers.get(DOCUMENT_CONTEXT_HEADER))
                return httpx2.Response(200)

            async with httpx2.AsyncClient(
                transport=httpx2.MockTransport(receive), auth=transport.auth
            ) as client:
                await client.post(transport.url, json={"method": "tools/list"})
            return []

    monkeypatch.setattr(mcp_utils, "MCPAdapter", Adapter)
    server = MCPServerConfiguration(
        id="mcp-knowledge-flow-mcp-tabular",
        name="tabular",
        transport="streamable_http",
        url="https://kf.invalid/mcp/tabular",
        auth_mode="delegated",
        enabled=True,
    )
    await mcp_utils.get_connected_mcp_client_for_agent(
        "agent-a",
        [server],
        RuntimeContext(),
        credentials=provider,
        refresh_owner=SimpleNamespace(document_context=lambda: payload),
    )
    assert seen == [payload]
    assert mcp_utils._catalog_cache_config(server, await provider.credentials()) is None


@pytest.mark.asyncio
async def test_ordinary_mcp_client_never_forwards_a_document_context():
    from fred_runtime.common.outbound_credentials import static_person_provider

    seen = []

    async def receive(request):
        seen.append(request.headers.get(DOCUMENT_CONTEXT_HEADER))
        return httpx2.Response(200)

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(receive),
        auth=MCPHTTPAuth(static_person_provider("person")),
    ) as client:
        await client.post(
            "https://external.invalid/mcp",
            headers={DOCUMENT_CONTEXT_HEADER: "untrusted"},
        )
    assert seen == [None]
