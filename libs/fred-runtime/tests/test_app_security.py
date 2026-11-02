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

"""Weaver terms admission, independent of the route-test startup fixtures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app
from fred_runtime.app.dependencies import attach_pod_container
from fred_runtime.app.security import current_user, current_user_or_service

PERSON = KeycloakUser(uid="person-a", username="alice", roles=[])
SERVICE = KeycloakUser(uid="workload-a", username="worker", roles=["service_agent"])
DELEGATED = AssertedUser("person-a", "workload-a", "run-a", "agent-a")


def terms_app(subject, *, accepted=True, version="2026-10", error=None, app=None):
    connection = MagicMock()
    connection.scalar = AsyncMock(return_value=accepted, side_effect=error)
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
    app = app if app is not None else FastAPI()

    attach_pod_container(
        app,
        MagicMock(
            configuration=SimpleNamespace(app=SimpleNamespace(gcu_version=version)),
            get_sql_engine=lambda: engine,
        ),
    )

    async def authenticate(request: Request):
        return subject

    app.dependency_overrides[oidc.authenticate_request] = authenticate

    @app.get("/person")
    async def person(user=Depends(current_user)):
        return {"uid": user.uid}

    @app.get("/service")
    async def service(user=Depends(current_user_or_service)):
        return {"uid": user.uid}

    @app.get("/before-terms")
    async def before_terms(user=Depends(oidc.authenticate_request)):
        return {"uid": user.uid}

    return app, engine, connection


@pytest.mark.parametrize("subject", [PERSON, DELEGATED])
@pytest.mark.parametrize("path", ["/person", "/service"])
def test_terms_queries_canonical_person_and_configured_version(subject, path):
    app, engine, connection = terms_app(subject)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"uid": "person-a"}
    statement, parameters = connection.scalar.await_args.args
    assert "terms_acceptance" in str(statement)
    assert parameters == {"uid": "person-a", "version": "2026-10"}
    engine.connect.return_value.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("subject", [PERSON, DELEGATED])
@pytest.mark.parametrize("accepted", [False, None])
@pytest.mark.parametrize("path", ["/person", "/service"])
def test_missing_terms_refuses_person_and_delegated_person(subject, accepted, path):
    app, _, _ = terms_app(subject, accepted=accepted)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 403
    assert response.json() == {"detail": "user_not_accept_gcu"}


def test_terms_database_failure_is_unavailable_and_redacted():
    app, engine, _ = terms_app(PERSON, error=RuntimeError("private database details"))
    with TestClient(app) as client:
        response = client.get("/person")
    assert response.status_code == 503
    assert response.json() == {"detail": "terms_acceptance_unavailable"}
    assert "private" not in response.text
    engine.connect.return_value.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("path,expected", [("/service", 200), ("/person", 403)])
def test_service_exception_only_applies_to_service_routes(path, expected):
    app, _, connection = terms_app(SERVICE, accepted=False)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == expected
    assert connection.scalar.await_count == (path == "/person")


@pytest.mark.parametrize(
    "path,version", [("/before-terms", "2026-10"), ("/person", None)]
)
def test_unconfigured_or_pre_terms_routes_need_no_acceptance_query(path, version):
    app, engine, _ = terms_app(PERSON, accepted=False, version=version)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    engine.connect.assert_not_called()


@pytest.fixture
def mounted_pod(monkeypatch, minimal_config):
    """Construct production routes; fake IO without starting SQL/model services."""
    from fred_core.common import get_config
    from fred_runtime.capabilities import CapabilityRegistry
    from fred_runtime.common.outbound_credentials import (
        get_delegation_runtime,
        set_delegation_runtime,
    )

    previous = get_delegation_runtime()
    assert minimal_config.security is not None
    minimal_config.security.user.enabled = True
    minimal_config.app.base_url = ""
    monkeypatch.setattr(
        agent_app, "boot_capability_registry", lambda **kwargs: CapabilityRegistry()
    )
    try:
        app = agent_app.create_agent_app({}, minimal_config)
        assert set(app.dependency_overrides) == {get_config}
        yield app
    finally:
        set_delegation_runtime(previous)


PROTECTED_REQUESTS = [
    ("POST", "/agents/execute"),
    ("POST", "/agents/execute/stream"),
    ("POST", "/agents/evaluate"),
    ("POST", "/agents/sessions/session-a/steer"),
    ("GET", "/agents/sessions"),
    ("GET", "/agents/sessions/session-a/messages"),
    ("DELETE", "/agents/sessions/session-a"),
    ("GET", "/agents/checkpoints"),
    ("GET", "/agents/checkpoints/_stats"),
    ("GET", "/agents/checkpoints/session-a"),
    ("DELETE", "/agents/checkpoints/session-a"),
    ("POST", "/agents/capabilities/writable_document/validate-config"),
    ("POST", "/agents/creation-assistant/draft"),
]


@pytest.mark.parametrize("method,path", PROTECTED_REQUESTS)
@pytest.mark.parametrize(
    "accepted,error,status,detail",
    [
        (False, None, 403, "user_not_accept_gcu"),
        (
            True,
            RuntimeError("private SQL details"),
            503,
            "terms_acceptance_unavailable",
        ),
    ],
)
def test_mounted_routes_refuse_before_body_validation_or_business_logic(
    mounted_pod, monkeypatch, method, path, accepted, error, status, detail
):
    app, _, connection = terms_app(
        PERSON, app=mounted_pod, accepted=accepted, error=error
    )
    resolver = AsyncMock()
    monkeypatch.setattr(agent_app, "_authorize_and_resolve", resolver)
    # No lifespan: the real app's routes and middleware use the attached fake IO.
    client = TestClient(app)
    try:
        response = client.request(method, path, json={})
    finally:
        client.close()
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    connection.scalar.assert_awaited_once()
    resolver.assert_not_awaited()


@pytest.mark.parametrize("method,path", PROTECTED_REQUESTS)
def test_mounted_routes_reject_invalid_jwt_before_terms(
    mounted_pod, monkeypatch, method, path
):
    app, engine, _ = terms_app(PERSON, app=mounted_pod)
    del app.dependency_overrides[oidc.authenticate_request]
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    client = TestClient(app)
    try:
        response = client.request(
            method, path, json={}, headers={"Authorization": "Bearer malformed"}
        )
    finally:
        client.close()
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    engine.connect.assert_not_called()


@pytest.mark.parametrize("path", ["/agents/sessions", "/agents/checkpoints"])
@pytest.mark.parametrize(
    "accepted,detail",
    [(False, "user_not_accept_gcu"), (True, "requires_own_credential")],
)
def test_mounted_history_requires_own_credential_after_terms(
    mounted_pod, path, accepted, detail
):
    app, _, connection = terms_app(DELEGATED, app=mounted_pod, accepted=accepted)
    client = TestClient(app)
    try:
        response = client.get(path)
    finally:
        client.close()
    assert response.status_code == 403
    assert response.json() == {"detail": detail}
    assert connection.scalar.await_args.args[1]["uid"] == DELEGATED.uid


@pytest.mark.parametrize("subject", [PERSON, DELEGATED])
@pytest.mark.parametrize(
    "path", ["/agents/execute", "/agents/execute/stream", "/agents/evaluate"]
)
@pytest.mark.parametrize("resume", [None, {"answer": "continue"}])
def test_mounted_execution_passes_admitted_person_once(
    mounted_pod, monkeypatch, subject, path, resume
):
    app, _, connection = terms_app(subject, app=mounted_pod)
    resolver = AsyncMock(side_effect=HTTPException(409, "resolver-reached"))
    monkeypatch.setattr(agent_app, "_authorize_and_resolve", resolver)
    client = TestClient(app)
    try:
        response = client.post(
            path,
            json={
                "agent_instance_id": "instance-a",
                "session_id": "session-a",
                "input": "hello",
                "resume_payload": resume,
                "runtime_context": {"space_id": "space-a"},
            },
        )
    finally:
        client.close()
    assert response.status_code == 409
    assert response.json() == {"detail": "resolver-reached"}
    resolver.assert_awaited_once()
    assert resolver.await_args is not None
    assert resolver.await_args.kwargs["authenticated_user"] is subject
    connection.scalar.assert_awaited_once()
