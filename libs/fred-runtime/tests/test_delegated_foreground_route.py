"""A delegated attended run lives inside its stream: when the response ends,
however it ended, the run's children are cancelled and its record is gone.

The stream tests drive the real app, `KPIMiddleware` included, through
`httpx.ASGITransport`, so a disconnect reaches the route the way a server
delivers it: as an `http.disconnect` on `receive`.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import fred_runtime.app.agent_app as agent_app_module
import httpx
import pytest
from conftest import StaticWorkloadTokens
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core.security import oidc as oidc_module
from fred_core.security.delegation import DelegationConfig, initialize_delegation
from fred_core.security.models import StandingAuthorizationError
from fred_core.security.structure import KeycloakUser
from fred_runtime.app.agent_app import _write_turn_history, create_agent_app
from fred_runtime.app.dependencies import get_pod_container_from_app
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    set_delegation_runtime,
)
from fred_runtime.runtime_context import get_runtime_context, set_runtime_context
from fred_runtime.runtime_support.run_scope import register_run_child
from fred_sdk.contracts.react_contract import ReActInput, ReActOutput
from fred_sdk.contracts.runtime import (
    AgentRuntime,
    AwaitingHumanRuntimeEvent,
    Executor,
    HumanInputRequest,
    RuntimeEvent,
    StatusRuntimeEvent,
)
from langchain_core.messages import AIMessage
from starlette.types import Message
from test_agent_app import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    _build_test_config,
    _EchoAgent,
)

STREAM_PATH = "/pod/v1/agents/execute/stream"
PERSON_TOKEN = "person-token"
TIMEOUT = 5.0


@pytest.fixture(autouse=True)
def _restore_process_security() -> Iterator[None]:
    keycloak_enabled = oidc_module.KEYCLOAK_ENABLED
    yield
    oidc_module.KEYCLOAK_ENABLED = keycloak_enabled
    initialize_delegation(DelegationConfig())
    set_delegation_runtime(None)
    # Each pod installs a process-wide runtime context; later modules must not see it.
    set_runtime_context(None)


def _portal_call(client: TestClient, func, *args):
    assert client.portal is not None
    return client.portal.call(func, *args)


async def _install_control_plane_transport(
    app, transport: httpx.AsyncBaseTransport
) -> None:
    container = get_pod_container_from_app(app)
    old_client = container.get_control_plane_http_client()
    client = httpx.AsyncClient(transport=transport)
    container._control_plane_http_client = client
    runtime_context = get_runtime_context()
    runtime_context._config = replace(
        runtime_context.config, control_plane_http_client=client
    )
    await old_client.aclose()


def _person_pod(
    monkeypatch,
    tmp_path,
    *,
    model: ToolFriendlyFakeChatModel | None = None,
    authorized_origins: list[str] | None = None,
    decode: Callable[[str], KeycloakUser] | None = None,
) -> FastAPI:
    """A pod acting for people, whose only caller is a signed-in person."""
    model = model or ToolFriendlyFakeChatModel(responses=[])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        decode
        or (
            lambda token: KeycloakUser(
                uid="owner-a", username="synthetic", roles=[], client_id="browser"
            )
        ),
    )
    rebac = SimpleNamespace(
        enforces_standing=True,
        enabled=True,
        validate_standing_model=AsyncMock(),
        is_standing_seed_ready=AsyncMock(return_value=True),
        require_user_standing=AsyncMock(),
        check_user_team_permission_or_raise=AsyncMock(),
    )
    monkeypatch.setattr(
        agent_app_module, "rebac_factory", lambda *args, **kwargs: rebac
    )
    config = _build_test_config(
        tmp_path,
        control_plane_url="http://control-plane.test/control-plane/v1",
        user_security_enabled=True,
        act_for_people=True,
    )
    if authorized_origins is not None:
        security = config.security
        assert security is not None
        config = config.model_copy(
            update={
                "security": security.model_copy(
                    update={"authorized_origins": authorized_origins}
                )
            }
        )
    return create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()}, config=config
    )


def _install_delegation() -> DelegationRuntime:
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True),
        token_provider=StaticWorkloadTokens(),
    )
    set_delegation_runtime(runtime)
    return runtime


def _admitted_run_ids(monkeypatch) -> list[str]:
    """The run id each admission wrote, read off the provider it returned."""
    run_ids: list[str] = []
    admit = agent_app_module._admit_run_credentials

    def _spy(*args: Any, **kwargs: Any):
        provider = admit(*args, **kwargs)
        run_ids.append(cast(Any, provider).run_id)
        return provider

    monkeypatch.setattr(agent_app_module, "_admit_run_credentials", _spy)
    return run_ids


def _executor_runtime(
    monkeypatch,
    stream: Callable[[], AsyncGenerator[RuntimeEvent, None]],
    *,
    on_dispose: Callable[[], Awaitable[None] | None] = lambda: None,
) -> None:
    """Replace the ReAct engine with one whose executor streams `stream()`."""

    class _Executor(Executor[ReActInput, ReActOutput]):
        async def invoke(self, input_model, config):  # noqa: ANN001
            raise NotImplementedError

        async def stream(self, input_model, config):  # noqa: ANN001
            async for event in stream():
                yield event

    class _Runtime(AgentRuntime[Any, ReActInput, ReActOutput]):
        def __init__(self, *, definition, services, capability_block=None):
            super().__init__(definition=definition, services=services)

        async def build_executor(self, binding):  # noqa: ANN001
            return _Executor()

        async def on_dispose(self) -> None:
            result = on_dispose()
            if inspect.isawaitable(result):
                await result

    monkeypatch.setattr(agent_app_module, "ReActRuntime", _Runtime)


def _keep_streams(monkeypatch) -> list[AsyncGenerator[str, None]]:
    """Hold every response stream, so only the response's own close, never
    garbage collection, can end the run behind it."""
    streams: list[AsyncGenerator[str, None]] = []
    build = agent_app_module._stream

    def _kept(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
        stream = build(*args, **kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setattr(agent_app_module, "_stream", _kept)
    return streams


class _Connection:
    """An ASGI shim between the transport and the app, standing for the server.

    It delivers `http.disconnect` on `receive` once `drop()` is called, can hold
    the client on its first frame until `release()` so the next one waits in
    `send`, and records what `on_end` observes the moment the app returns,
    before anything else runs.
    """

    def __init__(self, app: FastAPI, *, hold_first_frame: bool = False) -> None:
        self.app = app
        self.hold_first_frame = hold_first_frame
        self.dropped = asyncio.Event()
        self.released = asyncio.Event()
        self.frames: list[bytes] = []
        self.on_end: Callable[[], dict[str, Any]] = dict
        self.at_end: dict[str, Any] | None = None

    def drop(self) -> None:
        self.dropped.set()

    def release(self) -> None:
        self.released.set()

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body_read = False

        async def _receive() -> dict[str, Any]:
            nonlocal body_read
            if body_read:
                await self.dropped.wait()
                return {"type": "http.disconnect"}
            message = await receive()
            body_read = not message.get("more_body", False)
            return message

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                self.frames.append(message["body"])
                if self.hold_first_frame:
                    await self.released.wait()
            await send(message)

        await self.app(scope, _receive, _send)
        self.at_end = self.on_end()


@asynccontextmanager
async def _serving(connection: _Connection):
    async with connection.app.router.lifespan_context(connection.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=connection),
            base_url="http://runtime.test",
        ) as client:
            yield client


def _payloads(body: bytes | str) -> list[dict[str, Any]]:
    text = body.decode() if isinstance(body, bytes) else body
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def _post(client: httpx.AsyncClient, body: dict[str, Any]) -> Awaitable[httpx.Response]:
    return client.post(
        STREAM_PATH,
        headers={"Authorization": f"Bearer {PERSON_TOKEN}"},
        json=body,
    )


_DIRECT_TURN = {"agent_id": "rags.sample.echo", "input": "hello"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unavailable", "expected_status", "cause"),
    [(True, 503, "standing_unavailable"), (False, 403, "standing_refused")],
)
async def test_direct_stream_preserves_standing_decision_at_http_boundary(
    monkeypatch, tmp_path, unavailable, expected_status, cause
) -> None:
    app = _person_pod(monkeypatch, tmp_path)
    connection = _Connection(app)
    async with _serving(connection) as client:
        _install_delegation()
        rebac = get_runtime_context().config.rebac_engine
        assert rebac is not None
        rebac.require_user_standing.side_effect = StandingAuthorizationError(
            unavailable=unavailable
        )
        response = await asyncio.wait_for(_post(client, _DIRECT_TURN), TIMEOUT)

    assert response.status_code == expected_status
    assert response.headers["X-Fred-Denial-Cause"] == cause
    assert "owner-a" not in response.text
    assert PERSON_TOKEN not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unavailable", "expected_status", "cause"),
    [(True, 503, "standing_unavailable"), (False, 403, "standing_refused")],
)
async def test_managed_stream_preserves_standing_decision_at_http_boundary(
    monkeypatch, tmp_path, unavailable, expected_status, cause
) -> None:
    app = _person_pod(monkeypatch, tmp_path)
    connection = _Connection(app)
    async with _serving(connection) as client:
        _install_delegation()
        rebac = get_runtime_context().config.rebac_engine
        assert rebac is not None
        rebac.check_user_team_permission_or_raise.side_effect = (
            StandingAuthorizationError(unavailable=unavailable)
        )
        response = await asyncio.wait_for(
            _post(
                client,
                {
                    "agent_instance_id": "instance-a",
                    "input": "hello",
                    "runtime_context": {"team_id": "team-a"},
                },
            ),
            TIMEOUT,
        )

    assert response.status_code == expected_status
    assert response.headers["X-Fred-Denial-Cause"] == cause
    assert "owner-a" not in response.text
    assert PERSON_TOKEN not in response.text


@pytest.mark.asyncio
async def test_delegated_history_failure_log_omits_identifiers_and_exception(
    caplog,
) -> None:
    class FailingHistory:
        async def next_rank(self, session_id: str) -> int:
            raise RuntimeError("endpoint-secret-session-a")

    _install_delegation()
    caplog.set_level(logging.ERROR, logger=agent_app_module.__name__)

    await _write_turn_history(
        session_id="session-a",
        user_id="person-a",
        request_message="hello",
        payloads=[],
        history_store=cast(Any, FailingHistory()),
    )

    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == agent_app_module.__name__
    ] == ["event=turn_history outcome=failed reason=rank_query_failed"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "expected_kind", "model_index"),
    [
        (
            [AIMessage(content="done"), AIMessage(content="unexpected rerun")],
            "final",
            1,
        ),
        ([], "execution_error", 0),
    ],
)
async def test_a_delegated_stream_runs_once_and_carries_no_run_handle(
    monkeypatch, tmp_path, caplog, responses, expected_kind, model_index
) -> None:
    caplog.set_level(logging.DEBUG, logger=agent_app_module.__name__)
    model = ToolFriendlyFakeChatModel(responses=responses)
    app = _person_pod(monkeypatch, tmp_path, model=model)
    run_ids = _admitted_run_ids(monkeypatch)
    control_plane_requests: list[httpx.Request] = []

    def control_plane(request: httpx.Request) -> httpx.Response:
        control_plane_requests.append(request)
        return httpx.Response(500)

    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        await _install_control_plane_transport(app, httpx.MockTransport(control_plane))
        response = await asyncio.wait_for(_post(client, _DIRECT_TURN), TIMEOUT)

    assert response.status_code == 200
    assert "x-fred-run-id" not in response.headers
    assert not any(line.startswith("id:") for line in response.text.splitlines())
    assert _payloads(response.text)[-1]["kind"] == expected_kind
    assert model.i == model_index
    # A direct run resolves locally: nothing reaches the control plane.
    assert control_plane_requests == []
    assert len(run_ids) == 1
    assert len(runtime.records) == 0
    delegated_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == agent_app_module.__name__
    )
    for identifier in ("owner-a", run_ids[0], "rags.sample.echo", PERSON_TOKEN):
        assert identifier not in delegated_logs


@pytest.mark.asyncio
async def test_a_cancelled_request_ends_the_run_and_its_children(
    monkeypatch, tmp_path
) -> None:
    """A: the request task is cancelled while the executor waits."""
    started = asyncio.Event()
    children: list[asyncio.Task[Any]] = []

    async def stream() -> AsyncGenerator[RuntimeEvent, None]:
        child = asyncio.create_task(asyncio.Event().wait())
        register_run_child(child)
        children.append(child)
        started.set()
        await asyncio.Event().wait()
        yield StatusRuntimeEvent(status="unreachable")  # pragma: no cover

    app = _person_pod(monkeypatch, tmp_path)
    _executor_runtime(monkeypatch, stream)
    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        request = asyncio.ensure_future(_post(client, _DIRECT_TURN))
        await asyncio.wait_for(started.wait(), TIMEOUT)
        assert len(runtime.records) == 1

        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(request, TIMEOUT)

        assert len(runtime.records) == 0
        assert children[0].done()
        assert children[0].cancelled()
        assert not any(
            payload.get("kind") == "final"
            for frame in connection.frames
            for payload in _payloads(frame)
        )


@pytest.mark.asyncio
async def test_a_stream_dropped_after_its_first_frame_ends_with_the_response(
    monkeypatch, tmp_path
) -> None:
    """B: the client reads one frame and leaves while the next waits in `send`,
    so the disconnect never reaches the stream; the response's end does."""
    second_frame = asyncio.Event()
    children: list[asyncio.Task[Any]] = []
    stream_tasks: list[asyncio.Task[Any]] = []

    async def stream() -> AsyncGenerator[RuntimeEvent, None]:
        stream_tasks.append(cast(asyncio.Task[Any], asyncio.current_task()))
        child = asyncio.create_task(asyncio.Event().wait())
        register_run_child(child)
        children.append(child)
        yield StatusRuntimeEvent(status="working")
        second_frame.set()
        yield StatusRuntimeEvent(status="still working")
        await asyncio.Event().wait()  # pragma: no cover

    at_cleanup: dict[str, Any] = {}

    def cleanup() -> None:
        # The run's own cleanup starts only once it can obtain no credential
        # and its children are already cancelled.
        record = runtime.records.get(run_ids[0])
        at_cleanup["terminal"] = record is not None and record.terminal
        at_cleanup["child_stopped"] = children[0].cancelling() > 0

    app = _person_pod(monkeypatch, tmp_path)
    run_ids = _admitted_run_ids(monkeypatch)
    _executor_runtime(monkeypatch, stream, on_dispose=cleanup)
    streams = _keep_streams(monkeypatch)
    connection = _Connection(app, hold_first_frame=True)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        connection.on_end = lambda: {
            "records": len(runtime.records),
            "child_stopped": children[0].done(),
        }
        request = asyncio.ensure_future(_post(client, _DIRECT_TURN))
        await asyncio.wait_for(second_frame.wait(), TIMEOUT)
        assert len(connection.frames) == 1

        # The client stays busy on the first frame until the disconnect has
        # cancelled the response task where it waits, in `send`.
        connection.drop()
        await asyncio.wait_for(asyncio.wait(stream_tasks), TIMEOUT)
        assert stream_tasks[0].cancelled()
        connection.release()
        response = await asyncio.wait_for(request, TIMEOUT)

        assert response.status_code == 200
        assert connection.at_end == {"records": 0, "child_stopped": True}
        assert at_cleanup == {"terminal": True, "child_stopped": True}
        assert children[0].done()
        assert children[0].cancelled()
        assert [p["kind"] for p in _payloads(response.content)] == ["status"]
        assert len(streams) == 1


