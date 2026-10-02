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

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from conftest import (
    MockIdentityProvider,
    StaticWorkloadTokens,
    admitted_provider,
)
from fred_core.logs.context import log_context
from fred_core.logs.propagation import CONTEXT_HEADER, decode_log_context
from fred_core.security.backend_to_backend_auth import M2MBearerAuth
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    DelegationConfig,
)
from fred_runtime.common import mcp_runtime, mcp_utils
from fred_runtime.common.mcp_interceptors import (
    DelegatedAuthorityInterceptor,
    LivePersonBearerInterceptor,
)
from fred_runtime.common.mcp_runtime import _mcp_cache_key
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationRuntime,
    OutboundCredentialProvider,
    OutboundCredentials,
    PersonCredentialProvider,
    RunRecord,
    static_person_provider,
)
from fred_runtime.common.tool_node_utils import create_mcp_tool_node
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import MCPServerConfiguration, MCPServerRef
from langchain_core.messages import AIMessage
from langchain_mcp_adapters import sessions as mcp_sessions
from langchain_mcp_adapters import tools as mcp_adapter_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from langgraph.graph import END, START, MessagesState, StateGraph
from mcp.types import CallToolResult, TextContent, Tool

UPSTREAM_MARKER = "upstream-detail-marker"
PERSON_BEARER = "Bearer person-token"
WORKLOAD_BEARER = "Bearer workload-token"


def delegated_provider() -> DelegatedCredentialProvider:
    """A real provider admitted for one run: alice, run-7, agent-a."""
    return admitted_provider(StaticWorkloadTokens())


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
async def test_a_delegated_server_gets_the_bearer_adapter_and_the_grant(
    connections, monkeypatch
):
    """The connection holds no bearer of its own: the adapter takes one per
    request, so building it acquires nothing."""
    identity = MockIdentityProvider(monkeypatch)
    await connect(
        [server("delegated")], credentials=admitted_provider(identity.provider)
    )

    connection = connections["kf-mcp"]
    assert isinstance(connection["auth"], M2MBearerAuth)
    assert "headers" not in connection
    assert identity.acquisitions == 0
    assert "person=alice" in connection["url"]
    assert "run=run-7" in connection["url"]
    assert "agent=agent-a" in connection["url"]


@pytest.mark.asyncio
async def test_the_grant_travels_outside_the_tools_arguments(connections):
    """It is on the endpoint, so a tool schema never carries it and a model can
    never write it."""
    await connect([server("delegated")], credentials=delegated_provider())

    connection = connections["kf-mcp"]
    assert connection["url"].startswith("http://kf.invalid/mcp?")
    assert "headers" not in connection


@pytest.mark.asyncio
async def test_a_user_token_server_is_refused_under_delegation(connections):
    with pytest.raises(DelegationUnavailableError) as raised:
        await connect([server("user_token")], credentials=delegated_provider())

    assert raised.value.reason == "delegation_unavailable"
    assert connections == {}  # nothing was connected, so no bearer was sent


@pytest.mark.asyncio
async def test_a_no_token_server_is_unchanged_under_delegation(connections):
    await connect([server("no_token")], credentials=delegated_provider())

    assert connections["kf-mcp"].get("headers") in (None, {})
    assert "auth" not in connections["kf-mcp"]


@pytest.mark.asyncio
async def test_a_transport_that_cannot_carry_the_grant_is_refused(connections):
    with pytest.raises(DelegationUnavailableError):
        await connect(
            [server("delegated", transport="stdio")], credentials=delegated_provider()
        )

    assert connections == {}


@pytest.mark.asyncio
async def test_a_refused_server_exposes_no_identifier_to_logs_or_the_run(
    connections, caplog
):
    caplog.clear()
    with caplog.at_level(logging.ERROR):
        with pytest.raises(DelegationUnavailableError) as raised:
            await connect([server("user_token")], credentials=delegated_provider())

    assert "kf-mcp" not in caplog.text
    assert "kf-mcp" not in str(raised.value)


