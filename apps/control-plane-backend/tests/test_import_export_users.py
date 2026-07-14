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

"""AUTHZ-07 Part 8 §40.2: declarative platform provisioning for identities/teams/roles/users.

The `users.json` bundle entry names a Keycloak identity by username and
describes the Fred-side authorization state it should end up with (team
membership, team roles, platform roles). This importer
(`import_export/importer.py::_run_users_phase`) is two-phase: phase 1
(`_provision_bundle_identities`) creates a Keycloak identity for any entry
that has no existing match AND carries a `password`; phase 2 (unchanged from
this session's earlier work) resolves username → sub and grants roles. An
entry with no `password` is assumed to already exist — it is never
force-created, only skipped and reported if it still doesn't resolve.

It also never bypasses the team permission model: `schema.fga`'s `type team`
comment is explicit that team-scoped roles (`team_admin`/`team_editor`/
`team_analyst`/`team_member`) are never derived from a platform role. A
brand-new team's *initial* `team_admin`(s) can be seeded at creation
(`teams.service.create_team`'s own one-shot bootstrap capability), but any
other team-scoped grant requires the importing `platform_admin` to already
hold `team_admin` on that team — otherwise it is skipped and reported, never
forced through.

Real SQLite-backed `TeamMetadataStore` + a hand-rolled ReBAC fake that
actually enforces the `team_admin`-only permission model (unlike a fake that
merely records calls), matching this branch's established test pattern
(`test_metadata_stores.py`'s `_make_sqlite_engine`,
`test_bootstrap_platform_admin.py`'s `_FakeRebac`).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export.bundle import open_bundle
from control_plane_backend.import_export.importer import (
    MigrationReport,
    _provision_bundle_identities,
    run_import,
)
from control_plane_backend.import_export.schemas import BundleUserEntry
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.users.dependencies import (
    KeycloakAdminFactory,
    UserServiceDependencies,
)
from control_plane_backend.users.service import find_user_sub_by_username
from fred_core import (
    ORGANIZATION_ID,
    KeycloackDisabled,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.tasks.models import StartMigrationRequest
from fred_core.tasks.service import TaskService
from fred_core.teams.metadata_store import TeamMetadataStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# ── fixtures / fakes ───────────────────────────────────────────────────────


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    """One file-backed SQLite async engine carrying the full control-plane schema."""
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import fred_core.tasks.orm_models  # noqa: F401

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


class _FakeTeamRebac:
    """ReBAC fake that actually enforces the `team_admin`-only permission
    model (schema.fga's `type team`: `can_administer_*` is `team_admin`-only,
    never derived from a platform role) — a fake that merely records calls
    would not catch a bypass regression.

    Org-scoped checks (`CAN_CREATE_TEAM`) always pass, mirroring
    `can_create_team: platform_admin` in schema.fga — these tests' caller is
    always a platform_admin.
    """

    def __init__(self) -> None:
        self.team_admins: dict[str, set[str]] = {}
        self.org_relations: list[Relation] = []
        self.team_relations: list[Relation] = []

    async def ensure_team_organization_relations(self, team_ids: list[Any]) -> None:
        return None

    async def add_relations(self, relations: list[Relation]) -> None:
        for relation in relations:
            await self.add_relation(relation)

    async def add_relation(self, relation: Relation) -> None:
        if relation.resource.type == Resource.TEAM:
            self.team_relations.append(relation)
            if relation.relation == RelationType.TEAM_ADMIN:
                self.team_admins.setdefault(str(relation.resource.id), set()).add(
                    relation.subject.id
                )
        else:
            self.org_relations.append(relation)

    async def check_user_permission_or_raise(
        self, user: KeycloakUser, permission: Any, resource_id: Any, **_kwargs: Any
    ) -> None:
        if str(resource_id) == ORGANIZATION_ID:
            return
        from fred_core import AuthorizationError

        raise AuthorizationError(
            user.uid, getattr(permission, "value", str(permission)), Resource.TEAM
        )

    async def check_user_team_permissions_or_raise(
        self, *, user: KeycloakUser, team_id: Any, permissions: Any
    ) -> str | None:
        admins = self.team_admins.get(str(team_id), set())
        if user.uid not in admins:
            from fred_core import AuthorizationError

            permissions = list(permissions)
            perm = permissions[0].value if permissions else "?"
            raise AuthorizationError(user.uid, perm, Resource.TEAM)
        return "consistency-token"

    async def has_permission(
        self,
        subject: RebacReference,
        permission: Any,
        resource: RebacReference,
        **_kw: Any,
    ) -> bool:
        return subject.id in self.team_admins.get(str(resource.id), set())

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Any,
        **_kw: Any,
    ) -> set[RebacReference]:
        if relation == RelationType.TEAM_ADMIN:
            return {
                RebacReference(Resource.USER, uid)
                for uid in self.team_admins.get(str(resource.id), set())
            }
        return set()


class _FakeKeycloakAdmin:
    """Read-only `username -> sub` directory. Only `a_get_users` is
    implemented; any write call (`a_create_user`, `a_update_user`,
    `a_delete_user`, ...) raises via `__getattr__` instead of silently
    succeeding — the load-bearing guarantee that username resolution never
    creates or mutates a Keycloak identity.
    """

    def __init__(self, directory: dict[str, str]) -> None:
        self._directory = directory
        self.calls: list[dict[str, Any]] = []

    async def a_get_users(
        self, query: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(query or {})
        username = (query or {}).get("username")
        sub = self._directory.get(cast(str, username))
        return [{"id": sub, "username": username}] if sub else []

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"find_user_sub_by_username must never call Keycloak admin "
            f"method {name!r} — read-only by design"
        )


class _FakeWritableKeycloakAdmin:
    """`username -> sub` directory that also allows the identity phase's
    write call. Unlike `_FakeKeycloakAdmin` above (deliberately read-only, to
    prove the role phase never creates identities), this fake implements
    `a_create_user`/`a_get_user` — `create_user`'s (`users/service.py`) two
    underlying `python-keycloak` `KeycloakAdmin` calls — and records every
    `a_create_user` payload so a test can assert the identity phase called it
    with the right data. A successful create is reflected back into the
    directory, mirroring real Keycloak: the next `a_get_users` lookup for
    that username resolves, exactly as `_provision_bundle_identities`
    followed by `_resolve_bundle_usernames` expects.
    """

    def __init__(self, directory: dict[str, str] | None = None) -> None:
        self._directory: dict[str, str] = dict(directory or {})
        self.create_calls: list[dict[str, Any]] = []

    async def a_get_users(
        self, query: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        username = (query or {}).get("username")
        sub = self._directory.get(cast(str, username))
        return [{"id": sub, "username": username}] if sub else []

    async def a_create_user(
        self, payload: dict[str, Any], exist_ok: bool = False
    ) -> str:
        self.create_calls.append(payload)
        username = cast(str, payload["username"])
        user_id = f"created-{username}-sub"
        self._directory[username] = user_id
        return user_id

    async def a_get_user(self, user_id: str) -> dict[str, Any]:
        username = next(
            (u for u, sub in self._directory.items() if sub == user_id), None
        )
        return {"id": user_id, "username": username}


def _admin_user(uid: str = "platform-admin-sub") -> KeycloakUser:
    return KeycloakUser(uid=uid, username="platform-admin", roles=[], email=None)


async def _no_users_by_ids(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {}


def _team_deps(engine: AsyncEngine, rebac: _FakeTeamRebac) -> TeamServiceDependencies:
    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    config.app.default_team_max_resources_storage_size = 5368709120
    store = TeamMetadataStore(engine)
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, SchedulerBackend.MEMORY),
        get_team_metadata_store=lambda: store,
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=lambda: ConversationPolicyCatalog(),
        get_users_by_ids=cast(Any, _no_users_by_ids),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


def _user_deps(
    directory: dict[str, str],
) -> tuple[UserServiceDependencies, _FakeKeycloakAdmin]:
    admin = _FakeKeycloakAdmin(directory)
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=cast(KeycloakAdminFactory, lambda: admin),
    )
    return deps, admin


def _writable_user_deps(
    directory: dict[str, str],
) -> tuple[UserServiceDependencies, _FakeWritableKeycloakAdmin]:
    admin = _FakeWritableKeycloakAdmin(directory)
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=cast(KeycloakAdminFactory, lambda: admin),
    )
    return deps, admin


_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "import_export" / "demo_provisioning"
)


def _build_bundle_bytes_from_fixture() -> bytes:
    """Zip the checked-in demo provisioning fixture — same fixture
    `make build-demo-bundle` packages — instead of hand-rolling a dict, so the
    success-path test exercises the real, git-committed bundle content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(_FIXTURE_DIR / "manifest.json", "manifest.json")
        zf.write(_FIXTURE_DIR / "users.json", "users.json")
    return buf.getvalue()


