# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Managed MCP admission and per-turn execution. Local fakes, never real credentials."""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from conftest import StaticWorkloadTokens
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_runtime.common import managed_mcp
from fred_sdk.contracts.managed_mcp import (
    McpConnectionBinding,
    McpCredentialBinding,
    McpTabularBinding,
    McpTool,
)
from mcp.types import TextContent, Tool

ID = UUID("8cfd2a56-2d35-4d18-b67c-5e42b0a9c122")


def binding(*, revision=1, auth=None, url="https://tools.invalid/mcp"):
    return McpConnectionBinding.model_validate(
        dict(
            connection_id=ID,
            capability_id=f"managed-mcp:{ID}",
            revision=revision,
            display_name="Search",
            configuration=dict(url=url, authentication=auth or {"kind": "none"}),
            tools=[
                dict(
                    name="search",
                    description="Find",
                    input_schema={"type": "object", "properties": {}},
                    output_schema=None,
                    annotations=None,
                )
            ],
        )
    )


def remote(name="search", description="Find"):
    return Tool(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
    )


class FakeClient:
    instances = []
    pages = []
    fail = False
    gate: asyncio.Event | None = None

    def __init__(self, transport, **kwargs):
        self.transport = transport
        self.options = kwargs
        self.opened = 0
        self.closed = 0
        self.cursors = []
        self.calls = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        self.opened += 1
        return self

    async def __aexit__(self, *_):
        self.closed += 1

    async def list_tools_mcp(self, *, cursor, cache_mode):
        self.cursors.append(cursor)
        assert cache_mode == "bypass"
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("remote error contains synthetic-secret")
        return self.pages[len(self.cursors) - 1]


@pytest.fixture(autouse=True)
def clients(monkeypatch):
    FakeClient.instances = []
    FakeClient.pages = [page([remote()])]
    FakeClient.fail = False
    FakeClient.gate = None
    monkeypatch.setattr(managed_mcp, "Client", FakeClient)


def page(tools, cursor=None):
    return SimpleNamespace(
        tools=tools, next_cursor=cursor, model_dump_json=lambda: "{}"
    )


def test_local_destination_and_secret_are_verified(monkeypatch):
    admitted = binding(auth={"kind": "bearer", "credential_binding": "provider"})
    local = McpCredentialBinding(
        credential_binding="provider",
        url=admitted.configuration.url,
        secret_env="FRED_TEST_MCP_KEY",  # pragma: allowlist secret - test environment variable name
    )
    monkeypatch.delenv("FRED_TEST_MCP_KEY", raising=False)
    with pytest.raises(managed_mcp.ManagedMcpError, match="credential_missing"):
        managed_mcp.credential_headers(admitted, [local])
    monkeypatch.setenv("FRED_TEST_MCP_KEY", "synthetic-secret")
    assert managed_mcp.credential_headers(admitted, [local]) == {
        "Authorization": "Bearer synthetic-secret"
    }
    with pytest.raises(managed_mcp.ManagedMcpError, match="destination_mismatch"):
        managed_mcp.credential_headers(
            binding(
                auth=admitted.configuration.authentication.model_dump(),
                url="https://other.invalid/mcp",
            ),
            [local],
        )
    assert "synthetic-secret" not in admitted.model_dump_json()


def test_selection_and_compatibility_are_independent_of_native_names():
    admitted = binding()
    managed_mcp.validate_admission(
        ["search", admitted.capability_id], [admitted], compatible=True, credentials=[]
    )
    for selected, values, compatible in [
        (["search"], [admitted], True),
        ([admitted.capability_id], [], True),
        ([admitted.capability_id], [admitted], False),
    ]:
        with pytest.raises(managed_mcp.ManagedMcpError, match="binding_mismatch"):
            managed_mcp.validate_admission(
                selected, values, compatible=compatible, credentials=[]
            )


