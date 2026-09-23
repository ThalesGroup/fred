# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Which tool servers a delegated run may use, and what it sends them.

Activation is the decision point: a server that cannot receive a grant is not
activated at all, rather than being called with a credential it should not get.
For the servers that can, the grant travels on the endpoint — outside the tool's
own arguments, where no model output can reach it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, cast

import httpx
import pytest
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
)
from fred_runtime.common import mcp_runtime, mcp_utils
from fred_runtime.common.mcp_interceptors import DelegatedAuthorityInterceptor
from fred_runtime.common.mcp_runtime import _mcp_cache_key
from fred_runtime.common.outbound_credentials import (
    OutboundCredentialProvider,
    OutboundCredentials,
    static_person_provider,
)
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration, MCPServerRef
from langchain_mcp_adapters import tools as mcp_adapter_tools
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from mcp.types import CallToolResult, TextContent, Tool

UPSTREAM_MARKER = "upstream-detail-marker"
PERSON_BEARER = "Bearer person-token"
WORKLOAD_BEARER = "Bearer workload-token"


class DelegatedProvider(OutboundCredentialProvider):
    """A provider already admitted for one run, with a rotatable bearer."""

    delegated = True

    def __init__(
        self,
        *,
        person: str = "alice",
        run: str = "run-7",
        agent: str = "agent-a",
        authorization: str = WORKLOAD_BEARER,
    ) -> None:
        self.parameters = {
            GRANT_PARAM_PERSON: person,
            GRANT_PARAM_RUN: run,
            GRANT_PARAM_AGENT: agent,
        }
        self.authorization = authorization
        self.asked = 0

    async def credentials(self, *, override_token: str | None = None):
        self.asked += 1
        return OutboundCredentials(
            authorization=self.authorization,
            parameters=dict(self.parameters),
            delegated=True,
        )

    def for_agent(self, agent_id: str) -> "DelegatedProvider":
        return DelegatedProvider(
            person=self.parameters[GRANT_PARAM_PERSON],
            run=self.parameters[GRANT_PARAM_RUN],
            agent=agent_id,
            authorization=self.authorization,
        )


def server(
    auth_mode: str,
    *,
    transport: str = "streamable_http",
    url: str = "http://kf.invalid/mcp",
) -> MCPServerConfiguration:
    return MCPServerConfiguration.model_validate(
        {
            "id": "kf-mcp",
            "name": "kf",
            "transport": transport,
            "url": url,
            "enabled": True,
            "auth_mode": auth_mode,
        }
    )


@pytest.fixture
def connections(monkeypatch) -> dict[str, Any]:
    """Capture what the adapter would connect with, without connecting."""
    captured: dict[str, Any] = {}

    class _FakeMultiServerClient:
        def __init__(self, conns, tool_interceptors=None) -> None:
            captured.update(conns)
            self.tool_interceptors = list(tool_interceptors or [])

        async def get_tools(self, server_name: str):
            return []

    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", _FakeMultiServerClient)
    return captured


async def connect(
    servers: list[MCPServerConfiguration],
    *,
    credentials: OutboundCredentialProvider,
    access_token: str | None = None,
):
    return await mcp_utils.get_connected_mcp_client_for_agent(
        agent_id="agent-a",
        mcp_servers=servers,
        runtime_context=RuntimeContext(access_token=access_token),
        credentials=credentials,
    )


# ---------------------------------------------------------------------------
# Activation under the flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_delegated_server_receives_the_workload_bearer_and_the_grant(
    connections,
):
    await connect([server("delegated")], credentials=DelegatedProvider())

    connection = connections["kf-mcp"]
    assert connection["headers"]["Authorization"] == WORKLOAD_BEARER
    assert "person=alice" in connection["url"]
    assert "run=run-7" in connection["url"]
    assert "agent=agent-a" in connection["url"]


@pytest.mark.asyncio
async def test_the_grant_travels_outside_the_tools_arguments(connections):
    """It is on the endpoint, so a tool schema never carries it and a model can
    never write it."""
    await connect([server("delegated")], credentials=DelegatedProvider())

    connection = connections["kf-mcp"]
    assert connection["url"].startswith("http://kf.invalid/mcp?")
    assert set(connection["headers"]) == {"Authorization"}


@pytest.mark.asyncio
async def test_a_user_token_server_is_refused_under_delegation(connections):
    with pytest.raises(DelegationUnavailableError) as raised:
        await connect([server("user_token")], credentials=DelegatedProvider())

    assert raised.value.reason == "delegation_unavailable"
    assert connections == {}  # nothing was connected, so no bearer was sent


