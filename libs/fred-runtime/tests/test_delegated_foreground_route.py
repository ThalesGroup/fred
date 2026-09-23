from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import fred_runtime.app.agent_app as agent_app_module
import httpx
import pytest
from fastapi.testclient import TestClient
from fred_core.security import oidc as oidc_module
from fred_core.security.delegation import DelegationConfig, initialize_delegation
from fred_core.security.structure import KeycloakUser
from fred_runtime.app.agent_app import _write_turn_history, create_agent_app
from fred_runtime.app.config import PodExecutionConfig
from fred_runtime.app.dependencies import get_pod_container_from_app
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    RunRecord,
    set_delegation_runtime,
)
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support.foreground_runs import ForegroundRun
from langchain_core.messages import AIMessage
from test_agent_app import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    _build_test_config,
    _EchoAgent,
    _StaticWorkloadTokens,
)


@pytest.fixture(autouse=True)
def _restore_process_security() -> Iterator[None]:
    keycloak_enabled = oidc_module.KEYCLOAK_ENABLED
    yield
    oidc_module.KEYCLOAK_ENABLED = keycloak_enabled
    initialize_delegation(DelegationConfig())
    set_delegation_runtime(None)


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


def _portal_call(client: TestClient, func, *args):
    assert client.portal is not None
    return client.portal.call(func, *args)


@pytest.mark.asyncio
async def test_delegated_history_failure_log_omits_identifiers_and_exception(
    caplog,
) -> None:
    class FailingHistory:
        async def next_rank(self, session_id: str) -> int:
            raise RuntimeError("endpoint-secret-session-a")

    set_delegation_runtime(
        DelegationRuntime(
            config=DelegationConfig(enabled=True, allowed_callers=["runtime-client"]),
            token_provider=_StaticWorkloadTokens(),
            workload_client_id="runtime-client",
        )
    )
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


@pytest.mark.parametrize(
    (
        "responses",
        "expected_kind",
        "expected_outcome",
        "expected_reason",
        "model_index",
    ),
    [
        (
            [AIMessage(content="done"), AIMessage(content="unexpected rerun")],
            "final",
            "succeeded",
            None,
            1,
        ),
        ([], "execution_error", "failed", None, 0),
    ],
)
def test_initial_delegated_foreground_stream_reports_and_replays_once(
    monkeypatch,
    tmp_path,
    caplog,
    responses,
    expected_kind,
    expected_outcome,
    expected_reason,
    model_index,
) -> None:
    caplog.set_level(logging.DEBUG, logger=agent_app_module.__name__)
    model = ToolFriendlyFakeChatModel(responses=responses)
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="owner-a",
            username="synthetic",
            roles=[],
            client_id="browser",
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
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(
            tmp_path,
            control_plane_url="http://control-plane.test/control-plane/v1",
            user_security_enabled=True,
            delegation_allowed_callers=["runtime-client"],
        ),
    )
    requests: list[httpx.Request] = []

    def control_plane(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/agent-runs"):
            return httpx.Response(
                200,
                json={
                    "run_id": request.url.params["run"],
                    "run_ceiling_seconds": 60,
                    "binding": None,
                },
            )
        if request.url.path.endswith("/end"):
            return httpx.Response(200, json={})
        return httpx.Response(500)

    with TestClient(app) as client:
        set_delegation_runtime(
            DelegationRuntime(
                config=DelegationConfig(
                    enabled=True, allowed_callers=["runtime-client"]
                ),
                token_provider=_StaticWorkloadTokens(),
                workload_client_id="runtime-client",
            )
        )
        _portal_call(
            client,
            _install_control_plane_transport,
            app,
            httpx.MockTransport(control_plane),
        )
        response = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer person-token"},
            json={"agent_id": "rags.sample.echo", "input": "hello"},
        )
        run_id = response.headers["x-fred-run-id"]
        replay = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer refreshed-person-token"},
            json={"reconnect": {"run_id": run_id}},
        )

    assert response.status_code == 200
    assert "id: 0" in response.text
    assert '"sequence": 0' in response.text
    assert f'"kind": "{expected_kind}"' in response.text
    assert replay.status_code == 200
    assert replay.headers["x-fred-run-id"] == run_id
    assert replay.text == response.text
    assert model.i == model_index

    registration = [
        request for request in requests if request.url.path.endswith("/agent-runs")
    ]
    terminal = [request for request in requests if request.url.path.endswith("/end")]
    assert len(registration) == 1
    assert len(terminal) == 1
    assert registration[0].url.params["person"] == "owner-a"
    assert registration[0].url.params["run"] == run_id
    assert registration[0].url.params["agent"] == "rags.sample.echo"
    assert all(
        request.headers["authorization"] == "Bearer workload-token"
        for request in requests
    )
    assert b"person-token" not in b"\n".join(request.content for request in requests)
    assert json.loads(terminal[0].read()) == {
        "outcome": expected_outcome,
        "reason": expected_reason,
    }
    delegated_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == agent_app_module.__name__
    )
    for identifier in ("owner-a", run_id, "rags.sample.echo", "person-token"):
        assert identifier not in delegated_logs