@pytest.mark.asyncio
async def test_a_stream_dropped_before_its_first_frame_releases_the_record(
    monkeypatch, tmp_path
) -> None:
    """C: the connection goes before the stream reaches the run, so nothing in
    the stream ever owned the record the admission wrote."""
    entered = asyncio.Event()

    async def _never_resolves(**kwargs: Any) -> str:
        entered.set()
        await asyncio.Event().wait()
        return "unreachable"  # pragma: no cover

    app = _person_pod(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", _never_resolves)
    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        connection.on_end = lambda: {"records": len(runtime.records)}
        request = asyncio.ensure_future(_post(client, _DIRECT_TURN))
        await asyncio.wait_for(entered.wait(), TIMEOUT)
        assert len(runtime.records) == 1

        connection.drop()
        response = await asyncio.wait_for(request, TIMEOUT)

    assert response.status_code == 200
    assert connection.frames == []
    assert connection.at_end == {"records": 0}


@pytest.mark.asyncio
async def test_a_request_cancelled_while_a_frame_waits_in_send_ends_the_run(
    monkeypatch, tmp_path
) -> None:
    """The response task itself is cancelled while the stream waits at a
    `yield`: the response raises instead of ending, and the run still ends."""
    second_frame = asyncio.Event()
    children: list[asyncio.Task[Any]] = []

    async def stream() -> AsyncGenerator[RuntimeEvent, None]:
        child = asyncio.create_task(asyncio.Event().wait())
        register_run_child(child)
        children.append(child)
        yield StatusRuntimeEvent(status="working")
        second_frame.set()
        yield StatusRuntimeEvent(status="still working")
        await asyncio.Event().wait()  # pragma: no cover

    app = _person_pod(monkeypatch, tmp_path)
    _executor_runtime(monkeypatch, stream)
    streams = _keep_streams(monkeypatch)
    connection = _Connection(app, hold_first_frame=True)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        request = asyncio.ensure_future(_post(client, _DIRECT_TURN))
        await asyncio.wait_for(second_frame.wait(), TIMEOUT)
        assert len(streams) == 1
        assert len(runtime.records) == 1

        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(request, TIMEOUT)

        assert len(runtime.records) == 0
        assert children[0].done()
        assert children[0].cancelled()


@pytest.mark.asyncio
async def test_a_stream_failing_before_its_first_frame_releases_the_record(
    monkeypatch, tmp_path
) -> None:
    """The response raises before the stream reaches the run, so nothing in the
    stream ever owned the record the admission wrote."""

    async def _fails(**kwargs: Any) -> str:
        raise RuntimeError("synthetic history failure")

    app = _person_pod(monkeypatch, tmp_path)
    monkeypatch.setattr(agent_app_module, "_resolve_exchange_id", _fails)
    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        with pytest.raises(RuntimeError, match="synthetic history failure"):
            await asyncio.wait_for(_post(client, _DIRECT_TURN), TIMEOUT)

        assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_a_human_pause_ends_the_stream(monkeypatch, tmp_path) -> None:
    """D: the run pauses for a person and the response completes on its own."""

    async def stream() -> AsyncGenerator[RuntimeEvent, None]:
        yield AwaitingHumanRuntimeEvent(
            request=HumanInputRequest(question="Proceed?", checkpoint_id="cp-a")
        )

    app = _person_pod(monkeypatch, tmp_path)
    _executor_runtime(monkeypatch, stream)
    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        response = await asyncio.wait_for(_post(client, _DIRECT_TURN), TIMEOUT)

        assert response.status_code == 200
        assert [p["kind"] for p in _payloads(response.content)] == ["awaiting_human"]
        assert len(runtime.records) == 0


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_disposal_and_child_cleanup(
    monkeypatch, tmp_path
) -> None:
    disposing = asyncio.Event()
    release = asyncio.Event()
    disposed = asyncio.Event()
    child_cleaned = asyncio.Event()
    children: list[asyncio.Task[Any]] = []

    async def child() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()
            child_cleaned.set()

    async def stream() -> AsyncGenerator[RuntimeEvent, None]:
        task = asyncio.create_task(child())
        register_run_child(task)
        children.append(task)
        yield AwaitingHumanRuntimeEvent(
            request=HumanInputRequest(question="Proceed?", checkpoint_id="cp-a")
        )

    async def dispose() -> None:
        disposing.set()
        await release.wait()
        disposed.set()

    app = _person_pod(monkeypatch, tmp_path)
    run_ids = _admitted_run_ids(monkeypatch)
    _executor_runtime(monkeypatch, stream, on_dispose=dispose)
    connection = _Connection(app)
    async with _serving(connection) as client:
        runtime = _install_delegation()
        request = asyncio.ensure_future(_post(client, _DIRECT_TURN))
        await asyncio.wait_for(disposing.wait(), TIMEOUT)
        record = runtime.records.get(run_ids[0])
        assert record is not None and record.terminal
        request.cancel()
        request.cancel()
        release.set()
        await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), TIMEOUT)
        assert len(runtime.records) == 0
        assert child_cleaned.is_set()
        assert disposed.is_set()
        assert children[0].done()