@pytest.mark.asyncio
async def test_a_no_token_server_is_unchanged_under_delegation(connections):
    await connect([server("no_token")], credentials=DelegatedProvider())

    assert connections["kf-mcp"].get("headers") in (None, {})


@pytest.mark.asyncio
async def test_a_transport_that_cannot_carry_the_grant_is_refused(connections):
    with pytest.raises(DelegationUnavailableError):
        await connect(
            [server("delegated", transport="stdio")], credentials=DelegatedProvider()
        )

    assert connections == {}


@pytest.mark.asyncio
async def test_a_refused_server_exposes_no_identifier_to_logs_or_the_run(
    connections, caplog
):
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        with pytest.raises(DelegationUnavailableError) as raised:
            await connect([server("user_token")], credentials=DelegatedProvider())

    assert "kf-mcp" not in caplog.text
    assert "kf-mcp" not in str(raised.value)


@pytest.mark.asyncio
async def test_the_grant_is_kept_out_of_the_connection_logs(connections):
    with recorded_logs() as logs:
        await connect([server("delegated")], credentials=DelegatedProvider())

    assert logs.lines
    assert not [
        line
        for line in logs.lines
        if "kf.invalid/mcp" in line
        or "kf-mcp" in line
        or "alice" in line
        or "run-7" in line
        or "agent-a" in line
    ]


# ---------------------------------------------------------------------------
# Activation with the flag off — unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_flag_off_a_user_token_server_still_gets_the_person(connections):
    await connect(
        [server("user_token")],
        credentials=static_person_provider("person-token"),
        access_token="person-token",
    )

    connection = connections["kf-mcp"]
    assert connection["headers"]["Authorization"] == PERSON_BEARER
    assert connection["url"] == "http://kf.invalid/mcp"


@pytest.mark.asyncio
async def test_with_the_flag_off_a_delegated_entry_still_gets_the_person(connections):
    """The rollout depends on it: a catalog entry switched to `delegated` before
    the flag is on keeps working, on the person's own bearer and no parameters."""
    await connect(
        [server("delegated")],
        credentials=static_person_provider("person-token"),
        access_token="person-token",
    )

    connection = connections["kf-mcp"]
    assert connection["headers"]["Authorization"] == PERSON_BEARER
    assert connection["url"] == "http://kf.invalid/mcp"


@pytest.mark.asyncio
async def test_with_the_flag_off_a_no_token_server_still_gets_nothing(connections):
    await connect(
        [server("no_token")],
        credentials=static_person_provider("person-token"),
        access_token="person-token",
    )

    assert connections["kf-mcp"].get("headers") in (None, {})


# ---------------------------------------------------------------------------
# One connection per run, never shared between people
# ---------------------------------------------------------------------------


def test_two_people_never_share_a_cached_connection():
    servers = [server("delegated")]
    alice = OutboundCredentials(
        authorization=WORKLOAD_BEARER,
        parameters={
            GRANT_PARAM_PERSON: "alice",
            GRANT_PARAM_RUN: "run-1",
            GRANT_PARAM_AGENT: "agent-a",
        },
        delegated=True,
    )
    bob = OutboundCredentials(
        authorization=WORKLOAD_BEARER,
        parameters={
            GRANT_PARAM_PERSON: "bob",
            GRANT_PARAM_RUN: "run-2",
            GRANT_PARAM_AGENT: "agent-a",
        },
        delegated=True,
    )

    assert _mcp_cache_key("agent-a", servers, alice) != _mcp_cache_key(
        "agent-a", servers, bob
    )


def test_the_same_grant_always_yields_the_same_key():
    servers = [server("delegated")]
    credentials = OutboundCredentials(
        authorization=WORKLOAD_BEARER,
        parameters={
            GRANT_PARAM_PERSON: "alice",
            GRANT_PARAM_RUN: "run-1",
            GRANT_PARAM_AGENT: "agent-a",
        },
        delegated=True,
    )

    assert _mcp_cache_key("agent-a", servers, credentials) == _mcp_cache_key(
        "agent-a", servers, credentials
    )


@pytest.fixture
def empty_client_cache():
    """The connection cache is process-wide; leave it as the test found it."""
    mcp_runtime._mcp_client_cache.clear()
    yield mcp_runtime._mcp_client_cache
    mcp_runtime._mcp_client_cache.clear()