def _build_bundle_bytes(users: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format_version": 1,
                    "source_platform": "swift",
                    "created_at": "2026-07-14T00:00:00Z",
                    "tables": {},
                    "tuple_count": 0,
                    "realm_exported": False,
                    "content_keys": [],
                }
            ),
        )
        zf.writestr("users.json", json.dumps(users))
    return buf.getvalue()


async def _run(
    bundle_bytes: bytes,
    engine: AsyncEngine,
    *,
    platform_admin: KeycloakUser,
    user_deps: UserServiceDependencies,
    team_deps: TeamServiceDependencies,
) -> MigrationReport:
    task_service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
    start = await task_service.start(
        StartMigrationRequest(), created_by=platform_admin.uid
    )
    bundle = open_bundle(bundle_bytes)
    return await run_import(
        bundle=bundle,
        import_id="imp-users-1",
        task_id=start.task_id,
        task_service=task_service,
        engine=engine,
        agent_instance_store=AgentInstanceStore(engine),
        platform_admin=platform_admin,
        user_deps=user_deps,
        team_deps=team_deps,
    )


# ── users phase: end-to-end through run_import ─────────────────────────────


@pytest.mark.asyncio
async def test_users_phase_full_fixture_creates_identities_teams_and_roles(
    tmp_path: Path,
) -> None:
    """The success path, now end-to-end through the checked-in demo fixture
    (`tests/fixtures/import_export/demo_provisioning/` — the same fixture
    `make build-demo-bundle` packages). None of its 15 entries has an existing
    Keycloak identity, and every entry carries a password, so the identity
    phase (phase 1) creates all 15 first; the role phase (phase 2, unchanged)
    then resolves every one of them and provisions teams/roles exactly as
    before. `northbridge`/`fredlab`/`swiftpost` each get created because the
    fixture declares at least one `team_admin` for each (sophia, marc+priya,
    nadia respectively — seeded for free at team-creation time); every other
    team-scoped grant in the fixture is skipped because the importing
    `platform_admin` (a caller distinct from every bundle identity) holds no
    `team_admin` anywhere — proving the fixture round-trips through the full
    two-phase import without weakening the team-permission boundary."""
    engine = await _make_engine(tmp_path, "users-fixture.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, admin = _writable_user_deps({})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes_from_fixture()

        report = await _run(
            bundle_bytes,
            engine,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
        )

        assert report.identities_created == 15
        assert len(admin.create_calls) == 15
        assert report.users_processed == 15
        assert report.users_skipped == []
        assert report.teams_provisioned == 3
        # Free grants at team-creation time: sophia (northbridge), marc +
        # priya (fredlab), nadia (swiftpost).
        assert report.team_roles_granted == 4
        # Every other team-scoped grant in the fixture (team_editor/
        # team_member/team_analyst, or a repeated role the platform_admin
        # doesn't hold team_admin for) is skipped, not silently dropped.
        assert report.team_roles_skipped == 10
        # alice -> platform_admin, gabriel -> platform_observer.
        assert report.platform_roles_granted == 2

        metadata_store = team_deps.get_team_metadata_store()
        northbridge = await metadata_store.get_by_name("northbridge")
        fredlab = await metadata_store.get_by_name("fredlab")
        swiftpost = await metadata_store.get_by_name("swiftpost")
        assert northbridge is not None and fredlab is not None and swiftpost is not None
        assert rebac.team_admins[str(northbridge.id)] == {"created-sophia-sub"}
        assert rebac.team_admins[str(fredlab.id)] == {
            "created-marc-sub",
            "created-priya-sub",
        }
        assert rebac.team_admins[str(swiftpost.id)] == {"created-nadia-sub"}
        assert any(
            r.subject == RebacReference(Resource.USER, "created-alice-sub")
            and r.relation == RelationType.PLATFORM_ADMIN
            and r.resource == RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)
            for r in rebac.org_relations
        )
        assert any(
            r.subject == RebacReference(Resource.USER, "created-gabriel-sub")
            and r.relation == RelationType.PLATFORM_OBSERVER
            and r.resource == RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)
            for r in rebac.org_relations
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_skips_team_role_grant_platform_admin_cannot_make(
    tmp_path: Path,
) -> None:
    """bob's `team_editor` grant requires the platform_admin caller to
    already hold `team_admin` on `fredlab` — only alice (seeded at team
    creation) holds it. The grant is skipped and reported; it must not raise
    and must not fail the rest of the import."""
    engine = await _make_engine(tmp_path, "users-b.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({"alice": "alice-sub", "bob": "bob-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "alice",
                    "team_roles": {"team_admin": ["fredlab"]},
                    "platform_roles": [],
                },
                {
                    "username": "bob",
                    "team_roles": {"team_editor": ["fredlab"]},
                    "platform_roles": [],
                },
            ]
        )

        report = await _run(
            bundle_bytes,
            engine,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
        )

        assert report.teams_provisioned == 1
        assert report.team_roles_granted == 1  # alice's team_admin, at creation
        assert report.team_roles_skipped == 1  # bob's team_editor, skipped
        assert report.users_processed == 2
        assert any(
            "bob" in w and "team_editor" in w and "fredlab" in w
            for w in report.warnings
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_skips_and_reports_unresolved_username(
    tmp_path: Path,
) -> None:
    """A username with no matching Keycloak identity is skipped and reported
    — never created, and never fails the rest of the import."""
    engine = await _make_engine(tmp_path, "users-c.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({})  # empty directory: nobody resolves
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "ghost",
                    "team_roles": {"team_admin": ["fredlab"]},
                    "platform_roles": ["admin"],
                }
            ]
        )

        report = await _run(
            bundle_bytes,
            engine,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
        )

        assert report.users_processed == 0
        assert report.users_skipped == ["ghost"]
        assert report.teams_provisioned == 0  # no resolved team_admin to seed it
        assert report.platform_roles_granted == 0
        assert rebac.org_relations == []
        assert any("ghost" in w for w in report.warnings)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_rerun_is_idempotent(tmp_path: Path) -> None:
    """Re-running the same bundle twice: no duplicate team, no error
    re-granting the already-seeded team_admin, no error re-granting the
    already-held platform role."""
    engine = await _make_engine(tmp_path, "users-d.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({"alice": "alice-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "alice",
                    "team_roles": {"team_admin": ["fredlab"]},
                    "platform_roles": ["admin"],
                }
            ]
        )

        first = await _run(
            bundle_bytes,
            engine,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
        )
        assert first.teams_provisioned == 1
        assert first.team_roles_granted == 1
        assert first.platform_roles_granted == 1

        second = await _run(
            bundle_bytes,
            engine,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
        )
        assert second.teams_provisioned == 0
        assert second.team_roles_granted == 1
        assert second.team_roles_skipped == 0
        assert second.platform_roles_granted == 1
        assert second.warnings == []
    finally:
        await engine.dispose()