def test_human_resume_after_grace_is_a_fresh_admission_with_current_token(
    monkeypatch, tmp_path
) -> None:
    decoded_tokens: list[str] = []
    resumed_executions: list[str] = []
    paused_executions: list[str] = []
    paused_data_calls: list[str] = []
    paused_terminal_reports: list[tuple[str, str | None]] = []

    def decode(token: str) -> KeycloakUser:
        decoded_tokens.append(token)
        return KeycloakUser(
            uid="owner-a", username="synthetic", roles=[], client_id="browser"
        )

    async def stream(*args, **kwargs):
        resumed_executions.append("started")
        yield 'data: {"kind":"final","content":"resumed"}\n\n'

    async def expire_paused_run(app) -> None:
        ended = asyncio.Event()

        async def paused_source():
            paused_executions.append("started")
            yield 'data: {"kind":"awaiting_human","checkpoint_id":"checkpoint-a"}\n\n'
            await asyncio.Event().wait()
            paused_data_calls.append("called")  # pragma: no cover

        async def on_end(outcome: str, reason: str | None) -> None:
            paused_terminal_reports.append((outcome, reason))
            ended.set()

        run = ForegroundRun(
            RunRecord(
                run_id="paused-run",
                person_id="owner-a",
                agent_id="rags.sample.echo",
                mode="attended",
                run_ceiling_seconds=60,
            ),
            paused_source(),
            limits=app.state.foreground_runs.limits,
            on_end=on_end,
            on_cancel=lambda reason: None,
        )
        app.state.foreground_runs.add(run)
        attachment = await run.attach(None)
        run.start()
        await anext(attachment)
        await cast(AsyncGenerator[str, None], attachment).aclose()
        await asyncio.wait_for(ended.wait(), 0.2)

    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(
            ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
        ),
    )
    monkeypatch.setattr(agent_app_module, "_stream", stream)
    monkeypatch.setattr(oidc_module, "decode_jwt", decode)
    monkeypatch.setattr(
        agent_app_module,
        "rebac_factory",
        lambda *args, **kwargs: SimpleNamespace(
            enforces_standing=True,
            enabled=True,
            validate_standing_model=AsyncMock(),
            is_standing_seed_ready=AsyncMock(return_value=True),
            require_user_standing=AsyncMock(),
            check_user_team_permission_or_raise=AsyncMock(),
        ),
    )
    config = _build_test_config(
        tmp_path,
        control_plane_url="http://control-plane.test/control-plane/v1",
        user_security_enabled=True,
        delegation_allowed_callers=["runtime-client"],
    ).model_copy(
        update={
            "execution": PodExecutionConfig(
                reconnect_grace_seconds=0.01,
                run_ceiling_seconds=60,
            )
        }
    )
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()}, config=config
    )
    requests: list[httpx.Request] = []

    def control_plane(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/agent-runs"):
            return httpx.Response(
                200,
                json={
                    "run_id": request.url.params["run"],
                    "run_ceiling_seconds": 60,
                    "binding": None,
                },
            )
        if request.url.path.endswith("/end"):
            return httpx.Response(200, json={})
        return httpx.Response(500)

    with TestClient(app) as client:
        set_delegation_runtime(
            DelegationRuntime(
                config=DelegationConfig(
                    enabled=True, allowed_callers=["runtime-client"]
                ),
                token_provider=_StaticWorkloadTokens(),
                workload_client_id="runtime-client",
            )
        )
        _portal_call(
            client,
            _install_control_plane_transport,
            app,
            httpx.MockTransport(control_plane),
        )
        _portal_call(client, expire_paused_run, app)
        runtime_context = get_runtime_context()
        runtime_context._config = replace(
            runtime_context.config,
            checkpointer=None,
        )
        resumed = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer current-person-token"},
            json={
                "agent_id": "rags.sample.echo",
                "session_id": "session-a",
                "resume_payload": {"choice_id": "continue"},
            },
        )

    assert paused_executions == ["started"]
    assert paused_data_calls == []
    assert paused_terminal_reports == [("cancelled", "cancelled")]
    assert resumed.status_code == 200
    assert '"kind": "final"' in resumed.text
    assert resumed_executions == ["started"]
    assert decoded_tokens[-1] == "current-person-token"
    registrations = [r for r in requests if r.url.path.endswith("/agent-runs")]
    assert len(registrations) == 1
    assert registrations[0].url.params["run"] != "paused-run"
    assert len([r for r in requests if r.url.path.endswith("/end")]) == 1
    assert all(
        request.headers["authorization"] == "Bearer workload-token"
        for request in requests
    )