class _ConnectedClient:
    """What a connect returns: the interceptor list the runtime mutates in place."""

    def __init__(self) -> None:
        self.tool_interceptors: list[Any] = []


@pytest.mark.asyncio
async def test_a_delegated_connection_is_not_kept(monkeypatch, empty_client_cache):
    """Its grant names one run, so no later turn could ever reuse it; keeping it
    would only hold a connection's tools until the entry expired."""
    connected = _ConnectedClient()

    async def _connect(**kwargs: Any):
        return connected, []

    monkeypatch.setattr(mcp_runtime, "get_connected_mcp_client_for_agent", _connect)

    client, _ = await mcp_runtime._get_or_connect_mcp_client(
        agent_id="agent-a",
        mcp_servers=[server("delegated")],
        runtime_context=RuntimeContext(),
        tool_interceptors=[],
        credentials=DelegatedProvider(),
    )

    assert client is connected
    assert len(empty_client_cache) == 0


@pytest.mark.asyncio
async def test_with_the_flag_off_a_connection_is_still_kept(
    monkeypatch, empty_client_cache
):
    connected = _ConnectedClient()

    async def _connect(**kwargs: Any):
        return connected, []

    monkeypatch.setattr(mcp_runtime, "get_connected_mcp_client_for_agent", _connect)

    await mcp_runtime._get_or_connect_mcp_client(
        agent_id="agent-a",
        mcp_servers=[server("user_token")],
        runtime_context=RuntimeContext(),
        tool_interceptors=[],
        credentials=static_person_provider("alice-token"),
    )

    assert len(empty_client_cache) == 1


def test_with_the_flag_off_the_key_is_still_the_bearer():
    servers = [server("user_token")]
    first = OutboundCredentials(authorization="Bearer alice-token")
    second = OutboundCredentials(authorization="Bearer bob-token")

    assert _mcp_cache_key("agent-a", servers, first) != _mcp_cache_key(
        "agent-a", servers, second
    )


# ---------------------------------------------------------------------------
# Tool calls on an established connection
# ---------------------------------------------------------------------------


def tool_request(headers: dict[str, str] | None = None) -> MCPToolCallRequest:
    return MCPToolCallRequest(
        name="kf.search",
        args={"question": "q"},
        server_name="kf-mcp",
        headers=headers,
    )


def refusal(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://kf.invalid/mcp")
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=httpx.Response(status_code, text=UPSTREAM_MARKER, request=request),
    )


@pytest.mark.asyncio
async def test_every_tool_call_carries_a_current_bearer():
    """The connection was opened with the token of the moment; a later call must
    not be sent with it once the provider has moved on."""
    provider = DelegatedProvider()
    interceptor = DelegatedAuthorityInterceptor(
        provider, delegated_server_ids={"kf-mcp"}
    )
    seen: list[dict[str, Any]] = []

    async def _handler(request: MCPToolCallRequest):
        seen.append(dict(request.headers or {}))
        return "ok"

    await interceptor(tool_request({"Authorization": "Bearer stale-token"}), _handler)
    provider.authorization = "Bearer workload-token-2"
    await interceptor(tool_request({"Authorization": "Bearer stale-token"}), _handler)

    assert [headers["Authorization"] for headers in seen] == [
        WORKLOAD_BEARER,
        "Bearer workload-token-2",
    ]


@pytest.mark.parametrize("status_code", [401, 403])
@pytest.mark.asyncio
async def test_a_refused_tool_call_ends_the_run_without_a_retry(status_code: int):
    provider = DelegatedProvider()
    interceptor = DelegatedAuthorityInterceptor(
        provider, delegated_server_ids={"kf-mcp"}
    )
    attempts = 0

    async def _handler(request: MCPToolCallRequest):
        nonlocal attempts
        attempts += 1
        raise refusal(status_code)

    with pytest.raises(AuthorityLostError) as raised:
        await interceptor(tool_request(), _handler)

    assert attempts == 1
    assert UPSTREAM_MARKER not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.asyncio
async def test_an_ordinary_tool_failure_is_left_alone():
    interceptor = DelegatedAuthorityInterceptor(
        DelegatedProvider(), delegated_server_ids={"kf-mcp"}
    )

    async def _handler(request: MCPToolCallRequest):
        raise refusal(500)

    with pytest.raises(httpx.HTTPStatusError):
        await interceptor(tool_request(), _handler)