@pytest.mark.asyncio
async def test_the_grant_is_kept_out_of_the_connection_logs(connections):
    with recorded_logs() as logs:
        await connect([server("delegated")], credentials=delegated_provider())

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
    assert "auth" not in connection


@pytest.mark.asyncio
async def test_user_token_near_expiry_is_forwarded_without_service_auth(connections):
    context = RuntimeContext(access_token="person-token", access_token_expires_at=0)

    await mcp_utils.get_connected_mcp_client_for_agent(
        agent_id="agent-a",
        mcp_servers=[server("user_token")],
        runtime_context=context,
    )

    assert connections["kf-mcp"]["headers"]["Authorization"] == PERSON_BEARER
    assert "auth" not in connections["kf-mcp"]


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
        credentials=delegated_provider(),
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


def refusal(
    status_code: int, *, account_status_unavailable: bool = False
) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://kf.invalid/mcp")
    headers = (
        {"X-Fred-Denial-Cause": "account_status_unavailable"}
        if account_status_unavailable
        else {}
    )
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=httpx.Response(
            status_code, text=UPSTREAM_MARKER, request=request, headers=headers
        ),
    )


@pytest.mark.asyncio
async def test_own_identity_mcp_calls_read_live_bearer_but_no_token_stays_empty():
    token = "person-first"

    async def current_token() -> str:
        return token

    interceptor = LivePersonBearerInterceptor(
        PersonCredentialProvider(current_token),
        authenticated_server_ids={"kf-mcp"},
    )
    seen: list[dict[str, str]] = []

    async def handler(request: MCPToolCallRequest):
        seen.append(dict(request.headers or {}))
        return "ok"

    await interceptor(tool_request({"Authorization": "Bearer stale"}), handler)
    token = "person-updated"
    await interceptor(tool_request({"Authorization": "Bearer stale"}), handler)
    no_token = MCPToolCallRequest(
        name="kf.search", args={}, server_name="no-token", headers=None
    )
    await interceptor(no_token, handler)
    assert [headers["Authorization"] for headers in seen[:2]] == [
        "Bearer person-first",
        "Bearer person-updated",
    ]
    assert seen[2] == {}


@pytest.mark.asyncio
async def test_mcp_runtime_converted_tool_reads_rotated_person_bearer(
    monkeypatch, empty_client_cache
) -> None:
    opened: list[dict[str, Any]] = []

    class _Client:
        def __init__(self, conns, tool_interceptors=None) -> None:
            self.connections = conns
            self.tool_interceptors = list(tool_interceptors or [])

        async def get_tools(self, server_name: str):
            return []

    class _Session:
        async def initialize(self) -> None:
            pass

        async def call_tool(self, name, args, progress_callback=None):
            return CallToolResult(content=[TextContent(type="text", text="ok")])

    @asynccontextmanager
    async def _capture_session(connection, **kwargs):
        opened.append(dict(connection))
        yield _Session()

    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", _Client)
    monkeypatch.setattr(mcp_adapter_tools, "create_session", _capture_session)
    set_runtime_context(
        FredRuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.invalid/kf/v1",
                mcp_configuration=_McpCatalog(server("user_token")),
            )
        )
    )
    agent = _AgentShim(provider=None, token="person-first")
    runtime = mcp_runtime.MCPRuntime(agent=cast(Any, agent))
    try:
        await runtime.init()
        assert runtime.mcp_client is not None
        tool = mcp_adapter_tools.convert_mcp_tool_to_langchain_tool(
            None,
            Tool(
                name="search",
                description="Synthetic search tool",
                inputSchema={"type": "object", "properties": {}},
            ),
            connection={"transport": "streamable_http", "url": "http://kf.invalid/mcp"},
            tool_interceptors=runtime.mcp_client.tool_interceptors,
            server_name="kf-mcp",
        )
        await tool.ainvoke({})
        agent.runtime_context.access_token = "person-updated"
        await tool.ainvoke({})
    finally:
        await runtime.aclose()
        set_runtime_context(None)

    assert [item["headers"]["Authorization"] for item in opened] == [
        "Bearer person-first",
        "Bearer person-updated",
    ]


