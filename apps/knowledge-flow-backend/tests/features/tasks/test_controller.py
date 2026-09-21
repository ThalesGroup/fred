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

"""Reading one task's state: who may, and what they get back.

A Knowledge Base pod submits documents as a service identity, then polls this
route to learn when ingestion finished. It has no GCU record, so this one route
admits a workload without the human gate while every other task route keeps it;
what it may read is the shared task rule — creator, platform admin, team reader.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, Resource, get_current_user, get_current_user_or_service
from fred_core.common.fastapi_handlers import register_exception_handlers
from fred_core.security.structure import SERVICE_AGENT_ROLE
from fred_core.tasks.models import TaskState, TaskSummary

import knowledge_flow_backend.features.tasks.controller as controller_module
from knowledge_flow_backend.application_context import ApplicationContext

_NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
_TASK_ID = "task-1"
_CREATOR = "kb-pod"


class _FakeTaskService:
    """One task, held as the row the route authorizes on and the summary it returns."""

    def __init__(self, summary: TaskSummary) -> None:
        self._summary = summary
        self.reconciled: list[str] = []

    async def get_run(self, task_id: str) -> Any:
        if task_id != self._summary.task_id:
            return None
        return SimpleNamespace(created_by=self._summary.created_by, team_id=self._summary.team_id)

    async def reconcile_task(self, task_id: str) -> bool:
        self.reconciled.append(task_id)
        return False

    async def get_task(self, task_id: str) -> TaskSummary | None:
        return self._summary if task_id == self._summary.task_id else None


class _FakeRebac:
    """Grants nothing, so only the creator rule can admit a caller."""

    async def has_user_permission(self, user, permission, resource_id, **_kw) -> bool:
        return False

    async def check_user_team_permission_or_raise(self, user, permission, team_id) -> None:
        raise AuthorizationError(user.uid, permission.value, Resource.TEAM)


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The routes, plus the stub they reached, with no store or executor behind either."""
    summary = TaskSummary(
        task_id=_TASK_ID,
        kind="ingestion",
        state=TaskState.running,
        created_by=_CREATOR,
        team_id="team-1",
        created_at=_NOW,
        updated_at=_NOW,
    )
    service = _FakeTaskService(summary)
    monkeypatch.setattr(ApplicationContext, "get_task_service", lambda self: service)
    monkeypatch.setattr(controller_module, "get_rebac_engine", _FakeRebac)
    router = APIRouter()
    controller_module.TasksController(router)
    return SimpleNamespace(router=router, service=service, summary=summary)


def _client(tasks: SimpleNamespace, user: KeycloakUser) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(tasks.router)
    app.dependency_overrides[get_current_user_or_service] = lambda: user
    return TestClient(app)


def _service_identity(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[SERVICE_AGENT_ROLE], client_id="kb-pod")


def test_the_creator_reads_its_task_after_one_reconcile(tasks: SimpleNamespace) -> None:
    with _client(tasks, _service_identity(_CREATOR)) as client:
        response = client.get(f"/tasks/{_TASK_ID}")

    assert response.status_code == 200
    assert TaskSummary.model_validate(response.json()) == tasks.summary
    assert tasks.service.reconciled == [_TASK_ID]


def test_an_unknown_task_is_not_found(tasks: SimpleNamespace) -> None:
    with _client(tasks, _service_identity(_CREATOR)) as client:
        response = client.get("/tasks/missing")

    assert response.status_code == 404
    assert tasks.service.reconciled == []


def test_a_stranger_without_team_or_platform_right_is_refused(tasks: SimpleNamespace) -> None:
    with _client(tasks, _service_identity("someone-else")) as client:
        response = client.get(f"/tasks/{_TASK_ID}")

    assert response.status_code == 403
    assert tasks.service.reconciled == []


def _dependency_calls(router: APIRouter, path: str, method: str) -> set[Any]:
    route = next(r for r in router.routes if isinstance(r, APIRoute) and r.path == path and method in r.methods)
    return {d.call for d in route.dependant.dependencies}


def test_the_read_route_admits_a_service_without_human_admission(tasks: SimpleNamespace) -> None:
    calls = _dependency_calls(tasks.router, "/tasks/{task_id}", "GET")
    assert get_current_user_or_service in calls
    assert get_current_user not in calls


@pytest.mark.parametrize(
    "path,method",
    [
        ("/tasks", "GET"),
        ("/tasks/{task_id}/events", "GET"),
        ("/tasks/{task_id}/cancel", "POST"),
        ("/tasks/{task_id}/ack", "POST"),
    ],
)
def test_every_other_task_route_keeps_human_admission(tasks: SimpleNamespace, path: str, method: str) -> None:
    calls = _dependency_calls(tasks.router, path, method)
    assert get_current_user in calls
    assert get_current_user_or_service not in calls
