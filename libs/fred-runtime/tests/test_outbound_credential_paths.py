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
grant from the provider and its bearer from the shared authentication adapter,
through the real workload-token provider — a new path that forgets to is what
the source check at the end is for. The second half pins the refusal: one
renewal after a first 401 and nothing more, no fallback, no upstream text, and a
run-stopping error that reaches the engine instead of the model.
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from conftest import MockIdentityProvider, admitted_provider
from fastapi import HTTPException
from fred_core.logs.context import log_context
from fred_core.logs.propagation import CONTEXT_HEADER, decode_log_context
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
)
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.common.context_aware_tool import ContextAwareTool, _log_http_error
from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    OutboundCredentialProvider,
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
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
    RunStopError,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    MCPServerRef,
)
from fred_sdk.contracts.runtime import TeamWikiPortError, unwrap_run_stop_error
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel

# The body a refused receiver answers with. It must reach nothing the platform
# owns: not an exception message, not an event, not the transcript.
UPSTREAM_MARKER = "upstream-detail-marker"

PERSON_TOKEN = "unused-person-token"
GRANT = {
    GRANT_PARAM_PERSON: "alice",
    GRANT_PARAM_RUN: "run-7",
    GRANT_PARAM_AGENT: "agent-a",
}


def grant_of(request: httpx.Request) -> dict[str, str]:
    fields = dict(request.url.params)
    if request.headers.get("Content-Type") == "application/json":
        body = json.loads(request.content)
        if isinstance(body, dict):
            fields.update(body)
    return {key: fields[key] for key in GRANT if key in fields}


def bearers(requests: list[httpx.Request]) -> list[str]:
    return [request.headers.get("Authorization", "") for request in requests]


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
    handler, *, credentials: OutboundCredentialProvider
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
        credentials=credentials,
        access_token=PERSON_TOKEN,
    )
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))
    return client, seen


def ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def refused(status_code: int, *, account_status_unavailable: bool = False):
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text=UPSTREAM_MARKER,
            headers=(
                {"X-Fred-Denial-Cause": "account_status_unavailable"}
                if account_status_unavailable
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


Receiver = Callable[[httpx.Request], httpx.Response]
Path = Callable[[DelegatedCredentialProvider, Receiver], Awaitable[None]]


async def knowledge_call(provider: DelegatedCredentialProvider, receiver: Receiver):
    client, _ = kf_client(receiver, credentials=provider)
    await client._request_with_token_refresh("GET", "/documents", phase_name="test")


async def workspace_call(provider: DelegatedCredentialProvider, receiver: Receiver):
    workspace = FredWorkspaceFs(
        binding=binding(), settings=FakeAgentSettings(), credentials=provider
    )
    workspace._workspace_client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(receiver)
    )
    await workspace.read_bytes("notes.md")