@pytest.mark.asyncio
async def test_pagination_ignores_additions_and_clients_are_owned_per_turn(monkeypatch):
    FakeClient.pages = [page([remote()], "next"), page([remote("new-tool")])]
    converted = []

    async def convert(tool, client):
        from langchain_core.tools import StructuredTool

        async def call(**_):
            async with client:
                client.calls.append(tool.name)
                return "done"

        result = StructuredTool(
            name=tool.name, description="Find", args_schema={}, coroutine=call
        )
        converted.append(result)
        return result

    monkeypatch.setattr(managed_mcp, "as_langchain_tool", convert)
    registry = CapabilityRegistry()
    before = tuple(registry.ids())
    first = await managed_mcp.connect([binding()], [])
    second = await managed_mcp.connect(
        [binding(revision=2).model_copy(update={"display_name": "Renamed"})], []
    )
    assert len(first) == len(second) == 1
    assert first[0] is not second[0]
    assert tuple(registry.ids()) == before
    assert all(c.options["cache"] is False for c in FakeClient.instances)
    assert all(
        c.cursors == [None, "next"] and c.closed == 1 for c in FakeClient.instances
    )
    assert await first[0].ainvoke({}) == "done"
    assert FakeClient.instances[0].calls == ["search"]
    assert FakeClient.instances[1].calls == []
    assert FakeClient.instances[0].opened == FakeClient.instances[0].closed == 2
    assert first[0].name == second[0].name
    assert first[0].description == "MCP tool: search.\nFind"
    assert first[0].metadata is not None
    assert first[0].metadata["mcp_display_name"] == "Search · search"
    assert second[0].metadata is not None
    assert second[0].metadata["mcp_display_name"] == "Renamed · search"


@pytest.mark.asyncio
async def test_original_names_without_descriptions_and_across_connections(monkeypatch):
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    }
    published = tuple(
        McpTool(
            name=name,
            description=None,
            input_schema=schema,
            output_schema=None,
            annotations=None,
        )
        for name in ("add", "multiply")
    )
    first = binding().model_copy(
        update={"tools": published, "display_name": "Parc Eolien"}
    )
    other_id = UUID("affd2a56-2d35-4d18-b67c-5e42b0a9c122")
    second = first.model_copy(
        update={
            "connection_id": other_id,
            "capability_id": f"managed-mcp:{other_id}",
            "tools": published[:1],
            "display_name": "Autre parc",
        }
    )
    before = [value.model_dump() for value in (first, second)]
    FakeClient.pages = [
        page([Tool(name=tool.name, input_schema=schema) for tool in published])
    ]

    async def call_tool(client, name, arguments, *, raise_on_error):
        assert raise_on_error is False
        client.calls.append((name, arguments))
        a, b = arguments["a"], arguments["b"]
        result = a + b if name == "add" else a * b
        return SimpleNamespace(
            content=[TextContent(type="text", text=str(result))],
            is_error=False,
            structured_content=None,
        )

    # Exercise the real LangChain adapter, replacing only the MCP transport peer.
    monkeypatch.setattr(FakeClient, "server_info", None, raising=False)
    monkeypatch.setattr(FakeClient, "call_tool", call_tool, raising=False)
    tools = await managed_mcp.connect([first, second], [])
    assert len({tool.name for tool in tools}) == 3
    assert all(len(tool.name) <= 64 for tool in tools)
    assert [(tool.metadata or {})["mcp_display_name"] for tool in tools] == [
        "Parc Eolien · add",
        "Parc Eolien · multiply",
        "Autre parc · add",
    ]
    assert [tool.description for tool in tools] == [
        "MCP tool: add.",
        "MCP tool: multiply.",
        "MCP tool: add.",
    ]
    results = [await tool.ainvoke({"a": 2, "b": 3}) for tool in tools]
    assert [result[0]["text"] for result in results] == ["5", "6", "5"]
    assert [client.calls for client in FakeClient.instances] == [
        [("add", {"a": 2, "b": 3}), ("multiply", {"a": 2, "b": 3})],
        [("add", {"a": 2, "b": 3})],
    ]
    assert [value.model_dump() for value in (first, second)] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [[], [remote(description="Changed")]])
async def test_removed_or_changed_published_tool_refuses_execution(tools):
    FakeClient.pages = [page(tools)]
    with pytest.raises(managed_mcp.ManagedMcpError, match="published_tool_changed"):
        await managed_mcp.connect([binding()], [])
    assert FakeClient.instances[0].closed == 1


@pytest.mark.asyncio
async def test_partial_inventory_and_cycles_do_not_publish_partial_tools():
    FakeClient.pages = [page([remote()], "same"), page([], "same")]
    with pytest.raises(managed_mcp.ManagedMcpError, match="invalid_pagination"):
        await managed_mcp.connect([binding()], [])
    assert FakeClient.instances[0].closed == 1


