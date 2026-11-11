# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Managed MCP admission and per-turn execution. Local fakes, never real credentials."""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from fred_sdk.contracts.managed_mcp import McpBinding, McpCredentialBinding, McpTool
from fred_runtime.common import managed_mcp
from fred_runtime.capabilities.registry import CapabilityRegistry
from mcp.types import TextContent, Tool

ID = UUID("8cfd2a56-2d35-4d18-b67c-5e42b0a9c122")


def binding(*, revision=1, auth=None, url="https://tools.invalid/mcp"):
    return McpBinding.model_validate(
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
    gate = None

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
        secret_env="FRED_TEST_MCP_KEY",
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
    second = await managed_mcp.connect([binding(revision=2)], [])
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
    first = binding().model_copy(update={"tools": published})
    other_id = UUID("affd2a56-2d35-4d18-b67c-5e42b0a9c122")
    second = first.model_copy(
        update={
            "connection_id": other_id,
            "capability_id": f"managed-mcp:{other_id}",
            "tools": published[:1],
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
async def test_http_uses_only_provider_key_and_refuses_redirect(monkeypatch):
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
    factory = managed_mcp._client_factory({"x-api-key": "synthetic-secret"})
    client = factory(headers={"Accept": "application/json"}, follow_redirects=True)
    async with client:
        with pytest.raises(httpx2.TooManyRedirects):
            await client.post("https://tools.invalid/mcp")
    assert len(seen) == 1
    assert seen[0].headers["x-api-key"] == "synthetic-secret"
    assert "authorization" not in seen[0].headers
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


def test_managed_tools_never_infer_document_workspace_or_session_context():
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
        metadata={"mcp_server_id": binding().capability_id},
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
