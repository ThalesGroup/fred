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

"""
Issue #2182: overload, timeout and invalid SQL must stay distinguishable.

An operator paging on tabular failures needs to tell "the pod is saturated,
retry" (503) from "this query ran too long" (504) from "the caller wrote bad
SQL" (400). Collapsing any of those into a 500 hides real outages behind caller
errors, which is exactly what the existing `TabularQueryError` -> 400 branch was
introduced to prevent.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.controller import TabularController
from knowledge_flow_backend.features.tabular.execution import (
    TabularCapacityExceededError,
    TabularExecutionTimeoutError,
    register_tabular_exception_handlers,
)
from knowledge_flow_backend.features.tabular.service import TabularQueryError


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", email="tester@example.com", roles=["admin"])


@pytest.fixture
def tabular_client(app_context: ApplicationContext):
    app = FastAPI()
    register_tabular_exception_handlers(app)
    router = APIRouter()
    controller = TabularController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    with TestClient(app) as client:
        yield client, controller


@pytest.mark.parametrize(
    ("raised", "expected_status"),
    [
        (TabularCapacityExceededError("saturated"), 503),
        (TabularExecutionTimeoutError("too slow"), 504),
        (TabularQueryError("no such column"), 400),
        (ValueError("references no authorized dataset"), 400),
        (PermissionError("nope"), 403),
        (FileNotFoundError("gone"), 404),
    ],
)
def test_read_query_maps_each_failure_to_its_own_status(tabular_client, raised, expected_status):
    client, controller = tabular_client

    async def _raise(*_args, **_kwargs):
        raise raised

    controller.service.query_read = _raise

    response = client.post("/tabular/query", json={"sql": "SELECT 1"})

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("raised", "expected_status"),
    [
        (TabularCapacityExceededError("saturated"), 503),
        (TabularExecutionTimeoutError("too slow"), 504),
        (ValueError("keyword too short"), 400),
    ],
)
def test_search_maps_each_failure_to_its_own_status(tabular_client, raised, expected_status):
    client, controller = tabular_client

    async def _raise(*_args, **_kwargs):
        raise raised

    controller.service.search_values = _raise

    response = client.post("/tabular/search", json={"keyword": "abc"})

    assert response.status_code == expected_status


@pytest.fixture
def content_client(app_context: ApplicationContext):
    """The CSV preview route renders from the Parquet artifact, so it shares the
    tabular execution budget and must surface the same 503/504 split."""
    from knowledge_flow_backend.features.content.content_controller import ContentController

    app = FastAPI()
    register_tabular_exception_handlers(app)
    router = APIRouter()
    controller = ContentController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, controller


@pytest.mark.parametrize(
    ("raised", "expected_status"),
    [
        (TabularCapacityExceededError("saturated"), 503),
        (TabularExecutionTimeoutError("too slow"), 504),
    ],
)
def test_markdown_preview_maps_tabular_execution_errors(content_client, raised, expected_status):
    client, controller = content_client

    async def _raise(*_args, **_kwargs):
        raise raised

    controller.service.get_markdown_preview = _raise

    response = client.get("/markdown/doc-1")

    assert response.status_code == expected_status, "a saturated pod must not turn a document preview into a 500"