@pytest.mark.asyncio
async def test_failure_redacts_provider_body_and_cancellation_closes():
    FakeClient.fail = True
    with pytest.raises(managed_mcp.ManagedMcpError) as error:
        await managed_mcp.connect([binding()], [])
    assert str(error.value) == "mcp_connection_unavailable"
    FakeClient.fail = False
    FakeClient.gate = asyncio.Event()
    pending = asyncio.create_task(managed_mcp.connect([binding()], []))
    for _ in range(10):
        await asyncio.sleep(0)
        if len(FakeClient.instances) == 2 and FakeClient.instances[-1].cursors:
            break
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert FakeClient.instances[-1].closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("auth", "expected_headers"),
    [
        (
            {
                "kind": "api_key",
                "credential_binding": "provider",
                "header": "x-api-key",
            },
            {"x-api-key": "synthetic-secret"},
        ),
        (
            {"kind": "bearer", "credential_binding": "provider"},
            {"authorization": "Bearer synthetic-secret"},
        ),
    ],
)
async def test_http_uses_only_provider_key_and_refuses_redirect(
    monkeypatch, auth, expected_headers
):
    seen = []

    def receive(request):
        seen.append(request)
        return httpx2.Response(307, headers={"Location": "https://other.invalid/mcp"})

    original_client = httpx2.AsyncClient
    monkeypatch.setattr(
        httpx2,
        "AsyncClient",
        lambda **kwargs: original_client(
            **kwargs, transport=httpx2.MockTransport(receive), trust_env=False
        ),
    )
    admitted = binding(auth=auth)
    local = McpCredentialBinding(
        credential_binding="provider",
        url=admitted.configuration.url,
        secret_env="FRED_TEST_MCP_KEY",  # pragma: allowlist secret - test environment variable name
    )
    monkeypatch.setenv("FRED_TEST_MCP_KEY", "synthetic-secret")
    factory = managed_mcp._client_factory(
        managed_mcp.credential_headers(admitted, [local])
    )
    client = factory(
        {"Accept": "application/json"}, httpx2.Timeout(5), None, follow_redirects=True
    )
    async with client:
        with pytest.raises(httpx2.TooManyRedirects):
            await client.post("https://tools.invalid/mcp")
    assert len(seen) == 1
    assert {
        name: value
        for name, value in seen[0].headers.items()
        if name in {"authorization", "x-api-key"}
    } == expected_headers
    assert str(seen[0].url) == admitted.configuration.url
    assert not any(name.startswith("x-fred") for name in seen[0].headers)


@pytest.mark.asyncio
async def test_tool_errors_and_credential_echo_are_redacted():
    async def fail(**_):
        raise RuntimeError("synthetic-secret")

    async def echo(**_):
        return {"text": "synthetic-secret"}

    for call in (fail, echo):
        with pytest.raises(managed_mcp.ManagedMcpError) as error:
            await managed_mcp._guard_call(call, ("synthetic-secret",))()
        assert str(error.value) == "mcp_tool_unavailable"
        assert error.value.__context__ is None


def test_native_mcp_catalog_cannot_claim_central_identity():
    from fred_sdk.resources.mcp import McpCatalog

    with pytest.raises(ValueError, match="reserved"):
        McpCatalog.model_validate(
            {
                "servers": [
                    {
                        "id": binding().capability_id,
                        "name": "spoof",
                        "transport": "streamable_http",
                        "url": "https://tools.invalid/mcp",
                    }
                ]
            }
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"mcp_server_id": binding().capability_id},
        {
            "mcp_server_id": "mcp-knowledge-flow-mcp-tabular",
            "mcp_trusted_service": "knowledge_flow_tabular",
            "mcp_connection_id": None,
        },
    ],
)
def test_managed_tools_never_infer_document_workspace_or_session_context(metadata):
    from fred_runtime.common.context_aware_tool import ContextAwareTool
    from langchain_core.tools import StructuredTool

    async def call(**_):
        return "done"

    def forbidden_context():
        raise AssertionError("Managed MCP must not read Fred context for injection")

    tool = StructuredTool(
        name="central",
        description="Provider tool",
        args_schema={
            "type": "object",
            "properties": {
                "space_id": {"type": "string"},
                "session_id": {"type": "string"},
                "document_uids": {"type": "array"},
            },
        },
        coroutine=call,
        metadata=metadata,
    )
    wrapped = ContextAwareTool(tool, forbidden_context, forbidden_context)
    assert wrapped._inject_context_if_needed({}) == {}


