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
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import KeycloakUser
from fred_runtime.app.security import install_admission

PERSON = KeycloakUser(uid="person-a", username="alice", roles=[])
SERVICE = KeycloakUser(uid="workload-a", username="worker", roles=["service_agent"])
DELEGATED = AssertedUser("person-a", "workload-a", "run-a", "agent-a")


def terms_app(subject, *, accepted=True, version="2026-10", error=None):
    from fastapi import Depends

    connection = MagicMock()
    connection.scalar = AsyncMock(return_value=accepted, side_effect=error)
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
    app = FastAPI()
    from fred_runtime.app.dependencies import attach_pod_container

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
    install_admission(app)

    @app.get("/person")
    async def person(user=Depends(oidc.get_current_user)):
        return {"uid": user.uid}

    @app.get("/service")
    async def service(user=Depends(oidc.get_current_user_or_service)):
        return {"uid": user.uid}

    @app.get("/before-terms")
    async def before_terms(user=Depends(oidc.get_current_user_before_gcu)):
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
def test_missing_terms_refuses_person_and_delegated_person(subject, accepted):
    app, _, _ = terms_app(subject, accepted=accepted)
    with TestClient(app) as client:
        response = client.get("/person")
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