@pytest.mark.parametrize("status_code", [401, 403])
@pytest.mark.asyncio
async def test_a_refused_tool_call_ends_the_run_without_a_retry(status_code: int):
    provider = delegated_provider()
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
        delegated_provider(), delegated_server_ids={"kf-mcp"}
    )

    async def _handler(request: MCPToolCallRequest):
        raise refusal(500)

    with pytest.raises(httpx.HTTPStatusError):
        await interceptor(tool_request(), _handler)


@pytest.mark.asyncio
async def test_account_status_unavailable_tool_transport_ends_authority():
    interceptor = DelegatedAuthorityInterceptor(
        delegated_provider(), delegated_server_ids={"kf-mcp"}
    )

    async def _handler(request: MCPToolCallRequest):
        raise refusal(503, account_status_unavailable=True)

    with pytest.raises(AuthorityLostError):
        await interceptor(tool_request(), _handler)


@pytest.mark.asyncio
async def test_structured_mcp_refusal_stops_before_tool_error_conversion():
    interceptor = DelegatedAuthorityInterceptor(
        delegated_provider(), delegated_server_ids={"kf-mcp"}
    )

    async def _handler(request: MCPToolCallRequest):
        return CallToolResult(
            content=[TextContent(type="text", text="Tool access was refused.")],
            structuredContent={"cause": "authority_lost"},
            isError=True,
        )

    with pytest.raises(AuthorityLostError):
        await interceptor(tool_request(), _handler)


@pytest.mark.asyncio
async def test_unstructured_mcp_error_text_does_not_claim_lost_authority():
    interceptor = DelegatedAuthorityInterceptor(
        delegated_provider(), delegated_server_ids={"kf-mcp"}
    )
    result = CallToolResult(
        content=[TextContent(type="text", text='{"cause":"authority_lost"}')],
        isError=True,
    )

    async def _handler(request: MCPToolCallRequest):
        return result

    assert await interceptor(tool_request(), _handler) is result


@pytest.mark.asyncio
async def test_mcp_close_retains_lifecycle_until_teardown_finishes():
    runtime = object.__new__(mcp_runtime.MCPRuntime)
    release = asyncio.Event()
    started = asyncio.Event()

    async def lifecycle() -> None:
        started.set()
        await release.wait()

    runtime._lifecycle_task = asyncio.create_task(lifecycle())
    runtime._stop_event = asyncio.Event()
    runtime._ready_event = asyncio.Event()
    runtime._lifecycle_error = None
    runtime._close_task = None
    runtime._aclose_inprocess_toolkits = AsyncMock()
    close = asyncio.create_task(runtime.aclose())
    await started.wait()
    close.cancel()
    await asyncio.sleep(0)
    assert runtime._lifecycle_task is not None
    close.cancel()
    assert runtime._lifecycle_task is not None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await close
    assert runtime._lifecycle_task is None
    assert runtime._close_task is not None and runtime._close_task.done()
    runtime._aclose_inprocess_toolkits.assert_awaited_once()
    await runtime.aclose()