@pytest.mark.asyncio
async def test_listing_timeout_is_bounded_and_closes_client(monkeypatch):
    FakeClient.gate = asyncio.Event()
    timeout = asyncio.timeout
    monkeypatch.setattr(managed_mcp.asyncio, "timeout", lambda _: timeout(0.01))
    with pytest.raises(managed_mcp.ManagedMcpError, match="connection_unavailable"):
        await managed_mcp.connect([binding()], [])
    assert FakeClient.instances[0].closed == 1


def delegated_provider(person="alice", run="run-a", agent="agent-a"):
    from fred_core.security.backend_to_backend_auth import TokenLease
    from fred_core.security.delegation import DelegationConfig
    from fred_runtime.common.outbound_credentials import DelegationRuntime, RunRecord

    class Tokens(StaticWorkloadTokens):
        calls = 0
        refreshes = 0

        async def get_token_lease(self):
            self.calls += 1
            return TokenLease(
                token="workload-new" if self.refreshes else "workload-old",
                generation=self.refreshes,
            )

        async def refresh_rejected(self, lease):
            self.refreshes += 1
            return await self.get_token_lease()

    tokens = Tokens()
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True), token_provider=tokens
    )
    runtime.records.admit(RunRecord(run_id=run, person_id=person, agent_id=agent))
    return runtime.provider_for(run_id=run, agent_id=agent), tokens


def test_trusted_service_requires_exact_locally_configured_destination():
    trusted = McpTabularBinding(
        url="https://kf.invalid/api/mcp/tabular",
    )
    for base in (
        None,
        "https://attacker.invalid/api",
        "https://kf.invalid/other",
        "https://kf.invalid/api?grant=forged",
    ):
        with pytest.raises(managed_mcp.ManagedMcpError, match="destination_mismatch"):
            managed_mcp.validate_admission(
                [trusted.capability_id],
                [trusted],
                compatible=True,
                credentials=[],
                knowledge_flow_url=base,
            )
    managed_mcp.validate_admission(
        [trusted.capability_id],
        [trusted],
        compatible=True,
        credentials=[],
        knowledge_flow_url="https://kf.invalid/api/",
    )
    external = binding(url=trusted.url)
    assert managed_mcp.trusted_destination(external, "https://kf.invalid/api") is False
    assert managed_mcp.credential_headers(external, []) == {}


@pytest.mark.asyncio
async def test_one_service_clients_keep_two_pod_turns_isolated_and_external_has_no_fred_context(
    monkeypatch,
):
    from langchain_core.tools import StructuredTool

    FakeClient.pages = [page([remote("list_tabular_documents"), remote()])]

    async def convert(tool, client):
        async def call(**kwargs):
            client.calls.append((tool.name, kwargs))
            return "ok"

        return StructuredTool(
            name=tool.name,
            description="Knowledge Flow Tabular",
            args_schema={},
            coroutine=call,
            metadata={
                "mcp_trusted_service": "knowledge_flow_tabular",
                "mcp_service": "knowledge_flow",
                "mcp_delegated": True,
            },
        )

    monkeypatch.setattr(managed_mcp, "as_langchain_tool", convert)
    admitted = McpTabularBinding(
        url="https://kf.invalid/api/mcp/tabular",
    )
    providers = [
        delegated_provider("alice", "run-a", "agent-pod-a"),
        delegated_provider("bob", "run-b", "agent-pod-b"),
    ]
    result = await asyncio.gather(
        *[
            managed_mcp.connect(
                [admitted],
                [],
                knowledge_flow_url="https://kf.invalid/api",
                provider=provider,
                document_context=lambda person=person: (
                    '{"space_id":"' + person + '","attachment_ids":[]}'
                ),
            )
            for (provider, _), person in zip(
                providers, ("space-a", "space-b"), strict=True
            )
        ]
    )
    assert result[0][0] is not result[1][0]
    for index, tools in enumerate(result):
        assert tools[0].name == "list_tabular_documents"
        assert await tools[0].ainvoke({}) == "ok"
        assert FakeClient.instances[index].calls == [("list_tabular_documents", {})]
    seen = []

    async def receive(request):
        seen.append((str(request.url), dict(request.headers)))
        return httpx2.Response(200)

    for client in FakeClient.instances:
        async with httpx2.AsyncClient(
            auth=client.transport.auth, transport=httpx2.MockTransport(receive)
        ) as http:
            await http.post(client.transport.url, json={"method": "tools/call"})
    assert "person=alice" in seen[0][0] and "agent=agent-pod-a" in seen[0][0]
    assert "person=bob" in seen[1][0] and "agent=agent-pod-b" in seen[1][0]
    assert "space-a" in seen[0][1]["x-fred-document-context"]
    assert "space-b" in seen[1][1]["x-fred-document-context"]
    trusted_metadata = result[0][0].metadata
    assert trusted_metadata is not None
    assert trusted_metadata["mcp_trusted_service"] == "knowledge_flow_tabular"

    # A matching URL, display name or server annotation is never service identity.
    external = binding(url=admitted.url).model_copy(
        update={"display_name": "Knowledge Flow Tabular"}
    )
    external_tools = await managed_mcp.connect(
        [external],
        [],
        knowledge_flow_url="https://kf.invalid/api",
        provider=providers[0][0],
        document_context=lambda: "private",
    )
    client = FakeClient.instances[-1]
    assert client.transport.auth is None
    assert "person=" not in str(client.transport.url)
    external_metadata = external_tools[0].metadata
    assert external_metadata is not None
    assert external_metadata["mcp_trusted_service"] is None
    assert external_metadata["mcp_service"] is None
    assert external_metadata["mcp_delegated"] is False
    assert all(tokens.calls == 1 for _, tokens in providers)  # per-request lease only


