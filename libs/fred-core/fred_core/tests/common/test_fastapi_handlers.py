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
    assert "Authorization denied for user alice" in caplog.text


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
    assert "Unhandled exception in GET http://testserver/explode: boom" in caplog.text


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