@pytest.mark.asyncio
async def test_cancelled_mcp_init_keeps_lifecycle_for_later_disposal():
    runtime = object.__new__(mcp_runtime.MCPRuntime)
    release = asyncio.Event()
    started = asyncio.Event()

    async def lifecycle() -> None:
        started.set()
        await release.wait()

    lifecycle_task = asyncio.create_task(lifecycle())
    runtime._lifecycle_task = lifecycle_task
    runtime._stop_event = asyncio.Event()
    runtime._ready_event = asyncio.Event()
    runtime._lifecycle_error = None
    runtime._close_task = None
    runtime._aclose_inprocess_toolkits = AsyncMock()
    waiter = asyncio.create_task(runtime._await_lifecycle_attempt_completion())
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert runtime._lifecycle_task is lifecycle_task
    release.set()
    await runtime.aclose()
    assert lifecycle_task.done()
    assert runtime._lifecycle_task is None


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
async def test_the_tool_gate_adds_no_header_and_stops_only_delegated_calls(
    monkeypatch,
):
    """The bearer comes from the connection's authentication adapter, so the
    interceptor adds none; it refuses an ended run's delegated call before a
    session opens and leaves a no_token server alone."""
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True),
        token_provider=StaticWorkloadTokens(),
    )
    runtime.records.admit(
        RunRecord(run_id="run-7", person_id="alice", agent_id="agent-a")
    )
    interceptor = DelegatedAuthorityInterceptor(
        runtime.provider_for(run_id="run-7", agent_id="agent-a"),
        delegated_server_ids={"delegated-mcp"},
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
    no_token_tool, delegated_tool = (
        mcp_adapter_tools.convert_mcp_tool_to_langchain_tool(
            None,
            tool,
            connection=connection,
            tool_interceptors=[interceptor],
            server_name=server_name,
        )
        for server_name in ("no-token-mcp", "delegated-mcp")
    )

    with log_context(correlation_id="mcp-journey", custom="retained"):
        await no_token_tool.ainvoke({})
        await delegated_tool.ainvoke({})
    assert opened_connections[0] == dict(connection)
    delegated_headers = opened_connections[1]["headers"]
    assert "Authorization" not in delegated_headers
    assert decode_log_context(delegated_headers[CONTEXT_HEADER]) == (
        {"correlation_id": "mcp-journey", "custom": "retained"},
        None,
    )

    runtime.records.mark_terminal("run-7")
    await no_token_tool.ainvoke({})
    with pytest.raises(DelegationUnavailableError):
        await delegated_tool.ainvoke({})
    assert len(opened_connections) == 3


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


def refusing_client(
    status: int | None,
    *,
    transport_error: bool = False,
    account_status_unavailable: bool = False,
):
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
            response = httpx.Response(
                status or 500,
                request=request,
                text="refused",
                headers=(
                    {"X-Fred-Denial-Cause": "account_status_unavailable"}
                    if account_status_unavailable
                    else {}
                ),
            )
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


# ---------------------------------------------------------------------------
# The real MCP client library against a delegated tool server
# ---------------------------------------------------------------------------


class _ToolServer:
    """A minimal streamable-HTTP tool server answering over httpx.MockTransport.

    It sets no session id, so the library opens no event stream and sends no
    session teardown: every request it receives is one the run made.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        # The authentication adapter re-sends one request object, so copy it.
        self.requests.append(
            httpx.Request(
                request.method,
                request.url,
                headers=request.headers,
                content=request.content,
            )
        )
        message = json.loads(request.content)
        if "id" not in message:
            return httpx.Response(202)
        results = {
            "initialize": {
                "protocolVersion": message.get("params", {}).get("protocolVersion"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic", "version": "1"},
            },
            "tools/list": {
                "tools": [
                    {
                        "name": "search",
                        "description": "Synthetic search tool",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            },
            "tools/call": {"content": [{"type": "text", "text": "found"}]},
        }
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": results[message["method"]],
            },
        )

    def methods(self) -> list[str]:
        return [json.loads(request.content)["method"] for request in self.requests]


@pytest.fixture
def tool_server(monkeypatch) -> _ToolServer:
    """Serve the library's own HTTP client from a local tool server."""
    served = _ToolServer()

    def _client(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=True,
            transport=httpx.MockTransport(served),
        )

    monkeypatch.setattr(mcp_sessions, "create_mcp_http_client", _client)
    monkeypatch.setattr(mcp_utils, "create_mcp_http_client", _client)
    return served


@asynccontextmanager
async def running_mcp_runtime(
    monkeypatch, provider: OutboundCredentialProvider
) -> AsyncIterator[mcp_runtime.MCPRuntime]:
    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", MultiServerMCPClient)
    set_runtime_context(
        FredRuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.invalid/kf/v1",
                mcp_configuration=_McpCatalog(server("delegated")),
            )
        )
    )
    runtime = mcp_runtime.MCPRuntime(agent=cast(Any, _AgentShim(provider=provider)))
    try:
        await runtime.init()
        yield runtime
    finally:
        await runtime.aclose()
        set_runtime_context(None)