@pytest.mark.asyncio
async def test_the_stream_route_has_no_reconnect_surface(monkeypatch, tmp_path) -> None:
    """E: no reconnect body, schema or exposed run handle."""
    app = _person_pod(
        monkeypatch,
        tmp_path,
        model=ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")]),
        authorized_origins=["http://ui.test"],
    )
    run_ids = _admitted_run_ids(monkeypatch)
    connection = _Connection(app)
    async with _serving(connection) as client:
        _install_delegation()
        reconnect = await asyncio.wait_for(
            _post(client, {"reconnect": {"run_id": "run-a"}}), TIMEOUT
        )
        streamed = await asyncio.wait_for(
            client.post(
                STREAM_PATH,
                headers={
                    "Authorization": f"Bearer {PERSON_TOKEN}",
                    "Origin": "http://ui.test",
                },
                json=_DIRECT_TURN,
            ),
            TIMEOUT,
        )

    assert reconnect.status_code == 422
    assert len(run_ids) == 1  # the streamed turn's; the reconnect body admitted none
    assert streamed.status_code == 200
    assert streamed.headers["access-control-allow-origin"] == "http://ui.test"
    assert "access-control-expose-headers" not in streamed.headers
    assert "x-fred-run-id" not in streamed.headers
    schema = app.openapi()
    assert not {"RuntimeReconnect", "RuntimeReconnectRequest"} & set(
        schema["components"]["schemas"]
    )
    body = schema["paths"][STREAM_PATH]["post"]["requestBody"]
    assert body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RuntimeExecuteRequest"
    }


