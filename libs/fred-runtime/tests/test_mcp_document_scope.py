# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The native Agent Pod sends its server-bound scope outside MCP arguments."""

from collections.abc import Sequence
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
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding

A, D1, OUTSIDE = [str(UUID(int=i)) for i in (201, 101, 999)]


class _Settings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


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
            settings=_Settings(),
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
    server = MCPServerConfiguration.model_validate(
        {
            "id": "mcp-knowledge-flow-mcp-tabular",
            "name": "tabular",
            "transport": "streamable_http",
            "url": "https://kf.invalid/mcp/tabular",
            "auth_mode": "delegated",
            "enabled": True,
        }
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


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_http_and_mcp_share_fixed_attachment_ceiling(monkeypatch, enabled):
    import httpx
    from fred_runtime.common.kf_document_client import KfDocumentClient
    from fred_runtime.common.kf_vectorsearch_client import VectorSearchClient

    session = str(UUID(int=301))
    attachment = dict(
        document_id=str(UUID(int=401)), name="report.csv", mime="text/csv"
    )
    bound = binding([])
    bound.runtime_context.session_id = session
    facts = turn_binding("agent-1", session=session, attachments=[attachment])
    authority = TurnAuthority(facts, None)
    with RunScope.open() as run:
        run.turn_authority = authority
        authority.start(run)
        authority.bind_documents(
            bound.runtime_context, DocumentScope(), attachments_enabled=enabled
        )
        shim = _McpRuntimeAgentShim(binding=bound, settings=_Settings())
        expected = authority.document_context(bound.runtime_context)
        assert expected.document_scope.is_empty
        assert expected.attachment_ids == ((UUID(int=401),) if enabled else ())
        assert (
            DocumentAccessContext.model_validate_json(shim.document_context())
            == expected
        )
        seen = []

        async def request(**kwargs):
            seen.append(kwargs)
            path = kwargs["path"]
            data = (
                []
                if path.endswith(("search", "chunks"))
                else {
                    "document_uid": attachment["document_id"],
                    "content": "text",
                    "summary": "summary",
                    "shrunk_for_budget": False,
                }
            )
            return httpx.Response(
                200, json=data, request=httpx.Request("POST", "https://kf.invalid")
            )

        vector = object.__new__(VectorSearchClient)
        document = object.__new__(KfDocumentClient)
        document._summarize_read_timeout = 5
        monkeypatch.setattr(vector, "_request_with_token_refresh", request)
        monkeypatch.setattr(document, "_request_with_token_refresh", request)
        await vector.search(question="q", document_context=expected)
        await vector.get_document_chunks(
            document_uid=attachment["document_id"], limit=10, document_context=expected
        )
        await document.fetch_markdown(
            document_uid=attachment["document_id"], document_context=expected
        )
        await document.summarize(
            document_uid=attachment["document_id"], document_context=expected
        )
        await document.extract(
            document_uid=attachment["document_id"],
            instruction="all",
            document_context=expected,
        )
        assert len(seen) == 5
        for call in seen:
            assert (
                DocumentAccessContext.model_validate_json(
                    call["headers"][DOCUMENT_CONTEXT_HEADER]
                )
                == expected
            )
            assert "attachment_ids" not in call.get("json", {})
            assert "conversation_id" not in call.get("json", {})

        # Credential retries overwrite untrusted headers with the same fixed context.
        provider = admitted_provider(StaticWorkloadTokens())
        contexts = []

        async def receive(request):
            contexts.append(
                DocumentAccessContext.model_validate_json(
                    request.headers[DOCUMENT_CONTEXT_HEADER]
                )
            )
            return httpx2.Response(401 if len(contexts) == 1 else 200)

        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(receive),
            auth=MCPHTTPAuth(provider, document_context=shim.document_context),
        ) as client:
            await client.post(
                "https://kf.invalid/mcp", headers={DOCUMENT_CONTEXT_HEADER: "injected"}
            )
        assert contexts == [expected, expected]
        # A rebind/descendant cannot undo the parent's disabled source choice.
        descendant = bound.runtime_context.model_copy(
            update={"selected_document_uids": None, "include_session_scope": True}
        )
        authority.bind_documents(descendant, DocumentScope(), attachments_enabled=True)
        assert authority.document_context(descendant) == expected


@pytest.mark.asyncio
async def test_newly_ready_files_wait_for_the_next_turn():
    session = str(UUID(int=301))
    first = dict(
        document_id=str(UUID(int=401)), name="first.pdf", mime="application/pdf"
    )
    later = dict(
        document_id=str(UUID(int=402)),
        name="later.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    bound = binding([])
    bound.runtime_context.session_id = session
    data = turn_binding("agent-1", session=session, attachments=[first]).model_dump(
        mode="json"
    )
    from fred_sdk.contracts.weaver import WeaverRuntimeBinding

    for expected_ids in [(UUID(int=401),), (UUID(int=401), UUID(int=402))]:
        authority = TurnAuthority(WeaverRuntimeBinding.model_validate(data), None)
        with RunScope.open() as run:
            run.turn_authority = authority
            authority.start(run)
            authority.bind_documents(
                bound.runtime_context, DocumentScope(), attachments_enabled=True
            )
            data["attachments"] = [first, later]
            for _ in range(2):
                assert (
                    authority.document_context(bound.runtime_context).attachment_ids
                    == expected_ids
                )