@pytest.mark.asyncio
async def test_trusted_auth_renews_without_readmission_and_refuses_destination_changes():
    from fred_runtime.common.mcp_http_auth import MCPHTTPAuth
    from fred_runtime.common.mcp_utils import _mcp_http_client_factory
    from fred_runtime.runtime_support.authority import AuthorityLostError
    from mcp.shared._httpx_utils import request_within_origin

    provider, tokens = delegated_provider()
    seen = []
    endpoint = "https://kf.invalid/api/mcp/tabular?person=alice&run=run-a&agent=agent-a"
    auth = MCPHTTPAuth(
        provider, document_context=lambda: '{"attachment_ids":[]}', destination=endpoint
    )

    async def receive(request):
        seen.append((str(request.url), request.headers.get("authorization")))
        if len(seen) == 1:
            return httpx2.Response(401)
        return httpx2.Response(
            307, headers={"Location": "https://external.invalid/mcp"}
        )

    client = _mcp_http_client_factory(auth=auth)
    client._transport = httpx2.MockTransport(receive)
    async with client:
        with pytest.raises(httpx2.TooManyRedirects, match="redirect refused"):
            await request_within_origin(
                client, "POST", endpoint, json={"method": "tools/call"}
            )
        with pytest.raises(AuthorityLostError):
            await client.post("https://external.invalid/mcp", json={})
    assert seen == [
        (endpoint, "Bearer workload-old"),
        (endpoint, "Bearer workload-new"),
    ]
    assert tokens.refreshes == 1


@pytest.mark.asyncio
async def test_trusted_service_without_admitted_context_fails_before_connecting():
    admitted = McpTabularBinding(
        url="https://kf.invalid/api/mcp/tabular",
    )
    with pytest.raises(managed_mcp.ManagedMcpError, match="delegated_context_required"):
        await managed_mcp.connect(
            [admitted], [], knowledge_flow_url="https://kf.invalid/api"
        )
    assert FakeClient.instances == []


@pytest.mark.asyncio
async def test_trusted_calls_preserve_authority_stops_and_curated_sql_failures():
    from fred_runtime.common.context_aware_tool import _build_tool_error_message
    from fred_runtime.runtime_support.authority import AuthorityLostError

    async def refused(**_):
        raise RuntimeError("Tool access was refused.")

    with pytest.raises(AuthorityLostError):
        await managed_mcp._guard_call(refused, trusted_tool="query_tabular_documents")()

    failure = RuntimeError(
        'Error calling query_tabular_documents. Status code: 400. Response: {"detail":"Unknown column. Inspect the table schema."}'
    )

    async def invalid_query(**_):
        raise failure

    with pytest.raises(RuntimeError) as error:
        await managed_mcp._guard_call(
            invalid_query, trusted_tool="query_tabular_documents"
        )()
    assert error.value is failure
    assert (
        _build_tool_error_message(
            error.value, None, tool_name="query_tabular_documents"
        )
        == "Error: Unknown column. Inspect the table schema."
    )

    async def transport_failure(**_):
        raise RuntimeError(
            "transport failed at https://kf.invalid/?person=private&run=private"
        )

    with pytest.raises(managed_mcp.ManagedMcpError) as error:
        await managed_mcp._guard_call(
            transport_failure, trusted_tool="query_tabular_documents"
        )()
    assert str(error.value) == "mcp_tool_unavailable"
    assert error.value.__context__ is None