# ── _provision_bundle_identities: unit tests ────────────────────────────────


@pytest.mark.asyncio
async def test_provision_bundle_identities_creates_missing_user_with_password() -> None:
    """The load-bearing guarantee for the new phase: a bundle entry with no
    matching Keycloak identity and a `password` is created via `create_user`'s
    underlying `a_create_user` write call, with the expected payload. An
    entry that already resolves, and an entry with no `password`, are both
    left alone — proving the phase never overwrites an existing identity and
    never force-creates one without an explicit password."""
    user_deps, admin = _writable_user_deps({"existing": "existing-sub"})
    platform_admin = _admin_user()
    report = MigrationReport(import_id="imp-identity-1", source_platform="swift")

    bundle_users = [
        BundleUserEntry(
            username="newuser",
            email="newuser@app.com",
            first_name="New",
            last_name="User",
            password="Azerty123_",  # pragma: allowlist secret
        ),
        BundleUserEntry(
            username="existing",
            password="Azerty123_",  # pragma: allowlist secret
        ),
        BundleUserEntry(username="nopass"),
    ]

    await _provision_bundle_identities(bundle_users, user_deps, platform_admin, report)

    assert report.identities_created == 1
    assert len(admin.create_calls) == 1
    payload = admin.create_calls[0]
    assert payload["username"] == "newuser"
    assert payload["email"] == "newuser@app.com"
    assert payload["firstName"] == "New"
    assert payload["lastName"] == "User"
    assert payload["enabled"] is True
    assert payload["credentials"] == [
        {"type": "password", "value": "Azerty123_", "temporary": False}
    ]
    # existing/nopass never triggered a_create_user.
    assert {c["username"] for c in admin.create_calls} == {"newuser"}