@pytest.mark.asyncio
async def test_a_run_whose_record_is_gone_makes_no_tool_call():
    class _NoRecordProvider(OutboundCredentialProvider):
        delegated = True

        async def credentials(self, *, override_token: str | None = None):
            raise DelegationUnavailableError("This run has no admission record.")

        def for_agent(self, agent_id: str):
            return self

    interceptor = DelegatedAuthorityInterceptor(
        _NoRecordProvider(), delegated_server_ids={"kf-mcp"}
    )
    called = False

    async def _handler(request: MCPToolCallRequest):
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(DelegationUnavailableError):
        await interceptor(tool_request(), _handler)

    assert called is False


@pytest.mark.asyncio
async def test_converted_no_token_tool_never_receives_delegated_bearer(monkeypatch):
    """Exercise the adapter path that merges interceptor headers into the
    HTTP connection used for each converted tool call."""
    provider = DelegatedProvider()
    interceptor = DelegatedAuthorityInterceptor(
        provider, delegated_server_ids={"delegated-mcp"}
    )
    opened_connections: list[dict[str, Any]] = []

    class _Session:
        async def initialize(self) -> None:
            pass

        async def call_tool(self, name, args, progress_callback=None):
            return CallToolResult(content=[TextContent(type="text", text="ok")])

    @asynccontextmanager
    async def _capture_session(connection, **kwargs):
        opened_connections.append(dict(connection))
        yield _Session()

    monkeypatch.setattr(mcp_adapter_tools, "create_session", _capture_session)
    tool = Tool(
        name="search",
        description="Synthetic search tool",
        inputSchema={"type": "object", "properties": {}},
    )
    connection: StreamableHttpConnection = {
        "transport": "streamable_http",
        "url": "http://tools.invalid/mcp",
    }

    no_token_tool = mcp_adapter_tools.convert_mcp_tool_to_langchain_tool(
        None,
        tool,
        connection=connection,
        tool_interceptors=[interceptor],
        server_name="no-token-mcp",
    )
    await no_token_tool.ainvoke({})

    assert opened_connections[-1].get("headers") in (None, {})
    assert provider.asked == 0

    delegated_tool = mcp_adapter_tools.convert_mcp_tool_to_langchain_tool(
        None,
        tool,
        connection=connection,
        tool_interceptors=[interceptor],
        server_name="delegated-mcp",
    )
    await delegated_tool.ainvoke({})

    assert opened_connections[-1]["headers"]["Authorization"] == WORKLOAD_BEARER
    assert provider.asked == 1


# ---------------------------------------------------------------------------
# A receiver that refuses the tool listing
# ---------------------------------------------------------------------------


class _RecordingHandler(logging.Handler):
    """Every line as a reader would see it, rendered tracebacks included."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(logging.Formatter().format(record))


@contextmanager
def recorded_logs() -> Iterator[_RecordingHandler]:
    """Read what the pod's own handlers would write, which `caplog` stops
    seeing once the runtime has installed its logging setup."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.setLevel(level)
        root.removeHandler(handler)


GRANTED_ENDPOINT = "http://kf.invalid/mcp?person=alice&run=run-7&agent=agent-a"


def refusing_client(status: int | None, *, transport_error: bool = False):
    """A `MultiServerMCPClient` whose tool listing fails the way the adapter's
    does: the HTTP error the SDK raises from `raise_for_status`, quoting the
    endpoint it called."""
    instances: list[Any] = []

    class _FakeMultiServerClient:
        def __init__(self, conns, tool_interceptors=None) -> None:
            self.connections = conns
            self.tool_interceptors = list(tool_interceptors or [])
            self.calls = 0
            instances.append(self)

        async def get_tools(self, server_name: str):
            self.calls += 1
            request = httpx.Request("POST", GRANTED_ENDPOINT)
            if transport_error:
                raise httpx.ConnectError("connection refused", request=request)
            response = httpx.Response(status or 500, request=request, text="refused")
            raise httpx.HTTPStatusError(
                f"Client error '{status} Refused' for url '{GRANTED_ENDPOINT}'",
                request=request,
                response=response,
            )

    return _FakeMultiServerClient, instances


class _AgentSettings:
    id = "agent-a"
    team_id: str | None = "team-1"
    tuning = None
    active_mcp_servers = (MCPServerRef(id="kf-mcp"),)


