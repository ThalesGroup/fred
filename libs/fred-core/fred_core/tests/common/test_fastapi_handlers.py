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

from fastapi import FastAPI
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
