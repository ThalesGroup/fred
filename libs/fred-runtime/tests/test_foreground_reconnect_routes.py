from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fred_runtime.app.agent_app as agent_app_module
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fred_core.security import oidc as oidc_module
from fred_core.security.delegation import (
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser
from fred_runtime.app.agent_app import create_agent_app
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    RunRecord,
    set_delegation_runtime,
)
from fred_runtime.runtime_support.foreground_runs import ForegroundRun
from test_agent_app import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    _build_test_config,
    _EchoAgent,
    _StaticWorkloadTokens,
)


@pytest.fixture(autouse=True)
def _restore_security() -> Iterator[None]:
    enabled = oidc_module.KEYCLOAK_ENABLED
    yield
    oidc_module.KEYCLOAK_ENABLED = enabled
    initialize_delegation(DelegationConfig())
    set_delegation_runtime(None)


def _app(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(ToolFriendlyFakeChatModel(responses=[])),
    )
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="owner-a" if token == "owner-token" else "workload-subject",
            username="synthetic",
            roles=[] if token == "owner-token" else ["service_agent"],
            client_id="browser" if token == "owner-token" else "runtime-client",
            token_issuer="https://issuer.test/realms/fred",
            token_audiences=frozenset({"agent-runtime"}),
            token_type="Bearer",
        ),
    )
    monkeypatch.setattr(
        agent_app_module,
        "rebac_factory",
        lambda *args, **kwargs: SimpleNamespace(
            enforces_standing=True,
            enabled=True,
            validate_standing_model=AsyncMock(),
            is_standing_seed_ready=AsyncMock(return_value=True),
            require_user_standing=AsyncMock(),
        ),
    )
    app = create_agent_app(
        registry={_EchoAgent().agent_id: _EchoAgent()},
        config=_build_test_config(
            tmp_path,
            user_security_enabled=True,
            delegation_allowed_callers=["runtime-client"],
        ),
    )
    set_delegation_runtime(
        DelegationRuntime(
            config=DelegationConfig(enabled=True, allowed_callers=["runtime-client"]),
            token_provider=_StaticWorkloadTokens(),
            workload_client_id="runtime-client",
        )
    )
    monkeypatch.setattr(agent_app_module, "_authorize_execution_or_raise", AsyncMock())
    return app


def _record() -> RunRecord:
    return RunRecord(
        run_id="run-a",
        person_id="owner-a",
        agent_id="rags.sample.echo",
        mode="attended",
        run_ceiling_seconds=60,
    )


async def _add_completed_run(
    app, *, cancelled: list[str] | None = None
) -> ForegroundRun:
    ended = asyncio.Event()

    async def source():
        yield f"data: {json.dumps({'kind': 'final', 'content': 'done'})}\n\n"

    async def on_end(outcome, reason):
        ended.set()

    run = ForegroundRun(
        _record(),
        source(),
        limits=app.state.foreground_runs.limits,
        on_end=on_end,
        on_cancel=(cancelled if cancelled is not None else []).append,
    )
    app.state.foreground_runs.add(run)
    run.start()
    await ended.wait()
    return run


async def _add_expired_run(app) -> None:
    async def source():
        await asyncio.Event().wait()
        yield ""  # pragma: no cover

    async def on_end(outcome, reason):
        return None

    run = ForegroundRun(
        _record(),
        source(),
        limits=app.state.foreground_runs.limits,
        on_end=on_end,
        on_cancel=lambda reason: None,
    )
    app.state.foreground_runs.add(run)
    run.start()
    await run.cancel(grace=True)


async def _add_live_run(app, cancelled: list[str]) -> None:
    async def source():
        await asyncio.Event().wait()
        yield ""  # pragma: no cover

    async def on_end(outcome, reason):
        return None

    run = ForegroundRun(
        _record(),
        source(),
        limits=app.state.foreground_runs.limits,
        on_end=on_end,
        on_cancel=cancelled.append,
    )
    app.state.foreground_runs.add(run)
    run.start()


async def _drain(stream) -> None:
    async for _ in stream:
        pass


def _reconnect(client: TestClient, **body):
    return client.post(
        "/pod/v1/agents/execute/stream",
        headers={"Authorization": "Bearer owner-token"},
        json={"reconnect": {"run_id": "run-a", **body}},
    )


def _portal_call(client: TestClient, func, *args):
    assert client.portal is not None
    return client.portal.call(func, *args)


def _enable_workload_delegation() -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id="runtime-client",
                    subject="workload-subject",
                )
            ],
        ),
        issuer="https://issuer.test/realms/fred",
        audience="agent-runtime",
    )


def test_reconnect_requires_current_owner_credential_and_replays_sequence(
    monkeypatch, tmp_path
) -> None:
    app = _app(monkeypatch, tmp_path)
    resolve = AsyncMock(side_effect=AssertionError("reconnect must not readmit"))
    monkeypatch.setattr(agent_app_module, "_authorize_and_resolve", resolve)
    with TestClient(app) as client:
        _portal_call(client, _add_completed_run, app)
        response = _reconnect(client)

    assert response.status_code == 200
    assert response.headers["x-fred-run-id"] == "run-a"
    assert "id: 0" in response.text
    assert '"sequence": 0' in response.text
    resolve.assert_not_awaited()