async def call_search(runtime: mcp_runtime.MCPRuntime) -> dict[str, Any]:
    """One tool call through the tool node a turn uses."""
    builder = StateGraph(MessagesState)
    builder.add_node("tools", create_mcp_tool_node(runtime.get_tools()))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    call = AIMessage(
        content="", tool_calls=[{"name": "search", "args": {}, "id": "call-1"}]
    )
    return await builder.compile().ainvoke({"messages": [call]})


def carries_the_grant(request: httpx.Request) -> bool:
    return dict(request.url.params) == {
        GRANT_PARAM_PERSON: "alice",
        GRANT_PARAM_RUN: "run-7",
        GRANT_PARAM_AGENT: "agent-a",
    }


@pytest.mark.asyncio
async def test_every_request_to_a_delegated_tool_server_carries_a_current_bearer(
    monkeypatch, tool_server, empty_client_cache
):
    """A connection outlives one workload token: each HTTP request the library
    sends takes its own bearer, and grant resolution acquires none."""
    identity = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")

    async with running_mcp_runtime(
        monkeypatch, admitted_provider(identity.provider)
    ) as runtime:
        identity.expire()
        result = await call_search(runtime)

    assert "found" in str(result["messages"][-1].content)
    # The library validates a call's result against a listing of its own.
    assert tool_server.methods() == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/call",
        "tools/list",
    ]
    assert [request.headers["Authorization"] for request in tool_server.requests] == [
        "Bearer workload-token-1"
    ] * 3 + ["Bearer workload-token-2"] * 4
    assert all(carries_the_grant(request) for request in tool_server.requests)
    assert identity.acquisitions == len(tool_server.requests)


@pytest.mark.parametrize("stage", ["listing", "tool_call"])
@pytest.mark.asyncio
async def test_a_failed_workload_acquisition_ends_the_run_before_any_tool_request(
    monkeypatch, tool_server, empty_client_cache, stage
):
    identity = MockIdentityProvider(monkeypatch)
    provider = admitted_provider(identity.provider)
    listed: list[httpx.Request] = []

    with recorded_logs() as logs:
        with pytest.raises(DelegationUnavailableError) as raised:
            if stage == "listing":
                identity.failure = "refused"
                async with running_mcp_runtime(monkeypatch, provider):
                    pass
            else:
                async with running_mcp_runtime(monkeypatch, provider) as runtime:
                    listed = list(tool_server.requests)
                    identity.expire()
                    identity.failure = "refused"
                    await call_search(runtime)

    assert raised.value.reason == "delegation_unavailable"
    assert tool_server.requests == listed
    assert (stage == "listing") == (listed == [])
    assert [line for line in logs.lines if "workload credential" in line] == [
        "The workload credential could not be obtained (RuntimeError)."
    ]


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
                provider=delegated_provider(),
                auth_mode="delegated",
            )

    assert raised.value.reason == "authority_lost"
    assert [instance.calls for instance in instances] == [1]
    assert "alice" not in str(raised.value)
    assert not [line for line in logs.lines if "alice" in line]
    assert [line for line in logs.lines if "reason=authority_refused" in line]


@pytest.mark.asyncio
async def test_iam_refusal_during_listing_keeps_delegation_unavailable(
    monkeypatch, empty_client_cache
) -> None:
    attempts = 0

    class _Client:
        def __init__(self, conns, tool_interceptors=None) -> None:
            self.tool_interceptors = list(tool_interceptors or [])

        async def get_tools(self, server_name: str):
            nonlocal attempts
            attempts += 1
            request = httpx.Request("POST", "https://iam.invalid/token")
            response = httpx.Response(401, request=request)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                raise ExceptionGroup(
                    "transport",
                    [DelegationUnavailableError()],
                ) from None

    with pytest.raises(DelegationUnavailableError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=_Client,
            provider=delegated_provider(),
            auth_mode="delegated",
        )
    assert attempts == 1


