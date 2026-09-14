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

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.security.models import AuthorizationError, Resource


def test_authorization_error_handler_returns_team_specific_detail(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/teams")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="can_update_agents",
            resource=Resource.TEAM,
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/teams")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You are not allowed to manage agents in this team. Ask a team admin or editor."
    }
    assert "Authorization denied" in caplog.text
    assert "alice" not in caplog.text


def test_authorization_error_handler_humanizes_generic_resource_action() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/documents")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="read:global",
            resource=Resource.DOCUMENTS,
        )

    response = TestClient(app, raise_server_exceptions=False).get("/documents")

    assert response.status_code == 403
    assert response.json() == {"detail": "You are not allowed to read global document."}


def test_authorization_error_handler_does_not_label_a_team_subject_as_a_user(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/capability")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="team-1",
            action="can_use",
            resource=Resource.CAPABILITY,
            subject_type=Resource.TEAM,
            subject_id="team-1",
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/capability")

    assert response.status_code == 403
    assert "Authorization denied" in caplog.text
    assert "team-1" not in caplog.text


def test_authorization_error_handler_distinguishes_actor_from_team_subject(
    caplog,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/capability")
    async def denied() -> None:
        raise AuthorizationError(
            user_id="alice",
            action="can_use",
            resource=Resource.CAPABILITY,
            actor_uid="alice",
            subject_type=Resource.TEAM,
            subject_id="team-1",
        )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/capability")

    assert response.status_code == 403
    assert "Authorization denied" in caplog.text
    assert "alice" not in caplog.text
    assert "team-1" not in caplog.text


def test_generic_exception_handler_returns_internal_server_error(caplog) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get("/explode")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "Unhandled request failure" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.parametrize("with_actor", [False, True])
def test_authorization_handler_logs_no_identity_or_exception_chain(
    caplog, with_actor: bool
) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    canaries = ("actor-canary", "subject-canary", "cause-canary")

    @app.get("/denied")
    async def denied() -> None:
        raise AuthorizationError(
            user_id=canaries[0],
            action="can_use",
            resource=Resource.APP,
            actor_uid=canaries[0] if with_actor else None,
            subject_type=Resource.TEAM,
            subject_id=canaries[1],
        ) from RuntimeError(canaries[2])

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).get("/denied")

    assert response.status_code == 403
    records = [
        record
        for record in caplog.records
        if record.name == "fred_core.common.fastapi_handlers"
    ]
    assert [record.getMessage() for record in records] == ["Authorization denied"]
    for record in records:
        assert not record.args
        assert record.exc_info is None
        rendered = logging.Formatter().format(record)
        assert all(canary not in rendered for canary in canaries)


def test_generic_handler_logs_no_request_or_chained_exception_details(caplog) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    canaries = ("route-canary", "query-canary", "error-canary", "cause-canary")

    @app.get("/route-canary")
    async def failure() -> None:
        raise RuntimeError(canaries[2]) from ValueError(canaries[3])

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get(
            "/route-canary?key=query-canary"
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    records = [
        record
        for record in caplog.records
        if record.name == "fred_core.common.fastapi_handlers"
    ]
    assert [record.getMessage() for record in records] == ["Unhandled request failure"]
    for record in records:
        assert not record.args
        assert record.exc_info is None
        rendered = logging.Formatter().format(record)
        assert all(canary not in rendered for canary in canaries)


def test_authorization_error_is_a_permission_error() -> None:
    """A ReBAC denial raised via `check_permission_or_raise` must be catchable by
    any call site's plain `except PermissionError` — the standard denial -> 403
    mapping used across the codebase — without that call site needing its own
    `except AuthorizationError` clause. Without this, a route with only
    `except PermissionError: ... except Exception: 500` (e.g. the tabular
    controller) turns a real denial into an unhandled 500."""
    exc = AuthorizationError(user_id="alice", action="read", resource=Resource.TAGS)
    assert isinstance(exc, PermissionError)


def test_local_permission_error_handler_still_catches_authorization_error() -> None:
    """Reproduces the exact shape of a route that has its own local exception
    chain (`except PermissionError -> 403`, `except Exception -> 500`) instead of
    relying on the app-wide `AuthorizationError` handler above — the pattern in
    `tabular/controller.py`. Before `AuthorizationError` inherited from
    `PermissionError`, this fell through to the generic 500 branch."""
    app = FastAPI()

    @app.get("/query")
    async def denied() -> None:
        try:
            raise AuthorizationError(
                user_id="alice", action="read", resource=Resource.TAGS
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    response = TestClient(app, raise_server_exceptions=False).get("/query")
    assert response.status_code == 403