def test_a_human_resume_is_a_fresh_admission_with_the_current_token(
    monkeypatch, tmp_path
) -> None:
    decoded_tokens: list[str] = []
    streamed_run_ids: list[str] = []

    def decode(token: str) -> KeycloakUser:
        decoded_tokens.append(token)
        return KeycloakUser(
            uid="owner-a", username="synthetic", roles=[], client_id="browser"
        )

    async def stream(*args, **kwargs):
        streamed_run_ids.append(kwargs["credential_provider"].run_id)
        kind = "final" if args[1].resume_payload is not None else "awaiting_human"
        yield f'data: {{"kind":"{kind}"}}\n\n'

    app = _person_pod(monkeypatch, tmp_path, decode=decode)
    monkeypatch.setattr(agent_app_module, "_stream", stream)
    control_plane_requests: list[httpx.Request] = []

    def control_plane(request: httpx.Request) -> httpx.Response:
        control_plane_requests.append(request)
        return httpx.Response(500)

    with TestClient(app) as client:
        runtime = _install_delegation()
        _portal_call(
            client,
            _install_control_plane_transport,
            app,
            httpx.MockTransport(control_plane),
        )
        runtime_context = get_runtime_context()
        runtime_context._config = replace(runtime_context.config, checkpointer=None)
        paused = client.post(
            STREAM_PATH,
            headers={"Authorization": "Bearer person-token"},
            json=_DIRECT_TURN,
        )
        resumed = client.post(
            STREAM_PATH,
            headers={"Authorization": "Bearer current-person-token"},
            json={
                "agent_id": "rags.sample.echo",
                "session_id": "session-a",
                "resume_payload": {"choice_id": "continue"},
            },
        )

    assert paused.status_code == 200
    assert '"kind":"awaiting_human"' in paused.text
    assert resumed.status_code == 200
    assert '"kind":"final"' in resumed.text
    assert decoded_tokens[-1] == "current-person-token"
    assert len(streamed_run_ids) == 2
    assert streamed_run_ids[0] != streamed_run_ids[1]
    assert len(runtime.records) == 0
    assert control_plane_requests == []
