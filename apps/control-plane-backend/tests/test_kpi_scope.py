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
`resolve_kpi_scope` — the single authorization chokepoint every KPI preset
now shares (OBSERV-02 v3, `KPI-ANALYTICS-RFC.md` §2.3/§2.4).

Covers: platform-wide requires can_observe_platform (allow/deny), team-scoped
requires can_read_members on that team (allow/deny), and that the two checks
are never conflated (a team-scoped request never checks the org permission
and vice versa).
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.kpi import scope as kpi_scope
from control_plane_backend.kpi.scope import KpiScope, resolve_kpi_scope
from fred_core import KeycloakUser, OrganizationPermission, TeamPermission
from fred_core.common import TeamId
from fred_core.security.models import AuthorizationError, Resource


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


class _FakeRebac:
    """Denies everything by default; allow-list specific (permission, resource_id) pairs."""

    def __init__(self, *, allow: set[tuple[Any, str]] | None = None) -> None:
        self.allow = allow or set()
        self.calls: list[tuple[Any, str]] = []

    async def check_user_permission_or_raise(
        self, user: KeycloakUser, permission: Any, resource_id: str, **kwargs: Any
    ) -> None:
        del user, kwargs
        self.calls.append((permission, resource_id))
        if (permission, resource_id) not in self.allow:
            raise AuthorizationError("u1", str(permission), Resource.ORGANIZATION)


class _FakeContainer:
    def __init__(self, rebac: _FakeRebac) -> None:
        self._rebac = rebac

    def get_rebac_engine(self) -> _FakeRebac:
        return self._rebac


def _request_with(monkeypatch: pytest.MonkeyPatch, rebac: _FakeRebac) -> Any:
    container = _FakeContainer(rebac)
    monkeypatch.setattr(
        kpi_scope, "get_application_container", lambda request: container
    )
    return object()  # resolve_kpi_scope never touches `request` beyond this call


@pytest.mark.asyncio
async def test_platform_scope_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    from fred_core import ORGANIZATION_ID

    rebac = _FakeRebac(
        allow={(OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID)}
    )
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(request, _user(), None)

    assert result == KpiScope(team_id=None)
    assert rebac.calls == [
        (OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID)
    ]


@pytest.mark.asyncio
async def test_platform_scope_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    rebac = _FakeRebac(allow=set())
    request = _request_with(monkeypatch, rebac)

    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, _user(), None)


@pytest.mark.asyncio
async def test_team_scope_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    team_id = TeamId("team-1")
    rebac = _FakeRebac(allow={(TeamPermission.CAN_READ_MEMEBERS, str(team_id))})
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(request, _user(), team_id)

    assert result == KpiScope(team_id=team_id)
    assert rebac.calls == [(TeamPermission.CAN_READ_MEMEBERS, str(team_id))]


@pytest.mark.asyncio
async def test_team_scope_denied_for_non_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _FakeRebac(allow=set())
    request = _request_with(monkeypatch, rebac)

    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, _user(), TeamId("team-1"))


@pytest.mark.asyncio
async def test_team_scope_never_checks_org_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A team-scoped request must not fall back to (or also require) the
    platform-wide can_observe_platform check — the two scopes are disjoint."""
    team_id = TeamId("team-1")
    rebac = _FakeRebac(allow={(TeamPermission.CAN_READ_MEMEBERS, str(team_id))})
    request = _request_with(monkeypatch, rebac)

    await resolve_kpi_scope(request, _user(), team_id)

    assert all(perm == TeamPermission.CAN_READ_MEMEBERS for perm, _ in rebac.calls)
