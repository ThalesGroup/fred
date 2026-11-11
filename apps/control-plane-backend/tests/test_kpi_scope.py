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
`resolve_kpi_scope`: the single authorization chokepoint every KPI preset shares.

Covers platform scope (can_observe_platform), multi-team scope (observers may
read any set of real teams, others need can_read_analytics - team admin - on
every team), personal spaces always taking the team check, the team cap, and
`self_scoped` presets bypassing OpenFGA.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from control_plane_backend.kpi import scope as kpi_scope
from control_plane_backend.kpi.scope import (
    MAX_SCOPE_TEAMS,
    KpiScope,
    resolve_kpi_scope,
)
from fastapi import HTTPException
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA

_OBSERVE = (OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID)


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


def _admins(*team_ids: str) -> set[tuple[Any, str]]:
    return {(TeamPermission.CAN_READ_ANALYTICS, t) for t in team_ids}


def _role_grants(role: str, relation: str) -> bool:
    """Whether `role` held directly on a team yields `relation`, per the compiled model."""
    model = json.loads(DEFAULT_SCHEMA)
    team = next(t for t in model["type_definitions"] if t["type"] == "team")

    def holds(definition: dict[str, Any], name: str) -> bool:
        if "this" in definition:
            return name == role
        if "computedUserset" in definition:
            target = definition["computedUserset"]["relation"]
            return holds(team["relations"][target], target)
        return any(holds(child, name) for child in definition["union"]["child"])

    return holds(team["relations"][relation], relation)


class _FakeRebac:
    """Denies everything by default; allow-list specific (permission, resource_id) pairs."""

    def __init__(self, *, allow: set[tuple[Any, str]] | None = None) -> None:
        self.allow = allow or set()
        self.calls: list[tuple[Any, str]] = []

    async def has_user_permission(
        self, user: KeycloakUser, permission: Any, resource_id: str, **kwargs: Any
    ) -> bool:
        del user, kwargs
        self.calls.append((permission, resource_id))
        return (permission, resource_id) in self.allow

    async def check_user_permission_or_raise(
        self, user: KeycloakUser, permission: Any, resource_id: str, **kwargs: Any
    ) -> None:
        if not await self.has_user_permission(user, permission, resource_id):
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
    rebac = _FakeRebac(allow={_OBSERVE})
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(request, _user(), [])

    assert result == KpiScope()
    assert rebac.calls == [_OBSERVE]


@pytest.mark.asyncio
async def test_platform_scope_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request_with(monkeypatch, _FakeRebac())

    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, _user(), [])


@pytest.mark.asyncio
async def test_observer_reads_any_team_set_without_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _FakeRebac(allow={_OBSERVE})
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(
        request, _user(), [TeamId("a"), TeamId("b"), TeamId("a")]
    )

    assert result == KpiScope(team_ids=(TeamId("a"), TeamId("b")))
    assert rebac.calls == [_OBSERVE]


@pytest.mark.asyncio
async def test_team_admin_of_every_team_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _FakeRebac(allow=_admins("a", "b"))
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(request, _user(), [TeamId("a"), TeamId("b")])

    assert result == KpiScope(team_ids=(TeamId("a"), TeamId("b")))
    assert set(rebac.calls[1:]) == _admins("a", "b")


@pytest.mark.asyncio
async def test_team_admin_missing_one_team_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request_with(monkeypatch, _FakeRebac(allow=_admins("a")))

    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, _user(), [TeamId("a"), TeamId("b")])


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("team_member", False),
        ("team_editor", False),
        ("team_analyst", False),
        ("pending_team_admin", False),
        ("team_admin", True),
    ],
)
@pytest.mark.asyncio
async def test_only_team_admins_read_team_analytics(
    monkeypatch: pytest.MonkeyPatch, role: str, allowed: bool
) -> None:
    permission = TeamPermission.CAN_READ_ANALYTICS
    grants = {(permission, "a")} if _role_grants(role, permission.value) else set()
    request = _request_with(monkeypatch, _FakeRebac(allow=grants))

    if allowed:
        result = await resolve_kpi_scope(request, _user(), [TeamId("a")])
        assert result == KpiScope(team_ids=(TeamId("a"),))
    else:
        with pytest.raises(AuthorizationError):
            await resolve_kpi_scope(request, _user(), [TeamId("a")])


def test_every_member_role_still_reads_members() -> None:
    """The narrower analytics check must not be an alias of membership."""
    assert _role_grants("team_editor", TeamPermission.CAN_READ_MEMEBERS.value)
    assert not _role_grants("team_editor", TeamPermission.CAN_READ_ANALYTICS.value)


@pytest.mark.asyncio
async def test_personal_space_needs_membership_even_for_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    personal = TeamId("personal-someone-else")
    request = _request_with(monkeypatch, _FakeRebac(allow={_OBSERVE}))

    with pytest.raises(AuthorizationError):
        await resolve_kpi_scope(request, _user(), [TeamId("a"), personal])


@pytest.mark.asyncio
async def test_too_many_teams_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    rebac = _FakeRebac(allow={_OBSERVE})
    request = _request_with(monkeypatch, rebac)
    team_ids = [TeamId(f"t{i}") for i in range(MAX_SCOPE_TEAMS + 1)]

    with pytest.raises(HTTPException) as exc:
        await resolve_kpi_scope(request, _user(), team_ids)

    assert exc.value.status_code == 400
    assert rebac.calls == []


def test_admin_only_flag_is_gone() -> None:
    """Observers see every analytics tab, so no preset needs can_manage_platform."""
    from control_plane_backend.kpi.presets import PRESETS

    assert all(not hasattr(p, "platform_admin_only") for p in PRESETS)


@pytest.mark.asyncio
async def test_self_scoped_allowed_with_no_permissions_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain user must still read their own data through a self_scoped preset."""
    rebac = _FakeRebac()
    request = _request_with(monkeypatch, rebac)

    result = await resolve_kpi_scope(request, _user(), [], self_scoped=True)

    assert result == KpiScope()
    assert rebac.calls == []