class _McpCatalog:
    """The pod's MCP catalog as the runtime reads it: one enabled server."""

    def __init__(self, entry: MCPServerConfiguration) -> None:
        self.servers = [entry]

    def get_server(self, id: str) -> MCPServerConfiguration | None:
        return self.servers[0] if id == self.servers[0].id else None


class _AgentShim:
    """The agent context an MCP runtime binds to."""

    def __init__(
        self,
        *,
        provider: OutboundCredentialProvider | None,
        token: str | None = None,
    ) -> None:
        self.runtime_context = RuntimeContext(access_token=token)
        self.agent_settings = _AgentSettings()
        self.credential_provider = provider

    async def refresh_user_access_token(self) -> str:
        return "refreshed-person-token"


async def init_mcp_runtime(
    monkeypatch,
    *,
    client_cls: Any,
    provider: OutboundCredentialProvider | None,
    auth_mode: str,
    token: str | None = None,
) -> None:
    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", client_cls)
    monkeypatch.setattr(mcp_runtime, "MCP_CONNECT_RETRY_BASE_DELAY_SECS", 0.0)
    set_runtime_context(
        FredRuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.invalid/kf/v1",
                mcp_configuration=_McpCatalog(server(auth_mode)),
            )
        )
    )
    runtime: mcp_runtime.MCPRuntime | None = None
    try:
        runtime = mcp_runtime.MCPRuntime(
            agent=cast(Any, _AgentShim(provider=provider, token=token))
        )
        await runtime.init()
    finally:
        if runtime is not None:
            await runtime.aclose()
        set_runtime_context(None)


@pytest.mark.asyncio
async def test_no_token_only_runtime_never_asks_the_workload_provider(
    monkeypatch, empty_client_cache
):
    class _FailingDelegatedProvider(OutboundCredentialProvider):
        delegated = True

        async def credentials(self, *, override_token: str | None = None):
            raise AssertionError("no_token initialization requested credentials")

        def for_agent(self, agent_id: str):
            return self

    class _NoTokenClient:
        def __init__(self, conns, tool_interceptors=None) -> None:
            self.connections = conns
            self.tool_interceptors = list(tool_interceptors or [])

        async def get_tools(self, server_name: str):
            return []

    await init_mcp_runtime(
        monkeypatch,
        client_cls=_NoTokenClient,
        provider=_FailingDelegatedProvider(),
        auth_mode="no_token",
    )


@pytest.mark.asyncio
async def test_a_refused_tool_listing_ends_the_run_at_once(
    monkeypatch, empty_client_cache
):
    """A receiver that will not act for this person any more is not asked again
    under the platform's own identity, and its answer ends the run typed."""
    client_cls, instances = refusing_client(401)

    with recorded_logs() as logs:
        with pytest.raises(AuthorityLostError) as raised:
            await init_mcp_runtime(
                monkeypatch,
                client_cls=client_cls,
                provider=DelegatedProvider(),
                auth_mode="delegated",
            )

    assert raised.value.reason == "authority_lost"
    assert [instance.calls for instance in instances] == [1]
    assert "alice" not in str(raised.value)
    assert not [line for line in logs.lines if "alice" in line]
    assert [line for line in logs.lines if "reason=authority_refused" in line]


@pytest.mark.asyncio
async def test_a_receiver_that_is_merely_unwell_is_still_retried(
    monkeypatch, empty_client_cache
):
    client_cls, instances = refusing_client(503)

    with pytest.raises(mcp_utils.MCPConnectionError) as raised:
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=DelegatedProvider(),
            auth_mode="delegated",
        )

    assert sum(instance.calls for instance in instances) == 3
    assert "person=alice" not in str(raised.value)


@pytest.mark.asyncio
async def test_a_transport_failure_is_still_retried(monkeypatch, empty_client_cache):
    client_cls, instances = refusing_client(None, transport_error=True)

    with pytest.raises(mcp_utils.MCPConnectionError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=DelegatedProvider(),
            auth_mode="delegated",
        )

    assert sum(instance.calls for instance in instances) == 3


@pytest.mark.asyncio
async def test_with_the_flag_off_a_refused_listing_keeps_its_retries(
    monkeypatch, empty_client_cache
):
    """Nothing changes for a person's own token: a 401 there is an expiry to
    recover from, not an authority the platform has lost."""
    client_cls, instances = refusing_client(401)

    with pytest.raises(mcp_utils.MCPConnectionError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=None,
            auth_mode="user_token",
            token="person-token",
        )

    assert sum(instance.calls for instance in instances) == 3
