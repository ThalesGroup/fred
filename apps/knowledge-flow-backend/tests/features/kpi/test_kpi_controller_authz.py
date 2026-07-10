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

"""KPI dashboard authz wiring.

`POST /kpi/query`'s `view_global=true` branch (the standalone KPI dashboard,
`/monitoring/kpis`) must require `CAN_OBSERVE_PLATFORM` — platform_observer's
own capability — not `CAN_READ_KPI_GLOBAL`, which also gates the separate
control-plane Analytics presets (`/admin/analytics`) and must stay
platform_admin-only so granting `platform_observer` never implicitly widens
into that admin-only surface. The non-global branch requires authentication
only (AUTHZ-05 review item 8a).
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission, Resource, get_current_user
from fred_core.common import register_exception_handlers

from knowledge_flow_backend.features.kpi import kpi_controller as kpi_controller_module
from knowledge_flow_backend.features.kpi.kpi_controller import KPIController


class _FakeKpiStore:
    def __init__(self) -> None:
        self.queries: list[object] = []

    def query(self, body):
        self.queries.append(body)
        return {"rows": []}


class _FakeRebac:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if self.deny:
            raise AuthorizationError(user.uid, str(permission), Resource.ORGANIZATION)


def _build_app(monkeypatch, rebac: _FakeRebac, store: _FakeKpiStore) -> TestClient:
    monkeypatch.setattr(
        kpi_controller_module,
        "get_app_context",
        lambda: type("FakeAppContext", (), {"get_kpi_store": staticmethod(lambda: store)})(),
    )
    monkeypatch.setattr(kpi_controller_module, "get_rebac_engine", lambda: rebac)

    router = APIRouter()
    KPIController(router)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", roles=[], email=None, groups=[])
    return TestClient(app)


def _query_body(*, view_global: bool) -> dict:
    return {
        "since": "now-24h",
        "view_global": view_global,
        "select": [{"alias": "n", "op": "count"}],
    }


def test_global_view_requires_can_observe_platform(monkeypatch) -> None:
    rebac = _FakeRebac(deny=False)
    store = _FakeKpiStore()
    client = _build_app(monkeypatch, rebac, store)

    response = client.post("/kpi/query", json=_query_body(view_global=True))

    assert response.status_code == 200
    assert rebac.calls == [(OrganizationPermission.CAN_OBSERVE_PLATFORM, "fred")]


def test_global_view_denies_caller_without_can_observe_platform(monkeypatch) -> None:
    rebac = _FakeRebac(deny=True)
    store = _FakeKpiStore()
    client = _build_app(monkeypatch, rebac, store)

    response = client.post("/kpi/query", json=_query_body(view_global=True))

    assert response.status_code == 403
    assert store.queries == []


def test_non_global_view_requires_authentication_only(monkeypatch) -> None:
    """AUTHZ-05 review item 8a: no ReBAC check on the personal-scope branch."""
    rebac = _FakeRebac(deny=True)  # would 403 if (incorrectly) consulted
    store = _FakeKpiStore()
    client = _build_app(monkeypatch, rebac, store)

    response = client.post("/kpi/query", json=_query_body(view_global=False))

    assert response.status_code == 200
    assert rebac.calls == []
