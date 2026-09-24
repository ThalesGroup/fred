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

"""Every way out of the runtime, and what happens when one is refused.

The first half enumerates the outbound paths and proves each one takes its
credentials from the provider — a new path that forgets to is what the source
check at the end is for. The second half pins the refusal: no retry, no
fallback, no upstream text, and a run-stopping error that reaches the engine
instead of the model.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
)
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.common import mcp_utils
from fred_runtime.common.context_aware_tool import ContextAwareTool, _log_http_error
from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.outbound_credentials import (
    OutboundCredentialProvider,
    OutboundCredentials,
    PersonCredentialProvider,
    static_person_provider,
)
from fred_runtime.common.tool_node_utils import (
    create_mcp_tool_node,
    friendly_mcp_tool_error_handler,
)
from fred_runtime.integrations.v2_runtime.adapters import (
    DocumentSimilarityAdapter,
    FredKnowledgeSearchToolInvoker,
    FredWorkspaceFs,
    TeamWikiAdapter,
)
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import AuthorityLostError, RunStopError
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    MCPServerConfiguration,
    MCPServerRef,
)
from fred_sdk.contracts.runtime import TeamWikiPortError
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel

# The body a refused receiver answers with. It must reach nothing the platform
# owns: not an exception message, not an event, not the transcript.
UPSTREAM_MARKER = "upstream-detail-marker"

WORKLOAD_BEARER = "Bearer workload-token"
GRANT = {
    GRANT_PARAM_PERSON: "alice",
    GRANT_PARAM_RUN: "run-7",
    GRANT_PARAM_AGENT: "agent-a",
}


class RecordingProvider(OutboundCredentialProvider):
    """A delegated provider that counts how often it is asked."""

    delegated = True

    def __init__(self, authorization: str = WORKLOAD_BEARER) -> None:
        self._authorization = authorization
        self.asked = 0

    def set_authorization(self, authorization: str) -> None:
        self._authorization = authorization

    async def credentials(self, *, override_token: str | None = None):
        self.asked += 1
        return OutboundCredentials(
            authorization=self._authorization, parameters=dict(GRANT), delegated=True
        )

    def for_agent(self, agent_id: str) -> "RecordingProvider":
        return self


class FakeAgentSettings:
    id = "agent-a"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


@pytest.fixture(autouse=True)
def _runtime_context():
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    yield
    set_runtime_context(None)


def kf_client(
    handler, *, credentials: OutboundCredentialProvider | None = None
) -> tuple[KfBaseClient, list[httpx.Request]]:
    """A Knowledge Flow client whose transport answers locally.

    `httpx.MockTransport` keeps real httpx request building — URL, query string,
    headers, body — so what a receiver would see is what the test inspects.
    """
    seen: list[httpx.Request] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = KfBaseClient(
        frozenset({"GET", "POST"}),
        credentials=credentials or RecordingProvider(),
        access_token="unused-person-token",
    )
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))
    return client, seen


def ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def refused(status_code: int, *, standing_unavailable: bool = False):
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text=UPSTREAM_MARKER,
            headers=(
                {"X-Fred-Denial-Cause": "standing_unavailable"}
                if standing_unavailable
                else {}
            ),
        )

    return _handler


def binding(token: str | None = "person-bearer") -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1",
            user_id="alice",
            team_id="team-1",
            agent_instance_id="instance-1",
            access_token=token,
        ),
        portable_context=PortableContext(
            request_id="r-1",
            correlation_id="c-1",
            actor="alice",
            tenant="default",
            environment=PortableEnvironment.DEV,
            user_id="alice",
            team_id="team-1",
        ),
    )


# ---------------------------------------------------------------------------
# Enumeration: every outbound path asks the provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_knowledge_flow_client_asks_the_provider():
    provider = RecordingProvider()
    client, seen = kf_client(ok, credentials=provider)

    await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert provider.asked == 1
    assert seen[0].headers["Authorization"] == WORKLOAD_BEARER
    assert seen[0].url.params[GRANT_PARAM_PERSON] == "alice"


@pytest.mark.asyncio
async def test_the_mcp_connection_asks_the_provider(monkeypatch):
    provider = RecordingProvider()
    connections: dict[str, Any] = {}

    class _FakeMultiServerClient:
        def __init__(self, conns, tool_interceptors=None) -> None:
            connections.update(conns)
            self.tool_interceptors = list(tool_interceptors or [])

        async def get_tools(self, server_name: str):
            return []

    monkeypatch.setattr(mcp_utils, "MultiServerMCPClient", _FakeMultiServerClient)
    server = MCPServerConfiguration.model_validate(
        {
            "id": "kf-mcp",
            "name": "kf",
            "transport": "streamable_http",
            "url": "http://kf.invalid/mcp",
            "enabled": True,
            "auth_mode": "delegated",
        }
    )

    await mcp_utils.get_connected_mcp_client_for_agent(
        agent_id="agent-a",
        mcp_servers=[server],
        runtime_context=RuntimeContext(),
        credentials=provider,
    )

    assert provider.asked == 1
    assert connections["kf-mcp"]["headers"]["Authorization"] == WORKLOAD_BEARER


@pytest.mark.asyncio
async def test_the_team_wiki_client_asks_the_provider():
    provider = RecordingProvider()
    seen: list[dict[str, Any]] = []

    class _FakeControlPlaneClient:
        async def request(self, method, url, headers=None, **kwargs):
            seen.append({"method": method, "url": url, "headers": headers, **kwargs})
            return httpx.Response(
                200, json={"pages": []}, request=httpx.Request(method, url)
            )

    adapter = TeamWikiAdapter(
        binding=binding(),
        control_plane_url="http://control-plane.invalid/v1",
        http_client=_FakeControlPlaneClient(),
        credentials=provider,
    )

    await adapter.list_pages()

    assert provider.asked == 1
    assert seen[0]["headers"]["Authorization"] == WORKLOAD_BEARER
    assert seen[0]["params"][GRANT_PARAM_RUN] == "run-7"


@pytest.mark.asyncio
async def test_the_workspace_client_asks_the_provider():
    provider = RecordingProvider()
    workspace = FredWorkspaceFs(
        binding=binding(), settings=FakeAgentSettings(), credentials=provider
    )
    seen: list[httpx.Request] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"file-bytes")

    workspace._workspace_client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handle)
    )

    await workspace.read_bytes("notes.md")

    assert provider.asked == 1
    assert seen[0].headers["Authorization"] == WORKLOAD_BEARER
    assert seen[0].url.params[GRANT_PARAM_AGENT] == "agent-a"


@pytest.mark.asyncio
async def test_workspace_child_uses_live_person_bearer_without_grant():
    token = "person-first"

    async def current_token() -> str:
        return token

    workspace = FredWorkspaceFs(
        binding=binding("stale-person-token"),
        settings=FakeAgentSettings(),
        credentials=PersonCredentialProvider(current_token),
    )
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"synthetic")

    workspace._workspace_client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle)
    )
    await workspace.read_bytes("notes.md")
    token = "person-updated"
    await workspace.read_bytes("notes.md")
    assert [request.headers["Authorization"] for request in seen] == [
        "Bearer person-first",
        "Bearer person-updated",
    ]
    assert all(GRANT_PARAM_PERSON not in request.url.params for request in seen)


@pytest.mark.asyncio
async def test_the_control_plane_binding_call_asks_the_provider():
    provider = RecordingProvider()
    seen: list[dict[str, Any]] = []

    class _FakeBindingClient:
        async def get(self, url, headers=None, **kwargs):
            seen.append({"url": url, "headers": headers, **kwargs})
            # What the instance resolves to is not this test's subject; an
            # unknown instance ends the call right after the credentials were
            # taken, which is the step being pinned.
            return httpx.Response(404, text="unknown instance")

    request = agent_app_module._AgentExecuteRequest.model_construct(
        agent_id=None, agent_instance_id="instance-1", message="hi"
    )

    with pytest.raises(HTTPException) as raised:
        await agent_app_module._resolve_agent_instance(
            request=request,
            registry={},
            access_token="person-bearer",
            control_plane_url="http://control-plane.invalid/v1",
            http_client=_FakeBindingClient(),  # type: ignore[arg-type]
            team_id="team-1",
            credentials=provider,
        )

    assert raised.value.status_code == 404
    assert provider.asked == 1
    assert seen[0]["headers"]["Authorization"] == WORKLOAD_BEARER


def test_no_outbound_path_builds_an_authorization_header_of_its_own():
    """The enumeration above covers the paths that exist today; this covers the
    one added tomorrow. A module that sets an Authorization header must be a
    module that asks the provider for it."""
    runtime_root = pathlib.Path(agent_app_module.__file__).parent.parent
    searched = [
        *(runtime_root / "common").glob("*.py"),
        *(runtime_root / "integrations").rglob("*.py"),
        *(runtime_root / "capabilities").rglob("*.py"),
        runtime_root / "app" / "agent_app.py",
    ]

    offenders = [
        path.name
        for path in searched
        if '"Authorization"' in path.read_text()
        and "outbound_credentials" not in path.read_text()
    ]

    assert offenders == []


# ---------------------------------------------------------------------------
# A refused delegated call ends the run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403])
@pytest.mark.asyncio
async def test_a_refused_delegated_call_raises_and_is_not_retried(status_code: int):
    provider = RecordingProvider()
    client, seen = kf_client(refused(status_code), credentials=provider)

    with pytest.raises(AuthorityLostError) as raised:
        await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert len(seen) == 1
    assert UPSTREAM_MARKER not in str(raised.value)
    assert raised.value.reason == "authority_lost"


@pytest.mark.asyncio
async def test_only_structured_standing_unavailable_503_ends_authority():
    provider = RecordingProvider()
    denied, denied_seen = kf_client(
        refused(503, standing_unavailable=True), credentials=provider
    )
    with pytest.raises(AuthorityLostError):
        await denied._request_with_token_refresh("GET", "/documents", phase_name="test")
    assert len(denied_seen) == 1

    unavailable, unavailable_seen = kf_client(refused(503), credentials=provider)
    with pytest.raises(httpx.HTTPStatusError):
        await unavailable._request_with_token_refresh(
            "GET", "/documents", phase_name="test"
        )
    assert len(unavailable_seen) == 1


@pytest.mark.asyncio
async def test_a_refused_delegated_call_never_falls_back_to_the_persons_bearer():
    provider = RecordingProvider()
    client, seen = kf_client(refused(401), credentials=provider)

    with pytest.raises(AuthorityLostError):
        await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert [request.headers["Authorization"] for request in seen] == [WORKLOAD_BEARER]


@pytest.mark.asyncio
async def test_with_the_flag_off_a_401_keeps_its_refresh_and_retry():
    """The person path is untouched: a 401 is still an expiry to recover from,
    not a lost authority."""
    client, seen = kf_client(refused(401), credentials=static_person_provider("person"))

    with pytest.raises(httpx.HTTPStatusError):
        await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert seen[0].headers["Authorization"] == "Bearer person"


@pytest.mark.asyncio
async def test_a_refused_team_wiki_call_ends_the_run_instead_of_becoming_a_port_error():
    provider = RecordingProvider()

    class _RefusingClient:
        async def request(self, method, url, headers=None, **kwargs):
            return httpx.Response(
                403, text=UPSTREAM_MARKER, request=httpx.Request(method, url)
            )

    adapter = TeamWikiAdapter(
        binding=binding(),
        control_plane_url="http://control-plane.invalid/v1",
        http_client=_RefusingClient(),
        credentials=provider,
    )

    with pytest.raises(AuthorityLostError) as raised:
        await adapter.list_pages()

    assert UPSTREAM_MARKER not in str(raised.value)


@pytest.mark.asyncio
async def test_document_similarity_403_stops_the_run_without_retry():
    provider = RecordingProvider()
    seen: list[httpx.Request] = []

    def _refuse(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403, text=UPSTREAM_MARKER)

    adapter = DocumentSimilarityAdapter(
        binding=binding(), settings=FakeAgentSettings(), credentials=provider
    )
    adapter._search_client.client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(_refuse)
    )

    with pytest.raises(AuthorityLostError) as raised:
        await adapter.find_similar("synthetic", document_uids=["doc-a"])

    assert len(seen) == 1
    assert provider.asked == 1
    assert UPSTREAM_MARKER not in str(raised.value)


@pytest.mark.asyncio
async def test_builtin_similarity_keeps_delegated_credentials_after_rebind():
    provider = RecordingProvider()
    invoker = FredKnowledgeSearchToolInvoker(
        binding=binding(), settings=FakeAgentSettings(), credentials=provider
    )
    seen: list[httpx.Request] = []

    def _empty(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    for current_binding in (binding(), binding(token=None)):
        invoker.rebind(current_binding)
        invoker._similarity_port._search_client.client = httpx.AsyncClient(  # type: ignore[attr-defined]
            transport=httpx.MockTransport(_empty)
        )
        await invoker._similarity_port.find_similar(  # type: ignore[attr-defined]
            "synthetic", document_uids=["doc-a"]
        )

    assert provider.asked == 2
    assert len(seen) == 2
    assert all(request.headers["Authorization"] == WORKLOAD_BEARER for request in seen)


@pytest.mark.asyncio
async def test_a_team_wiki_transport_failure_is_still_a_port_error():
    """Only a refusal ends the run; everything else keeps the behaviour the
    capability already handles."""

    class _FailingClient:
        async def request(self, method, url, headers=None, **kwargs):
            raise httpx.ConnectError("unreachable")

    adapter = TeamWikiAdapter(
        binding=binding(),
        control_plane_url="http://control-plane.invalid/v1",
        http_client=_FailingClient(),
        credentials=RecordingProvider(),
    )

    with pytest.raises(TeamWikiPortError):
        await adapter.list_pages()


# ---------------------------------------------------------------------------
# A run-stopping error is never turned into a tool result
# ---------------------------------------------------------------------------


class _NoArgs(BaseModel):
    pass


class _StoppingTool(BaseTool):
    name: str = "fake.stopping"
    description: str = "Raises a run-stopping error."
    args_schema: Any = _NoArgs

    def _run(self) -> str:
        raise AuthorityLostError("A service refused this run's authority.")

    async def _arun(self, config: Any = None) -> str:
        raise AuthorityLostError("A service refused this run's authority.")


class _WrappedStoppingTool(BaseTool):
    name: str = "fake.wrapped"
    description: str = "Raises a run-stopping error wrapped in another error."
    args_schema: Any = _NoArgs

    def _run(self) -> str:
        raise RuntimeError("tool wrapper")

    async def _arun(self, config: Any = None) -> str:
        try:
            raise AuthorityLostError("A service refused this run's authority.")
        except AuthorityLostError as stop:
            raise RuntimeError("tool wrapper") from stop


class _FailingTool(BaseTool):
    name: str = "fake.failing"
    description: str = "Fails the way an unreachable server does."
    args_schema: Any = _NoArgs

    def _run(self) -> str:
        raise ConnectionError("unreachable")

    async def _arun(self, config: Any = None) -> str:
        raise ConnectionError("unreachable")


def tool_graph(tool: BaseTool):
    """One compiled graph around the shared tool node.

    A ToolNode only receives LangGraph's runtime inside a graph, so this is the
    same path a turn takes — not a hand-called node.
    """
    builder = StateGraph(MessagesState)
    builder.add_node("tools", create_mcp_tool_node([tool]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile()


def tool_call(name: str) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": {}, "id": "call-1"}]
    )


def test_the_tool_error_handler_lets_a_run_stopping_error_through():
    with pytest.raises(RunStopError):
        friendly_mcp_tool_error_handler(AuthorityLostError("stopped"))


def test_the_tool_error_handler_still_explains_an_unreachable_server():
    assert "MCP server" in friendly_mcp_tool_error_handler(ConnectionError("boom"))


@pytest.mark.asyncio
async def test_a_tool_node_propagates_a_run_stopping_error_instead_of_answering():
    with pytest.raises(RunStopError):
        await tool_graph(_StoppingTool()).ainvoke(
            {"messages": [tool_call("fake.stopping")]}
        )


@pytest.mark.asyncio
async def test_a_tool_node_still_answers_an_ordinary_tool_failure():
    """Unchanged: a failure the run can survive is still a tool result, so the
    transcript keeps a result for every call."""
    result = await tool_graph(_FailingTool()).ainvoke(
        {"messages": [tool_call("fake.failing")]}
    )

    assert "MCP server" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_a_tool_node_propagates_a_wrapped_run_stopping_error():
    with pytest.raises(RunStopError):
        await tool_graph(_WrappedStoppingTool()).ainvoke(
            {"messages": [tool_call("fake.wrapped")]}
        )


@pytest.mark.asyncio
async def test_the_context_aware_wrapper_raises_instead_of_returning_text():
    wrapper = ContextAwareTool(
        base_tool=_StoppingTool(),
        context_provider=lambda: None,
        agent_settings_provider=FakeAgentSettings,
    )

    with pytest.raises(RunStopError):
        await wrapper._arun()

    with pytest.raises(RunStopError):
        wrapper._run()


@pytest.mark.asyncio
async def test_the_context_aware_wrapper_finds_a_wrapped_run_stopping_error():
    wrapper = ContextAwareTool(
        base_tool=_WrappedStoppingTool(),
        context_provider=lambda: None,
        agent_settings_provider=FakeAgentSettings,
    )

    with pytest.raises(RunStopError):
        await wrapper._arun()


# ---------------------------------------------------------------------------
# A call that outlives the credential it started with
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_call_completes_even_though_its_bearer_expired_in_flight():
    """Acceptance happens once, at the receiver. The runtime neither re-checks
    nor retries a call that is already under way."""
    provider = RecordingProvider()

    def _rotate_then_answer(_request: httpx.Request) -> httpx.Response:
        provider.set_authorization("Bearer workload-token-2")
        return httpx.Response(200, json={"ok": True})

    client, seen = kf_client(_rotate_then_answer, credentials=provider)

    response = await client._request_with_token_refresh(
        "GET", "/documents", phase_name="test"
    )

    assert response.status_code == 200
    assert provider.asked == 1
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_a_later_call_carries_the_current_bearer_and_the_same_grant():
    provider = RecordingProvider()
    client, seen = kf_client(ok, credentials=provider)

    await client._request_with_token_refresh("GET", "/documents", phase_name="test")
    provider.set_authorization("Bearer workload-token-2")
    await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert [request.headers["Authorization"] for request in seen] == [
        WORKLOAD_BEARER,
        "Bearer workload-token-2",
    ]
    assert all(request.url.params[GRANT_PARAM_RUN] == "run-7" for request in seen)


# ---------------------------------------------------------------------------
# What a failure is allowed to say
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


def test_a_failed_tool_call_reports_its_endpoint_without_the_grant():
    """A delegated request carries the grant in its query, and a failure repeats
    that query — in the line reporting it and in its own text underneath."""
    url = "http://kf.invalid/documents?person=alice&run=run-7&agent=agent-a"
    request = httpx.Request("GET", url)
    error = httpx.HTTPStatusError(
        f"Server error '500 Internal Server Error' for url '{url}'",
        request=request,
        response=httpx.Response(500, request=request, text="boom"),
    )

    with recorded_logs() as logs:
        _log_http_error("kf.search", error)

    assert [line for line in logs.lines if "kf.invalid/documents" in line]
    assert not [line for line in logs.lines if "alice" in line or "run-7" in line]