@pytest.mark.asyncio
async def test_iam_refusal_during_tool_call_keeps_delegation_unavailable() -> None:
    interceptor = DelegatedAuthorityInterceptor(
        delegated_provider(), delegated_server_ids={"kf-mcp"}
    )
    request = httpx.Request("POST", "https://iam.invalid/token")
    response = httpx.Response(401, request=request)

    async def handler(call):
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise ExceptionGroup("transport", [DelegationUnavailableError()]) from None

    with pytest.raises(DelegationUnavailableError):
        await interceptor(tool_request(), handler)


@pytest.mark.asyncio
async def test_a_receiver_that_is_merely_unwell_is_still_retried(
    monkeypatch, empty_client_cache
):
    client_cls, instances = refusing_client(503)

    with pytest.raises(mcp_utils.MCPConnectionError) as raised:
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=delegated_provider(),
            auth_mode="delegated",
        )

    assert sum(instance.calls for instance in instances) == 3
    assert "person=alice" not in str(raised.value)


@pytest.mark.asyncio
async def test_account_status_unavailable_tool_listing_ends_without_retry(
    monkeypatch, empty_client_cache
):
    client_cls, instances = refusing_client(503, account_status_unavailable=True)
    with pytest.raises(AuthorityLostError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=delegated_provider(),
            auth_mode="delegated",
        )
    assert [instance.calls for instance in instances] == [1]


@pytest.mark.asyncio
async def test_a_transport_failure_is_still_retried(monkeypatch, empty_client_cache):
    client_cls, instances = refusing_client(None, transport_error=True)

    with pytest.raises(mcp_utils.MCPConnectionError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=delegated_provider(),
            auth_mode="delegated",
        )

    assert sum(instance.calls for instance in instances) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("refused_status", [401, 403])
async def test_with_the_flag_off_a_refused_listing_retries_connection(
    monkeypatch, empty_client_cache, refused_status
):
    client_cls, instances = refusing_client(refused_status)

    with pytest.raises(mcp_utils.MCPConnectionError):
        await init_mcp_runtime(
            monkeypatch,
            client_cls=client_cls,
            provider=None,
            auth_mode="user_token",
            token="person-token",
        )

    assert sum(instance.calls for instance in instances) == 3
    assert any(
        isinstance(interceptor, LivePersonBearerInterceptor)
        for instance in instances
        for interceptor in instance.tool_interceptors
    )


@pytest.mark.asyncio
async def test_mcp_transport_stamps_live_context_only_on_its_configured_origin(
    monkeypatch,
):
    seen = []
    transport = httpx.MockTransport(
        lambda request: (
            seen.append(request)
            or httpx.Response(302, headers={"Location": "http://external.invalid/leak"})
        )
    )
    monkeypatch.setattr(
        mcp_utils,
        "create_mcp_http_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=transport, follow_redirects=True, **kwargs
        ),
    )
    async with mcp_utils._delegated_mcp_http_client(
        origin=("http", "tools.invalid", None)
    ) as client:
        with log_context(correlation_id="one", session_id="session-a"):
            await client.get("http://tools.invalid/mcp")
        with log_context(correlation_id="two"):
            await client.get("http://tools.invalid/mcp")
            await client.get("http://external.invalid/explicit")
    assert len(seen) == 3
    assert decode_log_context(seen[0].headers[CONTEXT_HEADER])[0] == {
        "correlation_id": "one",
        "session_id": "session-a",
    }
    assert decode_log_context(seen[1].headers[CONTEXT_HEADER])[0] == {
        "correlation_id": "two"
    }
    assert CONTEXT_HEADER not in seen[2].headers