def test_reconnect_rejects_workload_grant_before_attachment(
    monkeypatch, tmp_path
) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        operation_id = app.openapi()["paths"]["/pod/v1/agents/execute/stream"]["post"][
            "operationId"
        ]
        assert operation_id
        _enable_workload_delegation()
        _portal_call(client, _add_completed_run, app)
        response = client.post(
            "/pod/v1/agents/execute/stream",
            params={"person": "owner-a", "run": "run-a", "agent": "rags.sample.echo"},
            headers={"Authorization": "Bearer reconnect-workload-token"},
            json={"reconnect": {"run_id": "run-a"}},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "requires_own_credential"


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/pod/v1/agents/sessions", {}),
        ("GET", "/pod/v1/agents/sessions/session-a/messages", {}),
        ("DELETE", "/pod/v1/agents/sessions/session-a", {}),
        ("GET", "/pod/v1/agents/checkpoints", {}),
        ("GET", "/pod/v1/agents/checkpoints/session-a", {}),
        ("DELETE", "/pod/v1/agents/checkpoints/session-a", {}),
        ("GET", "/pod/v1/agents/kpi-turns", {}),
        ("GET", "/pod/v1/agents/audit-events", {}),
        (
            "POST",
            "/pod/v1/agents/capabilities/demo_echo/validate-config",
            {"data": {"config": "{}"}},
        ),
        (
            "POST",
            "/pod/v1/agents/capabilities/chat-controls",
            {"json": {"items": []}},
        ),
        (
            "POST",
            "/v1/chat/completions",
            {
                "json": {
                    "model": "rags.sample.echo",
                    "messages": [{"role": "user", "content": "hello"}],
                }
            },
        ),
    ],
)
def test_retained_own_credential_routes_reject_asserted_subject(
    monkeypatch, tmp_path, method: str, path: str, request_kwargs: dict
) -> None:
    app = _app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        _enable_workload_delegation()
        response = client.request(
            method,
            path,
            params={"person": "owner-a", "run": "run-a", "agent": "rags.sample.echo"},
            headers={"Authorization": "Bearer workload-token"},
            **request_kwargs,
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "requires_own_credential"


def test_reconnect_owner_mismatch_does_not_cancel(monkeypatch, tmp_path) -> None:
    app = _app(monkeypatch, tmp_path)
    cancelled: list[str] = []
    monkeypatch.setattr(
        oidc_module,
        "decode_jwt",
        lambda token: KeycloakUser(
            uid="other", username="synthetic", roles=[], client_id="browser"
        ),
    )
    with TestClient(app) as client:
        _portal_call(client, partial(_add_completed_run, app, cancelled=cancelled))
        response = _reconnect(client)

    assert response.status_code == 403
    assert response.json()["detail"] == "run_owner_mismatch"
    assert cancelled == []


@pytest.mark.parametrize(
    "failure,status,cancelled",
    [
        (AuthorizationError("synthetic", "execute", Resource.AGENT), 403, True),
        (HTTPException(503), 503, False),
    ],
)
def test_reconnect_permission_failure_cancellation_policy(
    monkeypatch, tmp_path, failure: Exception, status: int, cancelled: bool
) -> None:
    app = _app(monkeypatch, tmp_path)
    reasons: list[str] = []
    monkeypatch.setattr(
        agent_app_module,
        "_authorize_execution_or_raise",
        AsyncMock(side_effect=failure),
    )
    with TestClient(app) as client:
        _portal_call(client, _add_live_run, app, reasons)
        response = _reconnect(client)
        assert response.status_code == status
        assert (reasons == ["authority_lost"]) is cancelled


def test_reconnect_rejects_conflict_and_unavailable_cursor(
    monkeypatch, tmp_path
) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        run = _portal_call(client, _add_completed_run, app)
        attachment = _portal_call(client, run.attach, None)
        conflict = _reconnect(client)
        _portal_call(client, _drain, attachment)
        unavailable = _reconnect(client, after_sequence=99)

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "run_already_attached"
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"] == "replay_unavailable"


def test_mixed_execute_and_reconnect_payload_is_rejected(monkeypatch, tmp_path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer owner-token"},
            json={
                "reconnect": {"run_id": "run-a"},
                "agent_id": "rags.sample.echo",
                "input": "must not execute",
            },
        )

    assert response.status_code == 422


def test_expired_reconnect_is_gone_but_unknown_is_not_found(
    monkeypatch, tmp_path
) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _portal_call(client, _add_expired_run, app)
        expired = _reconnect(client)
        unknown = client.post(
            "/pod/v1/agents/execute/stream",
            headers={"Authorization": "Bearer owner-token"},
            json={"reconnect": {"run_id": "unknown"}},
        )

    assert expired.status_code == 410
    assert unknown.status_code == 404