# ── find_user_sub_by_username: unit tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_find_user_sub_by_username_resolves_existing_user() -> None:
    admin = _FakeKeycloakAdmin({"alice": "alice-sub"})
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=cast(KeycloakAdminFactory, lambda: admin),
    )

    sub = await find_user_sub_by_username("alice", deps)

    assert sub == "alice-sub"
    assert admin.calls == [{"username": "alice", "exact": True}]


@pytest.mark.asyncio
async def test_find_user_sub_by_username_returns_none_when_not_found() -> None:
    admin = _FakeKeycloakAdmin({})
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=cast(KeycloakAdminFactory, lambda: admin),
    )

    assert await find_user_sub_by_username("ghost", deps) is None


@pytest.mark.asyncio
async def test_find_user_sub_by_username_returns_none_when_keycloak_disabled() -> None:
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=lambda: KeycloackDisabled(),
    )

    assert await find_user_sub_by_username("alice", deps) is None


@pytest.mark.asyncio
async def test_find_user_sub_by_username_never_calls_a_write_method() -> None:
    """The load-bearing guarantee: the fake backing this call only implements
    the read `a_get_users` — any attempted write raises via `__getattr__`
    rather than silently succeeding, so a regression that starts creating or
    mutating users here fails loudly instead of passing quietly."""
    admin = _FakeKeycloakAdmin({"alice": "alice-sub"})
    deps = UserServiceDependencies(
        configuration=cast(Any, MagicMock()),
        create_keycloak_admin_client=cast(KeycloakAdminFactory, lambda: admin),
    )

    await find_user_sub_by_username("alice", deps)
    await find_user_sub_by_username("nobody", deps)

    # Sanity: the fake really has no write path (confirms the assertions
    # above would have failed loudly had a write ever been attempted).
    with pytest.raises(AssertionError):
        await admin.a_create_user({})  # type: ignore[attr-defined]
