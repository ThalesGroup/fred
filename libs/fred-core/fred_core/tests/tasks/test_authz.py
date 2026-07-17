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

"""Canonical task visibility/authz — the single owner both backend routers use.
'Listable ⇒ streamable' must hold, and the two must never drift (CTRLP-12)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.rebac_engine import TeamPermission
from fred_core.security.structure import KeycloakUser
from fred_core.tasks.authz import (
    authorize_task_access,
    authorize_task_mutation,
    authorize_task_stream,
    list_tasks_scoped,
)


def _user(uid: str = "u", roles: list[str] | None = None) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=None, roles=roles or [])


def _run(*, created_by: str | None, team_id: str | None) -> Any:
    return SimpleNamespace(created_by=created_by, team_id=team_id)


class _FakeRebac:
    def __init__(self, *, platform: bool = False, team_ok: bool = False) -> None:
        self._platform = platform
        self._team_ok = team_ok
        self.team_checks: list[tuple[str, TeamPermission, str]] = []

    async def has_user_permission(
        self, user: KeycloakUser, permission: Any, resource_id: str, **_: Any
    ) -> bool:
        return self._platform

    async def check_user_permission_or_raise(
        self, user: KeycloakUser, permission: Any, resource_id: str, **_: Any
    ) -> None:
        if not self._platform:
            raise AuthorizationError(
                user.uid, "manage", Resource.ORGANIZATION, "denied"
            )

    async def check_user_team_permission_or_raise(
        self, user: KeycloakUser, permission: TeamPermission, team_id: str
    ) -> str:
        self.team_checks.append((user.uid, permission, team_id))
        if not self._team_ok:
            raise AuthorizationError(user.uid, "read", Resource.TEAM, "denied")
        return "token"


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def list_tasks(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(tasks=[])


# ── authorize_task_stream ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_creator_allowed_without_rebac() -> None:
    rebac = _FakeRebac()
    await authorize_task_stream(
        _user("alice"), _run(created_by="alice", team_id="t1"), cast(Any, rebac)
    )
    assert rebac.team_checks == []


@pytest.mark.asyncio
async def test_stream_legacy_admin_role_does_not_bypass_rebac() -> None:
    # The Keycloak "admin" role alone no longer grants stream access: authz is
    # ReBAC-only now, so a real admin must hold can_manage_platform (granted via
    # the role→relation bridge). This keeps stream authz in lockstep with list
    # authz, which never had a role fast-path (CTRLP-12).
    rebac = _FakeRebac(platform=False, team_ok=False)
    with pytest.raises(AuthorizationError):
        await authorize_task_stream(
            _user("sys", roles=["admin"]),
            _run(created_by="a", team_id="t1"),
            cast(Any, rebac),
        )


@pytest.mark.asyncio
async def test_stream_is_alias_of_access() -> None:
    assert authorize_task_stream is authorize_task_access


@pytest.mark.asyncio
async def test_stream_platform_admin_allowed() -> None:
    rebac = _FakeRebac(platform=True)
    await authorize_task_stream(
        _user("admin"), _run(created_by="alice", team_id="t1"), cast(Any, rebac)
    )


@pytest.mark.asyncio
async def test_stream_team_reader_allowed() -> None:
    rebac = _FakeRebac(team_ok=True)
    await authorize_task_stream(
        _user("mgr"), _run(created_by="alice", team_id="nb"), cast(Any, rebac)
    )
    assert rebac.team_checks == [("mgr", TeamPermission.CAN_READ_MEMEBERS, "nb")]


@pytest.mark.asyncio
async def test_stream_team_non_reader_denied() -> None:
    rebac = _FakeRebac()
    with pytest.raises(AuthorizationError):
        await authorize_task_stream(
            _user("bob"), _run(created_by="alice", team_id="nb"), cast(Any, rebac)
        )


@pytest.mark.asyncio
async def test_stream_no_team_non_platform_denied() -> None:
    rebac = _FakeRebac()
    with pytest.raises(HTTPException) as exc:
        await authorize_task_stream(
            _user("bob"), _run(created_by="alice", team_id=None), cast(Any, rebac)
        )
    assert exc.value.status_code == 403


# ── list_tasks_scoped ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_user_scope_needs_no_role_and_hides_terminal() -> None:
    service, rebac = _FakeService(), _FakeRebac()
    await list_tasks_scoped(
        cast(Any, service),
        cast(Any, rebac),
        _user("alice"),
        scope="user",
        team_id=None,
        kind=None,
        state=None,
    )
    assert service.calls == [
        {"created_by": "alice", "kind": None, "state": None, "exclude_terminal": True}
    ]


@pytest.mark.asyncio
async def test_list_platform_scope_requires_platform_admin() -> None:
    service = _FakeService()
    with pytest.raises(AuthorizationError):
        await list_tasks_scoped(
            cast(Any, service),
            cast(Any, _FakeRebac(platform=False)),
            _user("bob"),
            scope="platform",
            team_id=None,
            kind=None,
            state=None,
        )
    # allowed for a platform admin
    await list_tasks_scoped(
        cast(Any, service),
        cast(Any, _FakeRebac(platform=True)),
        _user("admin"),
        scope="platform",
        team_id=None,
        kind="erasure",
        state=None,
    )
    assert service.calls == [{"kind": "erasure", "state": None}]


@pytest.mark.asyncio
async def test_list_team_scope_requires_team_id() -> None:
    with pytest.raises(HTTPException) as exc:
        await list_tasks_scoped(
            cast(Any, _FakeService()),
            cast(Any, _FakeRebac()),
            _user("u"),
            scope="team",
            team_id=None,
            kind=None,
            state=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_team_scope_allows_team_reader() -> None:
    service, rebac = _FakeService(), _FakeRebac(platform=False, team_ok=True)
    await list_tasks_scoped(
        cast(Any, service),
        cast(Any, rebac),
        _user("mgr"),
        scope="team",
        team_id="nb",
        kind=None,
        state=None,
    )
    assert rebac.team_checks == [("mgr", TeamPermission.CAN_READ_MEMEBERS, "nb")]
    assert service.calls == [{"team_id": "nb", "kind": None, "state": None}]


@pytest.mark.asyncio
async def test_list_team_scope_denies_non_reader() -> None:
    with pytest.raises(AuthorizationError):
        await list_tasks_scoped(
            cast(Any, _FakeService()),
            cast(Any, _FakeRebac(platform=False, team_ok=False)),
            _user("bob"),
            scope="team",
            team_id="nb",
            kind=None,
            state=None,
        )


# ── authorize_task_mutation (cancel) — stricter subset of view ────────────────


@pytest.mark.asyncio
async def test_mutation_creator_allowed() -> None:
    rebac = _FakeRebac()
    await authorize_task_mutation(
        _user("alice"), _run(created_by="alice", team_id="t1"), cast(Any, rebac)
    )


@pytest.mark.asyncio
async def test_mutation_platform_admin_allowed() -> None:
    rebac = _FakeRebac(platform=True)
    await authorize_task_mutation(
        _user("admin"), _run(created_by="alice", team_id="t1"), cast(Any, rebac)
    )


@pytest.mark.asyncio
async def test_mutation_team_reader_denied() -> None:
    # A team reader can *view* (stream) a team task but must NOT cancel it: cancel
    # is a mutation, and read-level team access does not grant mutations.
    rebac = _FakeRebac(platform=False, team_ok=True)
    with pytest.raises(HTTPException) as exc:
        await authorize_task_mutation(
            _user("mgr"), _run(created_by="alice", team_id="nb"), cast(Any, rebac)
        )
    assert exc.value.status_code == 403
    assert rebac.team_checks == []  # never consulted team read for a mutation


@pytest.mark.asyncio
async def test_mutation_non_privileged_denied() -> None:
    rebac = _FakeRebac()
    with pytest.raises(HTTPException) as exc:
        await authorize_task_mutation(
            _user("bob"), _run(created_by="alice", team_id="t1"), cast(Any, rebac)
        )
    assert exc.value.status_code == 403


# ── view ⇄ mutation relationship (the invariant these predicates must hold) ───


@pytest.mark.asyncio
async def test_team_reader_can_view_but_not_mutate() -> None:
    """The one asymmetry we deliberately keep: a team reader streams but can't cancel."""
    run = _run(created_by="alice", team_id="nb")
    # view: allowed
    await authorize_task_access(_user("mgr"), run, cast(Any, _FakeRebac(team_ok=True)))
    # mutate: denied
    with pytest.raises(HTTPException):
        await authorize_task_mutation(
            _user("mgr"), run, cast(Any, _FakeRebac(team_ok=True))
        )


@pytest.mark.asyncio
async def test_platform_admin_can_both_view_and_mutate() -> None:
    """A ReBAC platform admin (no Keycloak 'admin' role) can stream AND cancel — the
    bug this convergence fixes: previously cancel required the legacy role."""
    run = _run(created_by="alice", team_id="t1")
    await authorize_task_access(_user("ops"), run, cast(Any, _FakeRebac(platform=True)))
    await authorize_task_mutation(
        _user("ops"), run, cast(Any, _FakeRebac(platform=True))
    )