async def binding_call(provider: DelegatedCredentialProvider, receiver: Receiver):
    request = agent_app_module._AgentExecuteRequest.model_construct(
        agent_id=None, agent_instance_id="instance-1", message="hi"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as client:
        # An unknown instance ends the lookup right after its one request,
        # which is the step being pinned.
        with pytest.raises(HTTPException) as raised:
            await agent_app_module._resolve_agent_instance(
                request=request,
                registry={},
                access_token=PERSON_TOKEN,
                control_plane_url="http://control-plane.invalid/v1",
                http_client=client,
                team_id="team-1",
                credentials=provider,
            )
    assert raised.value.status_code == 404


async def team_wiki_call(provider: DelegatedCredentialProvider, receiver: Receiver):
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as client:
        await TeamWikiAdapter(
            binding=binding(),
            control_plane_url="http://control-plane.invalid/v1",
            http_client=client,
            credentials=provider,
        ).list_pages()


def answering(path: str) -> Receiver:
    """What each receiver answers a successful call with."""

    def _answer(_request: httpx.Request) -> httpx.Response:
        if path == "binding":
            return httpx.Response(404, text="unknown instance")
        if path == "team-wiki":
            return httpx.Response(200, json={"pages": []})
        if path == "workspace":
            return httpx.Response(200, content=b"file-bytes")
        return httpx.Response(200, json={"ok": True})

    return _answer


PATHS: dict[str, Path] = {
    "knowledge": knowledge_call,
    "workspace": workspace_call,
    "binding": binding_call,
    "team-wiki": team_wiki_call,
}
RUN_PATHS = ("knowledge", "workspace", "team-wiki")


def recording(receiver: Receiver) -> tuple[Receiver, list[httpx.Request]]:
    """A retry re-sends the same request object, so each arrival is copied."""
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(
            httpx.Request(
                request.method,
                request.url,
                headers=request.headers,
                content=request.content,
            )
        )
        return receiver(request)

    return _record, seen


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.asyncio
async def test_each_delegated_request_acquires_its_bearer_once(monkeypatch, path):
    """Grant resolution acquires nothing; the request's authentication adapter
    acquires the one bearer it carries, beside the record's grant."""
    identity = MockIdentityProvider(monkeypatch, "workload-token-1")
    receiver, seen = recording(answering(path))

    with log_context(
        correlation_id="journey-a",
        request_id="upstream-a",
        team_id="team-a",
        custom={"phase": 2},
    ):
        await PATHS[path](admitted_provider(identity.provider), receiver)

    assert len(seen) == 1
    assert identity.acquisitions == 1
    assert identity.token_requests == ["request_initial"]
    assert bearers(seen) == ["Bearer workload-token-1"]
    assert grant_of(seen[0]) == GRANT
    assert decode_log_context(seen[0].headers[CONTEXT_HEADER]) == (
        {"correlation_id": "journey-a", "team_id": "team-a", "custom": {"phase": 2}},
        None,
    )


@pytest.mark.parametrize("path", RUN_PATHS)
@pytest.mark.asyncio
async def test_a_first_401_renews_the_bearer_once_and_keeps_the_grant(
    monkeypatch, path
):
    identity = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")
    answer = answering(path)

    def _expired_then_accepted(request: httpx.Request) -> httpx.Response:
        if len(seen) == 1:
            return httpx.Response(401, text=UPSTREAM_MARKER)
        return answer(request)

    receiver, seen = recording(_expired_then_accepted)

    await PATHS[path](admitted_provider(identity.provider), receiver)

    assert bearers(seen) == ["Bearer workload-token-1", "Bearer workload-token-2"]
    assert [grant_of(request) for request in seen] == [GRANT, GRANT]
    assert identity.acquisitions == 2
    assert identity.token_requests == ["request_initial", "request_renewal"]


@pytest.mark.parametrize("path", RUN_PATHS)
@pytest.mark.asyncio
async def test_a_second_401_ends_the_run_without_the_persons_bearer(monkeypatch, path):
    identity = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")
    receiver, seen = recording(refused(401))

    # The workspace client wraps what it raises; the stop is still in its chain.
    with pytest.raises(Exception) as raised:
        await PATHS[path](admitted_provider(identity.provider), receiver)

    stop = unwrap_run_stop_error(raised.value)
    assert isinstance(stop, AuthorityLostError)
    assert UPSTREAM_MARKER not in str(stop)
    assert bearers(seen) == ["Bearer workload-token-1", "Bearer workload-token-2"]
    assert [grant_of(request) for request in seen] == [GRANT, GRANT]
    assert identity.acquisitions == 2


@pytest.mark.parametrize("path", ("knowledge", "binding"))
@pytest.mark.asyncio
async def test_a_failed_acquisition_stops_the_run_before_any_request(monkeypatch, path):
    identity = MockIdentityProvider(monkeypatch)
    identity.failure = "refused"
    receiver, seen = recording(answering(path))

    with recorded_logs() as logs:
        with pytest.raises(DelegationUnavailableError) as raised:
            await PATHS[path](admitted_provider(identity.provider), receiver)

    assert raised.value.reason == "delegation_unavailable"
    assert seen == []
    assert [line for line in logs.lines if "workload credential" in line] == [
        "The workload credential could not be obtained (RuntimeError)."
    ]


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


@pytest.mark.asyncio
async def test_a_refused_delegated_call_raises_and_is_not_retried(monkeypatch):
    identity = MockIdentityProvider(monkeypatch)
    client, seen = kf_client(
        refused(403), credentials=admitted_provider(identity.provider)
    )

    with pytest.raises(AuthorityLostError) as raised:
        await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert len(seen) == 1
    assert identity.acquisitions == 1
    assert UPSTREAM_MARKER not in str(raised.value)
    assert raised.value.reason == "authority_lost"


@pytest.mark.asyncio
async def test_only_structured_account_status_unavailable_503_ends_authority(
    monkeypatch,
):
    provider = admitted_provider(MockIdentityProvider(monkeypatch).provider)
    denied, denied_seen = kf_client(
        refused(503, account_status_unavailable=True), credentials=provider
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
async def test_with_the_flag_off_a_401_keeps_its_refresh_and_retry():
    """The person path is untouched: a 401 is still an expiry to recover from,
    not a lost authority."""
    client, seen = kf_client(refused(401), credentials=static_person_provider("person"))

    with pytest.raises(httpx.HTTPStatusError):
        await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert seen[0].headers["Authorization"] == "Bearer person"


@pytest.mark.parametrize(
    ("failure", "stop_type", "requests"),
    [(None, AuthorityLostError, 1), ("refused", DelegationUnavailableError, 0)],
    ids=["refused-call", "failed-acquisition"],
)
@pytest.mark.asyncio
async def test_a_team_wiki_stop_stays_in_the_chain_of_the_port_error(
    monkeypatch, failure, stop_type, requests
):
    """The team-wiki capability finds the stop there and ends the run with it."""
    identity = MockIdentityProvider(monkeypatch)
    identity.failure = failure
    receiver, seen = recording(refused(403))

    with pytest.raises(TeamWikiPortError) as raised:
        await team_wiki_call(admitted_provider(identity.provider), receiver)

    assert isinstance(unwrap_run_stop_error(raised.value), stop_type)
    assert UPSTREAM_MARKER not in str(raised.value)
    assert len(seen) == requests


@pytest.mark.asyncio
async def test_document_similarity_403_stops_the_run_without_retry(monkeypatch):
    identity = MockIdentityProvider(monkeypatch)
    seen: list[httpx.Request] = []

    def _refuse(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403, text=UPSTREAM_MARKER)

    adapter = DocumentSimilarityAdapter(
        binding=binding(),
        settings=FakeAgentSettings(),
        credentials=admitted_provider(identity.provider),
    )
    adapter._search_client.client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(_refuse)
    )

    with pytest.raises(AuthorityLostError) as raised:
        await adapter.find_similar("synthetic", document_uids=["doc-a"])

    assert len(seen) == 1
    assert identity.acquisitions == 1
    assert UPSTREAM_MARKER not in str(raised.value)


@pytest.mark.asyncio
async def test_builtin_similarity_keeps_delegated_credentials_after_rebind(
    monkeypatch,
):
    identity = MockIdentityProvider(monkeypatch, "workload-token-1")
    invoker = FredKnowledgeSearchToolInvoker(
        binding=binding(),
        settings=FakeAgentSettings(),
        credentials=admitted_provider(identity.provider),
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

    assert identity.acquisitions == 2
    assert bearers(seen) == ["Bearer workload-token-1"] * 2
    assert [grant_of(request) for request in seen] == [GRANT, GRANT]


@pytest.mark.asyncio
async def test_a_team_wiki_transport_failure_is_still_a_port_error(monkeypatch):
    """Only a refusal ends the run; everything else keeps the behaviour the
    capability already handles."""

    def _unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    provider = admitted_provider(MockIdentityProvider(monkeypatch).provider)

    with pytest.raises(TeamWikiPortError):
        await team_wiki_call(provider, _unreachable)


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
async def test_a_call_completes_even_though_its_bearer_expired_in_flight(
    monkeypatch,
):
    """Acceptance happens once, at the receiver. The runtime neither re-checks
    nor retries a call that is already under way."""
    identity = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")

    def _expire_then_answer(_request: httpx.Request) -> httpx.Response:
        identity.expire()
        return httpx.Response(200, json={"ok": True})

    client, seen = kf_client(
        _expire_then_answer, credentials=admitted_provider(identity.provider)
    )

    response = await client._request_with_token_refresh(
        "GET", "/documents", phase_name="test"
    )

    assert response.status_code == 200
    assert len(seen) == 1
    assert identity.acquisitions == 1
    assert identity.issued == ["workload-token-1"]


@pytest.mark.asyncio
async def test_a_later_call_carries_the_current_bearer_and_the_same_grant(
    monkeypatch,
):
    identity = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")
    client, seen = kf_client(ok, credentials=admitted_provider(identity.provider))

    await client._request_with_token_refresh("GET", "/documents", phase_name="test")
    identity.expire()
    await client._request_with_token_refresh("GET", "/documents", phase_name="test")

    assert bearers(seen) == ["Bearer workload-token-1", "Bearer workload-token-2"]
    assert [grant_of(request) for request in seen] == [GRANT, GRANT]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["account_status_unavailable", "other", None])
async def test_binding_lookup_preserves_only_bounded_account_status_unavailable(
    monkeypatch, cause
):
    def endpoint(request):
        return httpx.Response(
            503,
            text=UPSTREAM_MARKER,
            headers={"X-Fred-Denial-Cause": cause} if cause else {},
        )

    request = agent_app_module._AgentExecuteRequest.model_construct(
        agent_id=None, agent_instance_id="instance-1", message="hi"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as client:
        with pytest.raises(HTTPException) as raised:
            await agent_app_module._resolve_agent_instance(
                request=request,
                registry={},
                access_token="person-bearer",
                control_plane_url="http://control-plane.invalid/v1",
                http_client=client,
                team_id="team-1",
                credentials=admitted_provider(
                    MockIdentityProvider(monkeypatch).provider
                ),
            )
    if cause == "account_status_unavailable":
        assert raised.value.status_code == 503
        assert raised.value.headers == {"X-Fred-Denial-Cause": cause}
        assert UPSTREAM_MARKER not in raised.value.detail
    else:
        assert raised.value.status_code == 502
        assert not raised.value.headers


@pytest.mark.asyncio
async def test_shared_client_context_is_per_invocation_and_redirects_are_confined(
    monkeypatch,
):
    identity = MockIdentityProvider(monkeypatch, "workload-token-1")
    client, seen = kf_client(
        lambda request: httpx.Response(
            302, headers={"Location": "http://external.invalid/redirect"}
        ),
        credentials=admitted_provider(identity.provider),
    )
    client.client.follow_redirects = True
    supplied = {"accept": "application/json"}
    try:
        with log_context(correlation_id="first", custom="first-only"):
            await client._execute_authenticated_request(
                "GET", "/documents", headers=supplied
            )
        with log_context(correlation_id="second"):
            await client._execute_authenticated_request("GET", "/documents")
        client._explicit_credentials = static_person_provider("ordinary-person")
        await client._execute_authenticated_request(
            "GET", "/documents", follow_redirects=False
        )
    finally:
        await client.client.aclose()
    assert supplied == {"accept": "application/json"}
    assert len(seen) == 3
    assert all(request.url.host == "kf.invalid" for request in seen)
    assert decode_log_context(seen[0].headers[CONTEXT_HEADER])[0] == {
        "correlation_id": "first",
        "custom": "first-only",
    }
    assert decode_log_context(seen[1].headers[CONTEXT_HEADER])[0] == {
        "correlation_id": "second"
    }
    assert CONTEXT_HEADER not in seen[2].headers
