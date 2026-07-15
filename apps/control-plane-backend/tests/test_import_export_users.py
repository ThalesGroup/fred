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

"""AUTHZ-07 Part 8 §40.2 / Step 2: declarative platform provisioning for
identities/teams/roles/users.

The `users.json` bundle entry names a Keycloak identity by username and
describes the Fred-side authorization state it should end up with (team
membership, team roles, platform roles). This importer
(`import_export/importer.py::_run_users_phase`) is two-phase: phase 1
(`_provision_bundle_identities`) creates a Keycloak identity for any entry
that has no existing match AND carries a `password`; phase 2 resolves
username → sub and grants every declared role. An entry with no `password`
is assumed to already exist — it is never force-created.

AUTHZ-07 Step 2 (this file's main subject) fixed the original design gap:
every team-scoped grant used to go through the ordinary, `team_admin`-gated
`teams.service.grant_team_member_role`, which the importing `platform_admin`
can never satisfy by design (RFC Part 8 §24.2/§24.7 — "zero implicit
access"), so every non-admin team-scoped grant in a real bundle was silently
downgraded to a skipped-and-reported warning while the import still reported
`succeeded`. The fix routes every team-scoped grant through
`_grant_team_role_via_import` — a private primitive that writes the relation
directly via `RebacEngine.add_relation`, exactly like `_grant_platform_role`
already does for org-level roles — and makes every unrecoverable bundle
problem (unknown role name, unresolved identity, unprovisionable team) raise
`BundleProvisioningError` instead of being downgraded to a warning. The
*ordinary* team-membership APIs (`grant_team_member_role`, `add_team_member`,
etc.) are completely unchanged and stay `team_admin`-bounded — proven by a
dedicated test below that calls `grant_team_member_role` directly with the
same importer identity and expects it to still refuse.

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
from uuid import uuid4

import pytest
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export.bundle import open_bundle
from control_plane_backend.import_export.importer import (
    BundleProvisioningError,
    MigrationReport,
    _effective_team_relations,
    _provision_bundle_identities,
    _run_users_phase,
    run_import,
)
from control_plane_backend.import_export.schemas import BundleUserEntry
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import (
    GrantTeamMemberRoleRequest,
    UserTeamRelation,
)
from control_plane_backend.teams.service import grant_team_member_role
from control_plane_backend.users.dependencies import (
    KeycloakAdminFactory,
    UserServiceDependencies,
)
from control_plane_backend.users.service import find_user_sub_by_username
from fred_core import (
    ORGANIZATION_ID,
    AuthorizationError,
    KeycloackDisabled,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.common import TeamId
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.security.rebac.noop_engine import NoopRebacEngine
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
        # Production `RebacEngine` implementations expose `enabled` (see
        # `RebacEngine.enabled`/`NoopRebacEngine.enabled`), and
        # `_run_users_phase` now checks `team_deps.rebac.enabled` before
        # doing anything else (AUTHZ-07 review r3585102660) — this fake must
        # report the same thing a real, active ReBAC engine would.
        self.enabled = True

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


class _SpyNoopRebac(NoopRebacEngine):
    """The real production no-op engine (`NoopRebacEngine`), spied on rather
    than reimplemented, so the ReBAC-disabled tests below prove `add_relation`
    is never even called — not just that it would have been a no-op."""

    def __init__(self) -> None:
        self.add_relation_calls: list[Relation] = []

    async def add_relation(self, relation: Relation) -> str | None:
        self.add_relation_calls.append(relation)
        return await super().add_relation(relation)


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
        raise AttributeError(
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
        get_policy_catalog=ConversationPolicyCatalog,
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
async def test_users_phase_full_fixture_reconciles_all_identities_teams_and_roles(
    tmp_path: Path,
) -> None:
    """The success path, end-to-end through the checked-in demo fixture
    (`tests/fixtures/import_export/demo_provisioning/` — the same fixture
    `make build-demo-bundle` packages). None of its 15 entries has an existing
    Keycloak identity, and every entry carries a password, so the identity
    phase (phase 1) creates all 15 first; the role phase (phase 2) then
    resolves every one of them and provisions every declared team/role.
    `northbridge`/`fredlab`/`swiftpost` each get created because the fixture
    declares at least one `team_admin` for each (sophia, marc+priya, nadia
    respectively — seeded for free at team-creation time). AUTHZ-07 Step 2
    (this test's load-bearing assertion): every *other* team-scoped grant in
    the fixture (bob's/derek's `team_editor`, phil's/zoe's/liam's
    `team_member`, elena's `team_analyst`, priya's extra `team_editor`+
    `team_analyst`) is now granted too, via the private
    `_grant_team_role_via_import` primitive — none of them skipped, even
    though the importing `platform_admin` (a caller distinct from every
    bundle identity) holds no `team_admin` anywhere. Before the fix, exactly
    these 10 grants were the ones silently downgraded to warnings."""
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
        # 2 (sophia team_admin) + 2 (marc, priya team_admin) + 1 (nadia
        # team_admin) seeded at creation, plus bob(x2)/phil(x2)/zoe/liam/
        # elena/derek/priya(x2 more) granted via the fix = 14 total.
        assert report.team_roles_granted == 14
        assert report.team_roles_skipped == 0
        # alice -> platform_admin, gabriel -> platform_observer.
        assert report.platform_roles_granted == 2
        assert report.warnings == []

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

        def _has(subject_sub: str, relation: RelationType, team_id: TeamId) -> bool:
            return any(
                r.subject == RebacReference(Resource.USER, subject_sub)
                and r.relation == relation
                and r.resource == RebacReference(Resource.TEAM, team_id)
                for r in rebac.team_relations
            )

        # bob's team_editor on both northbridge and fredlab — refused before
        # the fix, granted now.
        assert _has("created-bob-sub", RelationType.TEAM_EDITOR, northbridge.id)
        assert _has("created-bob-sub", RelationType.TEAM_EDITOR, fredlab.id)
        # phil's/zoe's/liam's explicit team_member.
        assert _has("created-phil-sub", RelationType.TEAM_MEMBER, northbridge.id)
        assert _has("created-phil-sub", RelationType.TEAM_MEMBER, swiftpost.id)
        assert _has("created-zoe-sub", RelationType.TEAM_MEMBER, fredlab.id)
        assert _has("created-liam-sub", RelationType.TEAM_MEMBER, swiftpost.id)
        # elena's team_analyst, derek's team_editor.
        assert _has("created-elena-sub", RelationType.TEAM_ANALYST, fredlab.id)
        assert _has("created-derek-sub", RelationType.TEAM_EDITOR, northbridge.id)
        # priya's cumulative roles: team_admin (seeded) + team_editor +
        # team_analyst, all three persisted, and no redundant direct
        # team_member tuple (schema.fga derives it from the three above).
        assert _has("created-priya-sub", RelationType.TEAM_ADMIN, fredlab.id)
        assert _has("created-priya-sub", RelationType.TEAM_EDITOR, fredlab.id)
        assert _has("created-priya-sub", RelationType.TEAM_ANALYST, fredlab.id)
        assert not _has("created-priya-sub", RelationType.TEAM_MEMBER, fredlab.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_grants_non_admin_role_on_fresh_team(
    tmp_path: Path,
) -> None:
    """AUTHZ-07 Step 2 — the regression this fix closes: bob's `team_editor`
    grant on the brand-new `fredlab` team (created in the same run because
    alice's entry seeds its `team_admin`) is granted directly, even though
    the importing `platform_admin` never holds `team_admin` on `fredlab`
    anywhere. Before the fix, this exact bundle produced `team_roles_skipped
    == 1` and a warning; it must now produce zero skips."""
    engine = await _make_engine(tmp_path, "users-fresh-nonadmin.sqlite3")
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
        assert report.team_roles_granted == 2  # alice's team_admin + bob's team_editor
        assert report.team_roles_skipped == 0
        assert report.users_processed == 2
        assert report.warnings == []

        metadata_store = team_deps.get_team_metadata_store()
        fredlab = await metadata_store.get_by_name("fredlab")
        assert fredlab is not None
        assert any(
            r.subject == RebacReference(Resource.USER, "bob-sub")
            and r.relation == RelationType.TEAM_EDITOR
            and r.resource == RebacReference(Resource.TEAM, fredlab.id)
            for r in rebac.team_relations
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_reconciles_role_on_preexisting_team_without_importer_team_admin(
    tmp_path: Path,
) -> None:
    """The load-bearing regression test for AUTHZ-07 Step 2: a team that
    already existed *before* this import (so it is never (re-)created, and no
    team_admin needs seeding for it) still gets its declared team-scoped role
    granted, even though the importing `platform_admin` holds no `team_admin`
    on it anywhere. Before the fix, this exact scenario was refused by
    `grant_team_member_role` and silently downgraded to a skip+warning."""
    engine = await _make_engine(tmp_path, "users-preexisting-team.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        metadata_store = team_deps.get_team_metadata_store()
        team_id = TeamId(uuid4().hex)
        await metadata_store.create(team_id, "fredlab")

        user_deps, _admin = _user_deps({"bob": "bob-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "bob",
                    "team_roles": {"team_editor": ["fredlab"]},
                    "platform_roles": [],
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

        assert report.teams_provisioned == 0  # pre-existing, never (re-)created
        assert report.team_roles_granted == 1
        assert report.team_roles_skipped == 0
        assert any(
            r.subject == RebacReference(Resource.USER, "bob-sub")
            and r.relation == RelationType.TEAM_EDITOR
            and r.resource == RebacReference(Resource.TEAM, team_id)
            for r in rebac.team_relations
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_fails_on_unknown_team_role(tmp_path: Path) -> None:
    """AUTHZ-07 Step 2: an unknown team-role name is a fail-closed validation
    error, not a warning — the whole import aborts before any write, proven
    here by asserting zero relations were ever written."""
    engine = await _make_engine(tmp_path, "users-unknown-role.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({"alice": "alice-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "alice",
                    "team_roles": {"team_superadmin": ["fredlab"]},
                    "platform_roles": [],
                }
            ]
        )

        with pytest.raises(BundleProvisioningError, match="unknown team role"):
            await _run(
                bundle_bytes,
                engine,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
            )

        assert rebac.team_relations == []
        assert rebac.org_relations == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_fails_on_unknown_platform_role(tmp_path: Path) -> None:
    """AUTHZ-07 Step 2: same fail-closed rule for an unknown `platform_roles`
    value."""
    engine = await _make_engine(tmp_path, "users-unknown-platform-role.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({"alice": "alice-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [{"username": "alice", "team_roles": {}, "platform_roles": ["superuser"]}]
        )

        with pytest.raises(BundleProvisioningError, match="unknown platform role"):
            await _run(
                bundle_bytes,
                engine,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
            )

        assert rebac.org_relations == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_fails_on_unresolved_username(tmp_path: Path) -> None:
    """AUTHZ-07 Step 2: a username with no matching Keycloak identity after
    the identity phase is now a fail-closed condition — the import aborts
    instead of silently skipping the entry and still reaching `succeeded`."""
    engine = await _make_engine(tmp_path, "users-unresolved.sqlite3")
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

        with pytest.raises(BundleProvisioningError, match="ghost"):
            await _run(
                bundle_bytes,
                engine,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
            )

        assert rebac.org_relations == []
        assert rebac.team_relations == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_fails_when_team_cannot_be_provisioned(
    tmp_path: Path,
) -> None:
    """AUTHZ-07 Step 2: a team referenced only via a non-admin role, with no
    `team_admin` declared anywhere in the bundle for it, cannot be created
    (`create_team` requires at least one initial `team_admin`) — this is now
    a fail-closed condition, not a silent skip."""
    engine = await _make_engine(tmp_path, "users-team-unprovisionable.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        user_deps, _admin = _user_deps({"bob": "bob-sub"})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "bob",
                    "team_roles": {"team_editor": ["fredlab"]},
                    "platform_roles": [],
                }
            ]
        )

        with pytest.raises(BundleProvisioningError, match="fredlab"):
            await _run(
                bundle_bytes,
                engine,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
            )

        assert rebac.team_relations == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_fails_when_rebac_disabled(tmp_path: Path) -> None:
    """Review thread on PR #1987 (discussion_r3585102660): when ReBAC is
    disabled, `team_deps.rebac` is `NoopRebacEngine` — every `add_relation`
    call it makes is a silent no-op, so `_apply_bundle_user_roles` would still
    increment `team_roles_granted`/`platform_roles_granted` and let the
    import finish `succeeded` while no authorization tuple was ever written.
    The users phase now refuses to run at all in that case, end-to-end
    through `run_import()`: no Keycloak identity is created (even though this
    entry carries a `password`) and no team is provisioned, proving the guard
    runs before phase 1 (identity creation) and phase 2 (team/role
    provisioning), not just before the role-granting loop."""
    engine = await _make_engine(tmp_path, "users-rebac-disabled.sqlite3")
    try:
        spy_rebac = _SpyNoopRebac()
        team_deps = _team_deps(engine, cast(Any, spy_rebac))
        user_deps, admin = _writable_user_deps({})
        platform_admin = _admin_user()

        bundle_bytes = _build_bundle_bytes(
            [
                {
                    "username": "alice",
                    "email": "alice@app.com",
                    "first_name": "Alice",
                    "last_name": "Watson",
                    "password": "Azerty123_",  # pragma: allowlist secret
                    "team_roles": {"team_admin": ["fredlab"]},
                    "platform_roles": ["admin"],
                }
            ]
        )

        with pytest.raises(BundleProvisioningError, match="ReBAC is disabled"):
            await _run(
                bundle_bytes,
                engine,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
            )

        assert admin.create_calls == []
        metadata_store = team_deps.get_team_metadata_store()
        assert await metadata_store.get_by_name("fredlab") is None
        assert spy_rebac.add_relation_calls == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_users_phase_rebac_disabled_guard_precedes_every_counter_increment(
    tmp_path: Path,
) -> None:
    """Same regression as `test_users_phase_fails_when_rebac_disabled`, but
    calling `_run_users_phase` directly (like
    `test_provision_bundle_identities_creates_missing_user_with_password`
    does for phase 1) so the test owns the `MigrationReport` instance and can
    assert every counter the phase could have touched — identities_created,
    users_processed, teams_provisioned, team_roles_granted,
    platform_roles_granted — is still at its zero default after the
    exception, not just that the import failed."""
    engine = await _make_engine(tmp_path, "users-phase-rebac-disabled.sqlite3")
    try:
        spy_rebac = _SpyNoopRebac()
        team_deps = _team_deps(engine, cast(Any, spy_rebac))
        user_deps, admin = _writable_user_deps({})
        platform_admin = _admin_user()
        task_service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
        start = await task_service.start(
            StartMigrationRequest(), created_by=platform_admin.uid
        )
        report = MigrationReport(
            import_id="imp-rebac-disabled", source_platform="swift"
        )

        bundle_users = [
            BundleUserEntry(
                username="alice",
                email="alice@app.com",
                first_name="Alice",
                last_name="Watson",
                password="Azerty123_",  # pragma: allowlist secret
                team_roles={"team_admin": ["fredlab"]},
                platform_roles=["admin"],
            )
        ]

        with pytest.raises(BundleProvisioningError, match="ReBAC is disabled"):
            await _run_users_phase(
                bundle_users=bundle_users,
                platform_admin=platform_admin,
                user_deps=user_deps,
                team_deps=team_deps,
                task_service=task_service,
                task_id=start.task_id,
                report=report,
            )

        assert admin.create_calls == []
        metadata_store = team_deps.get_team_metadata_store()
        assert await metadata_store.get_by_name("fredlab") is None
        assert spy_rebac.add_relation_calls == []
        assert report.identities_created == 0
        assert report.users_processed == 0
        assert report.teams_provisioned == 0
        assert report.team_roles_granted == 0
        assert report.platform_roles_granted == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_users_phase_rerun_is_idempotent(tmp_path: Path) -> None:
    """Re-running the same bundle twice: no duplicate team, no error
    re-granting the already-seeded team_admin, no error re-granting the
    already-held platform role, and — AUTHZ-07 Step 2 — zero skips on either
    run."""
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
        assert first.team_roles_skipped == 0
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


# ── ordinary team API boundary unchanged ────────────────────────────────────


@pytest.mark.asyncio
async def test_grant_team_member_role_still_requires_team_admin_for_the_importer(
    tmp_path: Path,
) -> None:
    """AUTHZ-07 Step 2 fixed the *import* path only. The ordinary
    team-membership API's permission boundary is completely unchanged:
    `teams.service.grant_team_member_role` still refuses a caller (here, the
    same platform_admin identity the import flow uses) that holds no
    `team_admin` on the target team — proving the fix is a narrow, private,
    import-only primitive, not a relaxation of the ordinary permission
    model."""
    engine = await _make_engine(tmp_path, "grant-ordinary-still-gated.sqlite3")
    try:
        rebac = _FakeTeamRebac()
        team_deps = _team_deps(engine, rebac)
        metadata_store = team_deps.get_team_metadata_store()
        team_id = TeamId(uuid4().hex)
        await metadata_store.create(team_id, "fredlab")
        platform_admin = _admin_user()

        with pytest.raises(AuthorizationError):
            await grant_team_member_role(
                platform_admin,
                team_id,
                "bob-sub",
                GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_EDITOR),
                team_deps,
            )
    finally:
        await engine.dispose()


# ── _effective_team_relations: unit tests (teams/team_roles semantics) ──────


def test_effective_team_relations_teams_without_role_falls_back_to_team_member() -> (
    None
):
    """`PLATFORM-IMPORT-RFC.md` §10: a team named in `teams` with no explicit
    role for this entry requests a single direct `team_member` tuple."""
    entry = BundleUserEntry(username="alice", teams=["fredlab"])
    assert _effective_team_relations(entry) == {
        "fredlab": {UserTeamRelation.TEAM_MEMBER}
    }


def test_effective_team_relations_explicit_role_suppresses_team_member_fallback() -> (
    None
):
    """A team with an explicit role never also gets the direct `team_member`
    fallback tuple — schema.fga already derives `team_member` from
    `team_admin`/`team_editor`/`team_analyst`."""
    entry = BundleUserEntry(
        username="bob",
        teams=["fredlab"],
        team_roles={"team_editor": ["fredlab"]},
    )
    assert _effective_team_relations(entry) == {
        "fredlab": {UserTeamRelation.TEAM_EDITOR}
    }


def test_effective_team_relations_cumulative_roles_on_same_team() -> None:
    """Multiple explicit roles on the same team are cumulative — all
    persisted, matching priya's `team_admin`+`team_editor`+`team_analyst` on
    `fredlab` in the demo fixture."""
    entry = BundleUserEntry(
        username="priya",
        teams=["fredlab"],
        team_roles={
            "team_admin": ["fredlab"],
            "team_editor": ["fredlab"],
            "team_analyst": ["fredlab"],
        },
    )
    assert _effective_team_relations(entry) == {
        "fredlab": {
            UserTeamRelation.TEAM_ADMIN,
            UserTeamRelation.TEAM_EDITOR,
            UserTeamRelation.TEAM_ANALYST,
        }
    }


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
        create_keycloak_admin_client=KeycloackDisabled,
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
    with pytest.raises(AttributeError):
        await admin.a_create_user({})  # type: ignore[attr-defined]
