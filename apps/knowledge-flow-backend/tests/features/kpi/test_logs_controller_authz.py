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

"""`/logs/query` authz wiring (issue #2009).

Unlike `/kpi/query`, logs have no per-user "personal scope" — every query is a
platform-wide view across all users and services, so it requires
`CAN_OBSERVE_PLATFORM` unconditionally. Mirrors
`test_kpi_controller_authz.py`'s fake-rebac pattern.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission, Resource, get_current_user
from fred_core.common import register_exception_handlers

from knowledge_flow_backend.features.kpi import logs_controller as logs_controller_module


class _FakeLogStore:
    def __init__(self) -> None:
        self.queries: list[object] = []

    def query(self, body):
        self.queries.append(body)
        return {"events": []}


class _FakeRebac:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if self.deny:
            raise AuthorizationError(user.uid, str(permission), Resource.ORGANIZATION)


def _build_app(monkeypatch, rebac: _FakeRebac, store: _FakeLogStore) -> TestClient:
    class _FakeAppContext:
        def get_log_store(self) -> _FakeLogStore:
            return store

    monkeypatch.setattr(logs_controller_module, "get_app_context", lambda: _FakeAppContext())
    monkeypatch.setattr(logs_controller_module, "get_rebac_engine", lambda: rebac)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(logs_controller_module.router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", roles=[], email=None)
    return TestClient(app)


def _query_body() -> dict:
    return {"since": "now-24h", "limit": 100}


def test_query_logs_requires_can_observe_platform(monkeypatch) -> None:
    rebac = _FakeRebac(deny=False)
    store = _FakeLogStore()
    client = _build_app(monkeypatch, rebac, store)

    response = client.post("/logs/query", json=_query_body())

    assert response.status_code == 200
    assert rebac.calls == [(OrganizationPermission.CAN_OBSERVE_PLATFORM, "fred")]
    assert len(store.queries) == 1


def test_query_logs_denies_caller_without_can_observe_platform(monkeypatch) -> None:
    rebac = _FakeRebac(deny=True)
    store = _FakeLogStore()
    client = _build_app(monkeypatch, rebac, store)

    response = client.post("/logs/query", json=_query_body())

    assert response.status_code == 403
    assert store.queries == []
