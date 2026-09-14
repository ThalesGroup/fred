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

"""Team administrator charter: admin-only team permissions apply only once the
team admin accepted the configured charter version."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fred_core
import pytest
from control_plane_backend.models.base import Base
from control_plane_backend.models.team_admin_charter_models import (
    TeamAdminCharterAcceptanceRow,
)
from control_plane_backend.teams import service as team_service
from control_plane_backend.teams.admin_charter_store import TeamAdminCharterStore
from control_plane_backend.teams.api import register_exception_handlers
from control_plane_backend.teams.schemas import (
    TeamAdminCharterDisabledError,
    TeamAdminCharterNotAcceptedError,
)
from control_plane_backend.teams.service import (
    ADMIN_ONLY_TEAM_PERMISSIONS,
    SHARED_WITH_ANALYST_TEAM_PERMISSIONS,
    _get_team_permissions_for_user,
    _validate_team_and_check_permission,
    accept_team_admin_charter,
    get_team_admin_charter_status,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core import (
    KeycloakUser,
    RebacDisabledResult,
    RebacReference,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import create_async_engine

_TEAM = TeamId("team-a")
_VERSION = "2026-09"


class _Denied(PermissionError):
    pass


class _FakeRebac:
    """Grants a fixed set of team permissions per user on every team."""

    def __init__(
        self,
        granted: dict[str, set[TeamPermission]],
        *,
        administered: dict[str, list[str]] | None = None,
        disabled: bool = False,
    ) -> None:
        self._granted = granted
        self._administered = administered or {}
        self._disabled = disabled
        self.lookups = 0

    async def check_user_team_permissions_or_raise(
        self, user: KeycloakUser, team_id: TeamId, permissions: list[TeamPermission]
    ) -> str:
        if not set(permissions) <= self._granted.get(user.uid, set()):
            raise _Denied("rebac denied")
        return "token"

    async def has_permissions(
        self, subject: RebacReference, permissions, resource, consistency_token=None
    ) -> list[bool]:
        held = self._granted.get(subject.id, set())
        return [permission in held for permission in permissions]

    async def lookup_user_resources(self, user: KeycloakUser, permission):
        self.lookups += 1
        assert permission == TeamPermission.CAN_ADMINISTER_ADMINS
        if self._disabled:
            return RebacDisabledResult()
        return [
            RebacReference(Resource.TEAM, team_id)
            for team_id in self._administered.get(user.uid, [])
        ]


class _FakeCharterStore:
    def __init__(self, accepted: dict[tuple[str, str], datetime] | None = None):
        self.accepted = dict(accepted or {})
        self.reads = 0

    async def get_accepted_at(self, user_id: str, version: str) -> datetime | None:
        self.reads += 1
        return self.accepted.get((user_id, version))

    async def accept(self, user_id: str, version: str) -> tuple[datetime, bool]:
        existing = self.accepted.get((user_id, version))
        if existing is not None:
            return existing, False
        now = datetime.now(timezone.utc)
        self.accepted[(user_id, version)] = now
        return now, True


_ADMIN = {
    TeamPermission.CAN_READ,
    TeamPermission.CAN_READ_MEMEBERS,
    TeamPermission.CAN_RUN_EVALUATIONS,
    TeamPermission.CAN_MANAGE_EVALUATION_CORPUS,
    *ADMIN_ONLY_TEAM_PERMISSIONS,
}
_EDITOR = {
    TeamPermission.CAN_READ,
    TeamPermission.CAN_READ_MEMEBERS,
    TeamPermission.CAN_UPDATE_RESOURCES,
}


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


def _deps(
    rebac: _FakeRebac, store: _FakeCharterStore, version: str | None = _VERSION
) -> Any:
    metadata_store = SimpleNamespace(
        get_by_team_id=lambda team_id: _async(SimpleNamespace(id=team_id))
    )
    return cast(
        Any,
        SimpleNamespace(
            configuration=SimpleNamespace(
                app=SimpleNamespace(team_admin_charter_version=version)
            ),
            rebac=rebac,
            get_team_metadata_store=lambda: metadata_store,
            get_team_admin_charter_store=lambda: store,
        ),
    )


async def _async(value: object) -> object:
    return value


async def _check(deps: Any, uid: str, permission: TeamPermission) -> None:
    await _validate_team_and_check_permission(
        _user(uid), _TEAM, deps.rebac, [permission], deps
    )


# --------------------------- permission gate ---------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permission",
    [TeamPermission.CAN_UPDATE_INFO, TeamPermission.CAN_ADMINISTER_MEMBERS],
)
async def test_admin_who_has_not_accepted_is_denied(
    permission: TeamPermission,
) -> None:
    deps = _deps(_FakeRebac({"admin": _ADMIN}), _FakeCharterStore())

    with pytest.raises(TeamAdminCharterNotAcceptedError):
        await _check(deps, "admin", permission)


@pytest.mark.asyncio
async def test_admin_who_accepted_is_allowed() -> None:
    store = _FakeCharterStore({("admin", _VERSION): datetime.now(timezone.utc)})
    deps = _deps(_FakeRebac({"admin": _ADMIN}), store)

    await _check(deps, "admin", TeamPermission.CAN_UPDATE_INFO)


@pytest.mark.asyncio
async def test_new_version_denies_an_admin_who_accepted_an_older_one() -> None:
    store = _FakeCharterStore({("admin", "2026-01"): datetime.now(timezone.utc)})
    deps = _deps(_FakeRebac({"admin": _ADMIN}), store)

    with pytest.raises(TeamAdminCharterNotAcceptedError):
        await _check(deps, "admin", TeamPermission.CAN_ADMINISTER_ADMINS)


@pytest.mark.asyncio
async def test_no_configured_version_never_reads_acceptances() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({"admin": _ADMIN}), store, version=None)

    await _check(deps, "admin", TeamPermission.CAN_UPDATE_INFO)
    assert store.reads == 0


@pytest.mark.asyncio
async def test_non_admin_gets_the_rebac_denial_without_reading_acceptances() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({"editor": _EDITOR}), store)

    with pytest.raises(_Denied):
        await _check(deps, "editor", TeamPermission.CAN_UPDATE_INFO)
    await _check(deps, "editor", TeamPermission.CAN_UPDATE_RESOURCES)
    assert store.reads == 0


# --------------------------- permission projection ---------------------------


@pytest.mark.asyncio
async def test_projection_drops_admin_only_permissions_until_accepted() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({"admin": _ADMIN}), store)

    before = set(await _get_team_permissions_for_user(_user("admin"), _TEAM, deps))
    assert before.isdisjoint(ADMIN_ONLY_TEAM_PERMISSIONS)
    assert before.isdisjoint(SHARED_WITH_ANALYST_TEAM_PERMISSIONS)
    assert TeamPermission.CAN_READ_MEMEBERS in before

    await accept_team_admin_charter(_user("admin"), deps)
    after = set(await _get_team_permissions_for_user(_user("admin"), _TEAM, deps))
    assert ADMIN_ONLY_TEAM_PERMISSIONS | SHARED_WITH_ANALYST_TEAM_PERMISSIONS <= after


@pytest.mark.asyncio
async def test_an_unaccepted_admin_who_is_also_analyst_keeps_evaluations() -> None:
    analyst_admin = _ADMIN | {TeamPermission.CAN_READ_CONVERSATIONS_FOR_EVALUATION}
    deps = _deps(_FakeRebac({"admin": analyst_admin}), _FakeCharterStore())

    permissions = set(await _get_team_permissions_for_user(_user("admin"), _TEAM, deps))

    assert permissions.isdisjoint(ADMIN_ONLY_TEAM_PERMISSIONS)
    assert SHARED_WITH_ANALYST_TEAM_PERMISSIONS <= permissions


@pytest.mark.asyncio
async def test_projection_for_a_non_admin_reads_no_acceptance() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({"editor": _EDITOR}), store)

    permissions = await _get_team_permissions_for_user(_user("editor"), _TEAM, deps)

    assert set(permissions) == _EDITOR
    assert store.reads == 0


def test_admin_only_permissions_match_the_schema() -> None:
    schema = (
        Path(fred_core.__file__).parent / "security" / "rebac" / "schema.fga"
    ).read_text()
    team_block = schema.split("type team", 1)[1].split("\ntype ", 1)[0]
    team_admin_only = {
        TeamPermission(name)
        for name in re.findall(
            r"^\s*define (can_\w+): team_admin\s*$", team_block, re.M
        )
    }

    assert team_admin_only == ADMIN_ONLY_TEAM_PERMISSIONS


# --------------------------- status and acceptance ---------------------------


@pytest.mark.asyncio
async def test_status_requires_acceptance_from_an_admin_who_has_not_accepted() -> None:
    rebac = _FakeRebac({}, administered={"admin": [_TEAM]})
    deps = _deps(rebac, _FakeCharterStore())

    status = await get_team_admin_charter_status(_user("admin"), deps)

    assert status.required is True
    assert status.accepted_at is None


@pytest.mark.asyncio
async def test_status_does_not_require_acceptance_from_a_user_without_teams() -> None:
    deps = _deps(_FakeRebac({}), _FakeCharterStore())

    status = await get_team_admin_charter_status(_user("member"), deps)

    assert status.required is False


@pytest.mark.asyncio
async def test_status_after_acceptance_skips_the_team_lookup() -> None:
    accepted_at = datetime(2026, 9, 14, tzinfo=timezone.utc)
    rebac = _FakeRebac({}, administered={"admin": [_TEAM]})
    deps = _deps(rebac, _FakeCharterStore({("admin", _VERSION): accepted_at}))

    status = await get_team_admin_charter_status(_user("admin"), deps)

    assert status.required is False
    assert status.accepted_at == accepted_at
    assert rebac.lookups == 0


@pytest.mark.asyncio
async def test_status_without_version_or_rebac_requires_nothing() -> None:
    rebac = _FakeRebac({}, administered={"admin": [_TEAM]})
    no_version = _deps(rebac, _FakeCharterStore(), version=None)
    assert (
        await get_team_admin_charter_status(_user("admin"), no_version)
    ).required is False

    disabled = _deps(_FakeRebac({}, disabled=True), _FakeCharterStore())
    assert (
        await get_team_admin_charter_status(_user("admin"), disabled)
    ).required is False


@pytest.mark.asyncio
async def test_acceptance_is_recorded_once_and_audited_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audited: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        team_service,
        "emit_audit_log",
        lambda event, **fields: audited.append((event, fields)),
    )
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({}), store)

    first = await accept_team_admin_charter(_user("admin"), deps)
    second = await accept_team_admin_charter(_user("admin"), deps)

    assert first.required is False and first.accepted_at is not None
    assert second.accepted_at == first.accepted_at
    assert audited == [
        (
            "team_admin.charter.accepted",
            {"actor_uid": "admin", "charter_version": _VERSION},
        )
    ]


@pytest.mark.asyncio
async def test_acceptance_without_version_is_refused() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac({}), store, version=None)

    with pytest.raises(TeamAdminCharterDisabledError):
        await accept_team_admin_charter(_user("admin"), deps)
    assert store.accepted == {}


def test_charter_errors_map_to_their_http_status() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-accepted")
    async def _not_accepted() -> None:
        raise TeamAdminCharterNotAcceptedError()

    @app.get("/disabled")
    async def _disabled() -> None:
        raise TeamAdminCharterDisabledError()

    client = TestClient(app)
    not_accepted = client.get("/not-accepted")
    disabled = client.get("/disabled")

    assert (not_accepted.status_code, not_accepted.json()) == (
        403,
        {"detail": "team_admin_charter_not_accepted"},
    )
    assert (disabled.status_code, disabled.json()) == (
        409,
        {"detail": "team_admin_charter_disabled"},
    )


# --------------------------- store ---------------------------


@pytest.mark.asyncio
async def test_store_keeps_the_first_acceptance_and_every_version(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'charter.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.tables[TeamAdminCharterAcceptanceRow.__tablename__].create
            )
        store = TeamAdminCharterStore(engine)

        assert await store.get_accepted_at("admin", _VERSION) is None

        first_at, first_inserted = await store.accept("admin", _VERSION)
        again_at, again_inserted = await store.accept("admin", _VERSION)
        _, other_inserted = await store.accept("admin", "2027-01")

        assert (first_inserted, again_inserted, other_inserted) == (True, False, True)
        assert again_at == await store.get_accepted_at("admin", _VERSION)
        assert await store.get_accepted_at("admin", "2027-01") is not None
        assert first_at is not None
    finally:
        await engine.dispose()
