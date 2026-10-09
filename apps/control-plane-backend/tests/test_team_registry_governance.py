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

"""AUTHZ-05 review item 9 (RFC Part 6 §32): team-registry governance capabilities.

`can_list_all_teams`, `can_delete_team`, `can_rescue_team_admin` let
`platform_admin` govern the *existence* of teams — they must never reach into
team data. `can_rescue_team_admin` must be mechanically inert against any team
that already has a `team_admin`: that guard is what makes it structurally
different from the `§24.7` escalation that was tried on this branch and
reverted (a standing grant reachable on every team, forever, through ordinary
membership endpoints). These tests lock in that a rescue only ever succeeds on
a genuinely orphaned team.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from control_plane_backend.teams.schemas import (
    CreateTeamRequest,
    Team,
    TeamAlreadyExistsError,
    TeamNotFoundError,
    TeamRescueNotOrphanedError,
    TeamWithPermissions,
    UpdateTeamRequest,
)
from control_plane_backend.teams.service import (
    create_team,
    delete_team,
    list_all_teams_for_registry,
    rescue_team_admin,
    search_candidate_team_admins,
    update_team,
)
from control_plane_backend.users.schemas import UserSummary
from fred_core import (
    AuthorizationError,
    KeycloakUser,
    PlatformPermission,
    SpacePermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
)
from fred_core.teams.space_models import SpaceContext, SpaceKind
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError


class _FakeRebac:
    """Records org-permission checks and relation writes/deletes for assertions."""

    def __init__(
        self,
        *,
        team_admin_ids: set[str] | None = None,
        add_relations_raises: Exception | None = None,
        granted: set[PlatformPermission] | None = None,
    ) -> None:
        self.permission_checks: list[PlatformPermission] = []
        self.team_permission_checks: list[tuple[str, tuple[TeamPermission, ...]]] = []
        self.team_admin_ids = team_admin_ids or set()
        self.added_relations: list[Relation] = []
        self.deleted_references: list[RebacReference] = []
        self._add_relations_raises = add_relations_raises
        self._granted = granted

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.permission_checks.append(permission)
        # `granted=None` keeps the permissive default every pre-existing test
        # relies on; a set turns this into a real allow-list so a delegated
        # role's exact reach can be asserted.
        if self._granted is not None and permission not in self._granted:
            raise AuthorizationError(user.uid, permission.value, Resource.PLATFORM)

    async def has_permissions(self, subject, checks, **kwargs):
        self.permission_checks.extend(permission for permission, _ in checks)
        return [
            self._granted is None
            or any(
                type(granted) is type(permission) and granted == permission
                for granted in self._granted
            )
            for permission, _ in checks
        ]

    async def check_permission_or_raise(self, subject, permission, resource, **kwargs):
        self.permission_checks.append(permission)
        if self._granted is not None and permission not in self._granted:
            raise AuthorizationError(subject.id, permission.value, resource.type)

    async def check_user_team_permissions_or_raise(
        self, *, user, team_id, permissions
    ) -> str | None:
        self.team_permission_checks.append((str(team_id), tuple(permissions)))
        return "consistency-token"

    async def lookup_subjects(self, resource, relation, subject_type, **kwargs):
        if relation == RelationType.TEAM_ADMIN:
            return [RebacReference(Resource.USER, uid) for uid in self.team_admin_ids]
        return []

    async def add_relation(self, relation: Relation, **kwargs: object):
        self.added_relations.append(relation)
        return None

    async def add_relations(self, relations, **kwargs: object):
        if self._add_relations_raises is not None:
            raise self._add_relations_raises
        for relation in relations:
            self.added_relations.append(relation)
        return "consistency-token"

    async def ensure_team_public_relations(self, team_ids) -> None:
        return None

    async def delete_all_relations_of_reference(self, reference: RebacReference):
        self.deleted_references.append(reference)
        return None


class _FakeMetadataStore:
    def __init__(
        self,
        teams: dict[str, TeamMetadata] | None = None,
        *,
        create_raises: Exception | None = None,
        upsert_raises: Exception | None = None,
    ) -> None:
        self.teams = dict(teams or {})
        self.deleted_ids: list[str] = []
        self.created: list[tuple[str, str]] = []
        self.advisory_lock_keys: list[str] = []
        self._create_raises = create_raises
        self._upsert_raises = upsert_raises

    async def get_by_team_id(self, team_id, session=None):
        return self.teams.get(str(team_id))

    async def list_all(self, session=None) -> list[TeamMetadata]:
        return list(self.teams.values())

    async def get_by_name(self, name, organization_id=None, session=None):
        return next((t for t in self.teams.values() if t.name == name), None)

    async def create(
        self, team_id, name, organization_id, session=None
    ) -> TeamMetadata:
        if self._create_raises is not None:
            raise self._create_raises
        self.created.append((str(team_id), name))
        metadata = TeamMetadata(id=TeamId(str(team_id)), name=name)
        self.teams[str(team_id)] = metadata
        return metadata

    async def upsert(self, team_id, patch, session=None) -> TeamMetadata | None:
        """Mirrors the real store's partial semantics via `to_store_values`, so a
        patch that leaves a field unset really does keep the stored value."""
        if self._upsert_raises is not None:
            raise self._upsert_raises
        existing = self.teams.get(str(team_id))
        if existing is None:
            return None
        name = patch.to_store_values().get("name")
        if name is not None and any(
            t.id != existing.id and t.name == name for t in self.teams.values()
        ):
            raise IntegrityError("UPDATE", {}, Exception("duplicate scoped name"))
        record = existing.model_dump()
        record.update(patch.to_store_values())
        updated = TeamMetadata(**record)
        self.teams[str(team_id)] = updated
        return updated

    async def delete(self, team_id, session=None) -> None:
        self.deleted_ids.append(str(team_id))
        self.teams.pop(str(team_id), None)

    @asynccontextmanager
    async def advisory_lock(self, key: str):
        """No-op stand-in for `TeamMetadataStore.advisory_lock` — records the
        key so callers can assert the right lock was requested; true
        serialization is a Postgres-only concern, not something a fake store
        needs to (or can) simulate."""
        self.advisory_lock_keys.append(key)
        yield


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="00000000-0000-0000-0000-000000000010",
        username="admin",
        roles=[],
        email=None,
    )


async def _no_users_by_ids(*_a, **_k) -> dict:
    return {}


async def _no_search_users(*_a, **_k) -> list:
    return []


class _FakePromptCategoryStoreForSeed:
    """Records `create()` calls; can be made to fail to exercise best-effort seeding."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.created: list[tuple[str, str, str]] = []  # (category_id, team_id, name)
        self._raises = raises

    async def create(self, record):
        if self._raises is not None:
            raise self._raises
        self.created.append((record.category_id, str(record.team_id), record.name))
        return record


class _FakePromptStoreForSeed:
    """Records `create()` calls for prompt rows seeded at team creation."""

    def __init__(self) -> None:
        self.created: list[
            tuple[str, str, str | None]
        ] = []  # (prompt_id, team_id, category_id)

    async def create(self, record):
        self.created.append((record.prompt_id, str(record.team_id), record.category_id))
        return record


def _deps(
    rebac: _FakeRebac,
    store: _FakeMetadataStore,
    *,
    prompt_store: Any = None,
    prompt_category_store: Any = None,
    search_users: Any = None,
):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()

    config.app.team_admin_charter_version = None
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_space_store=lambda: SimpleNamespace(
            resolve_for_user=AsyncMock(
                return_value=SpaceContext("org", SpaceKind.ORGANIZATION, "org", None)
            )
        ),
        get_default_team_store=cast(Any, object),
        get_team_admin_charter_store=cast(Any, object),
        get_prompt_store=cast(Any, lambda: prompt_store or cast(Any, object())),
        get_prompt_category_store=cast(
            Any, lambda: prompt_category_store or cast(Any, object())
        ),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, _no_users_by_ids),
        attach_avatar_urls=AsyncMock(side_effect=lambda summaries: summaries),
        search_users=cast(Any, search_users or _no_search_users),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


@pytest.fixture
def admitted_users(monkeypatch):
    store = SimpleNamespace(
        find_user_by_id=AsyncMock(return_value=SimpleNamespace(organization_id="org")),
        filter_organization_users=AsyncMock(side_effect=lambda ids, _org: set(ids)),
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service.get_user_store", lambda: store
    )
    return store


# --------------------------- create_team (name uniqueness race) -------------


@pytest.mark.asyncio
async def test_create_team_translates_db_integrity_error_to_already_exists(
    admitted_users,
) -> None:
    """AUTHZ-05 post-implementation review finding: the app-level `get_by_name`
    pre-check is a fast-path only — it cannot by itself close the race between
    two concurrent `POST /teams` calls for the same name, since both could
    pass it before either writes. Simulates that exact race (the pre-check
    reports no collision, but the store's `create` still raises because a
    concurrent write landed first and the DB's unique constraint caught it)
    and asserts it surfaces as the same `TeamAlreadyExistsError` (409) the
    fast-path raises, not a raw 500, and that nothing else was granted."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        create_raises=IntegrityError("INSERT", {}, Exception("duplicate key"))
    )

    with pytest.raises(TeamAlreadyExistsError):
        await create_team(
            _user(),
            CreateTeamRequest(
                name="swiftpost",
                initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"],
            ),
            _deps(rebac, store),
        )

    assert store.created == []
    assert rebac.added_relations == []


@pytest.mark.asyncio
async def test_create_team_stops_without_compensation_when_admin_grant_fails(
    admitted_users,
) -> None:
    """Uncertain FGA writes require explicit operator recovery."""
    rebac = _FakeRebac(add_relations_raises=RuntimeError("openfga unavailable"))
    store = _FakeMetadataStore()

    with pytest.raises(RuntimeError, match="openfga unavailable"):
        await create_team(
            _user(),
            CreateTeamRequest(
                name="swiftpost",
                initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"],
            ),
            _deps(rebac, store),
        )

    assert await store.get_by_name("swiftpost") is not None
    assert len(store.created) == 1
    assert store.deleted_ids == []
    assert rebac.added_relations == []


@pytest.mark.asyncio
async def test_seed_starter_kit_creates_categories_and_linked_prompts() -> None:
    """PROMPT-09: `_seed_starter_kit` (called by `create_team` right after the
    ReBAC bootstrap succeeds) creates the 4 starter categories and the 4
    starter prompts, each prompt correctly linked to its own category —
    replacing the removed platform-wide default-prompt catalog with real,
    team-owned, immediately editable content."""
    from control_plane_backend.product.prompt_starter_kit import (
        STARTER_CATEGORY_NAMES,
        STARTER_PROMPTS,
    )
    from control_plane_backend.teams.service import _seed_starter_kit

    rebac = _FakeRebac()
    store = _FakeMetadataStore()
    category_store = _FakePromptCategoryStoreForSeed()
    prompt_store = _FakePromptStoreForSeed()
    team_id = TeamId("swiftpost-team-id")

    await _seed_starter_kit(
        team_id,
        _deps(
            rebac,
            store,
            prompt_store=prompt_store,
            prompt_category_store=category_store,
        ),
    )

    assert len(category_store.created) == len(STARTER_CATEGORY_NAMES)
    seeded_names = {name for _cat_id, _team_id, name in category_store.created}
    assert seeded_names == set(STARTER_CATEGORY_NAMES)
    assert all(str(team_id) == tid for _cid, tid, _n in category_store.created)

    category_id_by_name = {
        name: cat_id for cat_id, _team_id, name in category_store.created
    }
    assert len(prompt_store.created) == len(STARTER_PROMPTS)
    for spec in STARTER_PROMPTS:
        match = next(
            (
                (pid, tid, cid)
                for pid, tid, cid in prompt_store.created
                if cid == category_id_by_name[spec.category_name]
            ),
            None,
        )
        assert match is not None, (
            f"no seeded prompt linked to category {spec.category_name!r}"
        )
        _prompt_id, prompt_team_id, _cid = match
        assert prompt_team_id == str(team_id)


@pytest.mark.asyncio
async def test_seed_starter_kit_failure_is_swallowed() -> None:
    """Starter-kit seeding is best-effort: a category-store failure must not
    propagate out of `_seed_starter_kit` — `create_team` calls it after the
    ReBAC bootstrap already succeeded, and a team with an empty prompt
    library is a degraded-but-valid state, unlike a missing ReBAC relation."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore()
    failing_category_store = _FakePromptCategoryStoreForSeed(
        raises=RuntimeError("db unavailable")
    )

    from control_plane_backend.teams.service import _seed_starter_kit

    # Must not raise.
    await _seed_starter_kit(
        TeamId("swiftpost-team-id"),
        _deps(rebac, store, prompt_category_store=failing_category_store),
    )


# --------------------------- update_team (team_admin rename) ----------------


def _stub_team_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `update_team`'s response tail with a bare projection.

    `_build_team_with_permissions` is a ReBAC read/BatchCheck fan-out with its
    own tests; these cover the rename rules, not the projection.
    """

    async def _build(_user, metadata, _deps, _token) -> TeamWithPermissions:
        return TeamWithPermissions(id=metadata.id, name=metadata.name)

    monkeypatch.setattr(
        "control_plane_backend.teams.service._build_team_with_permissions",
        _build,
    )


def _team_store(**names: str) -> _FakeMetadataStore:
    return _FakeMetadataStore(
        {tid: TeamMetadata(id=TeamId(tid), name=name) for tid, name in names.items()}
    )


@pytest.mark.asyncio
async def test_update_team_renames_the_team_under_can_update_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rename rides the existing team PATCH surface, so it is gated on
    `can_update_info` — exactly `team_admin` in schema.fga — and needs no
    platform-admin governance capability of its own. The stored name is the
    trimmed one: surrounding whitespace would make two visually identical
    names collide-free at the DB level."""
    rebac = _FakeRebac()
    store = _team_store(t1="Northbridge")
    _stub_team_projection(monkeypatch)

    team = await update_team(
        _user(),
        TeamId("t1"),
        UpdateTeamRequest(name="  Southbridge  "),
        _deps(rebac, store),
    )

    assert team.name == "Southbridge"
    assert store.teams["t1"].name == "Southbridge"
    assert rebac.team_permission_checks == [
        ("t1", (TeamPermission.CAN_UPDATE_INFO,)),
    ]


@pytest.mark.asyncio
async def test_update_team_refuses_a_name_another_team_already_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`teammetadata.name` is globally unique, so a rename can collide exactly
    like a create. It must surface as the same 409 and leave the team's own
    name untouched."""
    store = _team_store(t1="Northbridge", t2="Southbridge")
    _stub_team_projection(monkeypatch)

    with pytest.raises(TeamAlreadyExistsError):
        await update_team(
            _user(),
            TeamId("t1"),
            UpdateTeamRequest(name="Southbridge"),
            _deps(_FakeRebac(), store),
        )

    assert store.teams["t1"].name == "Northbridge"


@pytest.mark.asyncio
async def test_update_team_accepts_the_name_the_team_already_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The form posts every field it renders, so an unchanged name reaches the
    service on any edit. Matching the team's *own* registry row is a no-op, not
    a conflict — the rest of the patch must still apply."""
    store = _team_store(t1="Northbridge")
    _stub_team_projection(monkeypatch)

    team = await update_team(
        _user(),
        TeamId("t1"),
        UpdateTeamRequest(name="Northbridge", description="Storage team"),
        _deps(_FakeRebac(), store),
    )

    assert team.name == "Northbridge"
    assert store.teams["t1"].description == "Storage team"


@pytest.mark.asyncio
async def test_update_team_translates_a_rename_integrity_error_to_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same race as `create_team`'s: the `get_by_name` pre-check is a fast path
    only, and cannot close the window between two concurrent renames onto the
    same name. The unique constraint catches it, and the caller must still see
    a 409 rather than a raw 500."""
    store = _FakeMetadataStore(
        {"t1": TeamMetadata(id=TeamId("t1"), name="Northbridge")},
        upsert_raises=IntegrityError("UPDATE", {}, Exception("duplicate key")),
    )
    _stub_team_projection(monkeypatch)

    with pytest.raises(TeamAlreadyExistsError):
        await update_team(
            _user(),
            TeamId("t1"),
            UpdateTeamRequest(name="Southbridge"),
            _deps(_FakeRebac(), store),
        )


@pytest.mark.asyncio
async def test_update_team_does_not_mask_an_integrity_error_without_a_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only `name` is unique-constrained. A patch that renames nothing has no
    business turning a database failure into "that team name is taken"."""
    store = _FakeMetadataStore(
        {"t1": TeamMetadata(id=TeamId("t1"), name="Northbridge")},
        upsert_raises=IntegrityError("UPDATE", {}, Exception("boom")),
    )
    _stub_team_projection(monkeypatch)

    with pytest.raises(IntegrityError):
        await update_team(
            _user(),
            TeamId("t1"),
            UpdateTeamRequest(description="Storage team"),
            _deps(_FakeRebac(), store),
        )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_update_team_request_refuses_a_blank_name(value: str | None) -> None:
    """Every other field on this request treats `null` as "clear the value" —
    a team always has a name, so for this one it is a client error, not an
    erasure. A whitespace-only name is the same mistake in disguise."""
    with pytest.raises(ValidationError):
        UpdateTeamRequest.model_validate({"name": value})


def test_create_and_rename_agree_on_trimming() -> None:
    """Both write paths must trim, or the uniqueness they share is only skin
    deep: a team created as `"Ops "` and a rename to `"Ops"` would each pass
    the pre-check and the unique index, leaving two teams a reader cannot tell
    apart."""
    created = CreateTeamRequest(
        name="  Ops  ", initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"]
    )
    renamed = UpdateTeamRequest(name="  Ops  ")

    assert created.name == "Ops"
    assert renamed.name == "Ops"

    with pytest.raises(ValidationError):
        CreateTeamRequest.model_validate(
            {"name": "   ", "initial_team_admin_ids": ["alice"]}
        )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_update_team_request_keeps_clearing_other_fields(value: str | None) -> None:
    """Guard against the name rule leaking onto its neighbours: `description`
    still accepts `null` (clear it) and any string."""
    assert UpdateTeamRequest.model_validate({"description": value}).description == value


# --------------------------- can_rescue_team_admin ---------------------------


@pytest.mark.asyncio
async def test_rescue_team_admin_grants_admin_when_team_has_zero_admins() -> None:
    rebac = _FakeRebac(team_admin_ids=set())
    store = _FakeMetadataStore(
        {"orphan-team": TeamMetadata(id=TeamId("orphan-team"), name="Orphan")}
    )

    await rescue_team_admin(
        _user(), TeamId("orphan-team"), "rescued-user", _deps(rebac, store)
    )

    assert rebac.permission_checks == [PlatformPermission.CAN_RESCUE_TEAM_ADMIN]
    assert len(rebac.added_relations) == 1
    written = rebac.added_relations[0]
    assert written.subject == RebacReference(Resource.USER, "rescued-user")
    assert written.relation == RelationType.TEAM_ADMIN
    assert written.resource == RebacReference(Resource.TEAM, "orphan-team")
    # AUTHZ-05 post-implementation review finding: the zero-admin check and
    # the write must be serialized on a per-team advisory lock, since OpenFGA
    # itself cannot express "write only if this team has no team_admin yet".
    assert store.advisory_lock_keys == ["rescue_team_admin:orphan-team"]


@pytest.mark.asyncio
async def test_rescue_team_admin_rejects_when_team_already_has_an_admin() -> None:
    """The load-bearing guard: never a standing grant, only ever inert-unless-orphaned."""
    rebac = _FakeRebac(team_admin_ids={"existing-admin"})
    store = _FakeMetadataStore(
        {"staffed-team": TeamMetadata(id=TeamId("staffed-team"), name="Staffed")}
    )

    with pytest.raises(TeamRescueNotOrphanedError) as excinfo:
        await rescue_team_admin(
            _user(), TeamId("staffed-team"), "wannabe-admin", _deps(rebac, store)
        )

    assert excinfo.value.existing_admin_ids == {"existing-admin"}
    assert rebac.added_relations == []  # no relation written — mechanically inert


@pytest.mark.asyncio
async def test_rescue_team_admin_raises_not_found_for_unknown_team() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await rescue_team_admin(
            _user(), TeamId("ghost-team"), "someone", _deps(rebac, store)
        )

    assert rebac.added_relations == []


# --------------------------- can_delete_team ---------------------------


@pytest.mark.asyncio
async def test_delete_team_removes_metadata_and_all_relations() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {"gone-team": TeamMetadata(id=TeamId("gone-team"), name="Gone")}
    )

    await delete_team(_user(), TeamId("gone-team"), _deps(rebac, store))

    assert rebac.permission_checks == [PlatformPermission.CAN_DELETE_TEAM]
    assert rebac.deleted_references == [RebacReference(Resource.TEAM, "gone-team")]
    assert store.deleted_ids == ["gone-team"]


@pytest.mark.asyncio
async def test_delete_team_raises_not_found_for_unknown_team() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await delete_team(_user(), TeamId("ghost-team"), _deps(rebac, store))

    assert rebac.deleted_references == []
    assert store.deleted_ids == []


# --------------------------- can_list_all_teams ---------------------------


@pytest.mark.asyncio
async def test_list_all_teams_for_registry_checks_permission_before_delegating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct capability from `can_manage_platform` (`compute_platform_stats`'s
    caller, item 3) — narrower intent, its own gate, same underlying listing."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})
    captured: list[object] = []

    async def _fake_list_all_teams_unfiltered(user, deps):
        captured.append((user, deps))
        return []

    monkeypatch.setattr(
        "control_plane_backend.teams.service.list_all_teams_unfiltered",
        _fake_list_all_teams_unfiltered,
    )

    result = await list_all_teams_for_registry(_user(), _deps(rebac, store))

    assert result == []
    assert rebac.permission_checks == [PlatformPermission.CAN_LIST_ALL_TEAMS]
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_list_all_teams_for_registry_excludes_the_caller_personal_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTHZ-05 review item 12 (found live, 2026-07-11): `list_all_teams_unfiltered`
    mixes in the caller's own personal space (`stats.py` filters this same way for
    the same reason — see its module docstring). The registry (RFC §32) is
    `team_metadata_store` rows only; a personal space never had a row there, so
    it must never appear in `GET /teams/all`. Without this filter, the frontend
    authz self-test's foreign-team-isolation check flagged a platform_admin's own
    personal space as a "team she doesn't belong to" and failed on a false
    positive — not an actual cross-tenant leak."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    async def _fake_list_all_teams_unfiltered(user, deps):
        return [
            Team(id=TeamId("personal-platform-admin-1"), name="Equipe personnelle"),
            Team(id=TeamId("fredlab"), name="Fredlab"),
            Team(id=TeamId("northbridge"), name="Northbridge"),
        ]

    monkeypatch.setattr(
        "control_plane_backend.teams.service.list_all_teams_unfiltered",
        _fake_list_all_teams_unfiltered,
    )

    result = await list_all_teams_for_registry(_user(), _deps(rebac, store))

    assert {str(team.id) for team in result} == {"fredlab", "northbridge"}


@pytest.mark.asyncio
async def test_list_all_teams_for_registry_without_membership_reads_no_relations() -> (
    None
):
    """Pickers only need ids and names. `_FakeRebac` has no relation-read method,
    so any per-team ReBAC read on this path raises instead of passing silently."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {
            "fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab"),
            "northbridge": TeamMetadata(
                id=TeamId("northbridge"),
                name="Northbridge",
                max_resources_storage_size=10,
            ),
        }
    )
    deps = _deps(rebac, store)
    deps.configuration.app.default_team_max_resources_storage_size = 1024

    result = await list_all_teams_for_registry(_user(), deps, include_membership=False)

    assert rebac.permission_checks == [PlatformPermission.CAN_LIST_ALL_TEAMS]
    assert {
        (str(team.id), team.name, team.max_resources_storage_size) for team in result
    } == {("fredlab", "Fredlab", 1024), ("northbridge", "Northbridge", 10)}
    for team in result:
        assert team.member_count is None
        assert team.admins == []
        assert team.is_member is False
        assert team.my_relations == []


@pytest.mark.asyncio
async def test_list_all_teams_for_registry_without_membership_still_checks_permission() -> (
    None
):
    rebac = _FakeRebac(granted=set())
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    with pytest.raises(AuthorizationError):
        await list_all_teams_for_registry(
            _user(), _deps(rebac, store), include_membership=False
        )


@pytest.mark.asyncio
async def test_list_team_members_unfiltered_skips_the_per_team_permission_check() -> (
    None
):
    """AUTHZ-05 review item 14 (found live, 2026-07-11): `compute_platform_stats`
    (item 3) called the permission-checked `list_team_members` with the calling
    platform_admin's own identity, which 403s on every real team the admin isn't
    personally a member of — the common case, since `platform_admin` carries no
    standing team relation (RFC "zero implicit access"). Result: every per-team
    member/admin count on the platform data admin page silently showed 0.
    `list_team_members_unfiltered` must skip the per-team `CAN_READ_MEMEBERS`
    check the same way `list_all_teams_unfiltered` skips `CAN_READ` (item 3)."""
    from control_plane_backend.teams.service import (
        list_team_members,
        list_team_members_unfiltered,
    )

    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )
    deps = _deps(rebac, store)

    await list_team_members_unfiltered(_user(), TeamId("fredlab"), deps)
    assert rebac.team_permission_checks == []

    await list_team_members(_user(), TeamId("fredlab"), deps)
    assert rebac.team_permission_checks == [
        ("fredlab", (TeamPermission.CAN_READ_MEMEBERS,))
    ]


@pytest.mark.asyncio
async def test_get_teams_all_route_is_not_swallowed_by_team_id_path_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GET /teams/all` must be registered before `GET /teams/{team_id}` — otherwise
    the literal `all` segment is captured as a team id and routed to `get_team`
    instead of the registry listing. Also pins that `include_membership` reaches
    the service, defaulting to the full listing."""
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")

    captured_include_membership: list[bool] = []

    async def _fake_list_all_teams_for_registry(user, deps, *, include_membership):
        captured_include_membership.append(include_membership)
        return []

    monkeypatch.setattr(
        "control_plane_backend.teams.api.list_all_teams_from_service",
        _fake_list_all_teams_for_registry,
    )

    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/all")
        lean = await client.get("/control-plane/v1/teams/all?include_membership=false")

    assert resp.status_code == 200
    assert resp.json() == []
    assert lean.status_code == 200
    assert captured_include_membership == [True, False]


# --------------------------- team_manager delegation ------------------------
#
# A `team_manager` who is NOT a `platform_admin` holds exactly two org
# capabilities. These lock in both halves of that: the two surfaces the role
# owns work, and nothing else in the admin tier does.

_TEAM_MANAGER_GRANTS = {
    PlatformPermission.CAN_CREATE_TEAM,
    PlatformPermission.CAN_LIST_ALL_TEAMS,
}


def _team_manager() -> KeycloakUser:
    return KeycloakUser(uid="team-manager-1", username="mallory", roles=[], email=None)


def _team_manager_rebac(**kwargs: Any) -> _FakeRebac:
    return _FakeRebac(granted=_TEAM_MANAGER_GRANTS, **kwargs)


@pytest.mark.asyncio
async def test_organization_admin_creates_without_implicit_membership(
    monkeypatch, admitted_users
):
    rebac = _FakeRebac(granted={SpacePermission.CREATE_TEAM})
    store = _FakeMetadataStore()
    _stub_team_projection(monkeypatch)
    team = await create_team(
        _user(),
        CreateTeamRequest(
            name="Northbridge",
            initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"],
        ),
        _deps(rebac, store),
    )
    assert team.name == "Northbridge"
    assert rebac.permission_checks == [SpacePermission.CREATE_TEAM]
    assert {
        r.subject.id
        for r in rebac.added_relations
        if r.relation == RelationType.TEAM_ADMIN
    } == {"00000000-0000-0000-0000-000000000011"}


@pytest.mark.asyncio
async def test_platform_team_manager_cannot_substitute_for_organization_admin(
    admitted_users,
):
    rebac = _team_manager_rebac()
    store = _FakeMetadataStore()
    with pytest.raises(AuthorizationError):
        await create_team(
            _user(),
            CreateTeamRequest(
                name="Northbridge",
                initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"],
            ),
            _deps(rebac, store),
        )
    assert not store.created


@pytest.mark.asyncio
async def test_create_team_rejects_foreign_initial_member(admitted_users):
    admitted_users.filter_organization_users.side_effect = lambda _ids, _org: set()
    store = _FakeMetadataStore()
    from control_plane_backend.teams.schemas import TeamAdminConstraintError

    with pytest.raises(TeamAdminConstraintError, match="organization"):
        await create_team(
            _user(),
            CreateTeamRequest(
                name="Northbridge",
                initial_team_admin_ids=["00000000-0000-0000-0000-000000000011"],
            ),
            _deps(_FakeRebac(), store),
        )
    assert not store.created


@pytest.mark.asyncio
async def test_create_team_rejects_malformed_initial_member_before_writes(
    admitted_users,
):
    from control_plane_backend.teams.schemas import TeamAdminConstraintError

    store, rebac = _FakeMetadataStore(), _FakeRebac()
    with pytest.raises(TeamAdminConstraintError, match="valid user IDs"):
        await create_team(
            _user(),
            CreateTeamRequest(name="Team", initial_team_admin_ids=["invalid"]),
            _deps(rebac, store),
        )
    assert not store.created
    assert rebac.added_relations == []
    admitted_users.filter_organization_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_team_manager_lists_the_whole_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registry view must reach `list_all_teams_unfiltered` (every team)
    rather than the per-caller `CAN_READ`-filtered `list_teams` — a
    team_manager belongs to none of the teams they govern, so the filtered
    list would render `/admin/teams` empty for the role that owns it."""
    rebac = _team_manager_rebac()
    store = _FakeMetadataStore({})

    async def _fake_list_all_teams_unfiltered(user, deps):
        return [
            Team(id=TeamId("fredlab"), name="Fredlab"),
            Team(id=TeamId("northbridge"), name="Northbridge"),
        ]

    monkeypatch.setattr(
        "control_plane_backend.teams.service.list_all_teams_unfiltered",
        _fake_list_all_teams_unfiltered,
    )

    result = await list_all_teams_for_registry(_team_manager(), _deps(rebac, store))

    assert {str(team.id) for team in result} == {"fredlab", "northbridge"}
    assert rebac.permission_checks == [PlatformPermission.CAN_LIST_ALL_TEAMS]


@pytest.mark.asyncio
async def test_team_manager_cannot_delete_a_team() -> None:
    """`can_delete_team` stays platform_admin-only by design."""
    rebac = _team_manager_rebac()
    store = _team_store(t1="Northbridge")

    with pytest.raises(AuthorizationError):
        await delete_team(_team_manager(), TeamId("t1"), _deps(rebac, store))

    assert store.deleted_ids == []


@pytest.mark.asyncio
async def test_team_manager_cannot_rescue_a_team_admin() -> None:
    """`can_rescue_team_admin` stays platform_admin-only: it writes a
    `team_admin` tuple, which is the one door from the registry surface into a
    team's data."""
    rebac = _team_manager_rebac(team_admin_ids=set())
    store = _team_store(t1="Northbridge")

    with pytest.raises(AuthorizationError):
        await rescue_team_admin(
            _team_manager(), TeamId("t1"), "mallory", _deps(rebac, store)
        )

    assert rebac.added_relations == []


@pytest.mark.asyncio
async def test_team_manager_cannot_reach_a_can_manage_platform_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The delegation must be narrow: holding the two team-registry
    capabilities gives no access to the `can_manage_platform` catch-all that
    still gates import/export, tasks and platform reset. Driven through the
    real route so the assertion is about the permission that surface actually
    picks, not one this test named. This is the regression test for the whole
    point of splitting the admin tier."""
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")

    from control_plane_backend.import_export.api import _get_rebac_engine
    from control_plane_backend.main import create_app

    rebac = _team_manager_rebac()
    app = create_app()
    app.dependency_overrides[_get_rebac_engine] = lambda: cast(Any, rebac)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/import-export/stats")

    assert resp.status_code == 403
    assert rebac.permission_checks == [PlatformPermission.CAN_MANAGE_PLATFORM]


# --------------------------- candidate-admin search -------------------------


@pytest.mark.asyncio
async def test_search_candidate_team_admins_is_scoped_to_organization(admitted_users):
    from uuid import UUID

    rebac = _FakeRebac(granted={SpacePermission.CREATE_TEAM})
    identifiers = [
        "00000000-0000-0000-0000-000000000011",
        "00000000-0000-0000-0000-000000000012",
    ]
    admitted_users.filter_organization_users.side_effect = lambda _ids, _org: {
        UUID(identifiers[0])
    }

    async def search(query):
        return [
            UserSummary(id=identifier, username=query) for identifier in identifiers
        ]

    matches = await search_candidate_team_admins(
        _user(), "coh", _deps(rebac, _FakeMetadataStore(), search_users=search)
    )
    assert [user.id for user in matches] == identifiers[:1]
    assert rebac.permission_checks == [SpacePermission.CREATE_TEAM]
    admitted_users.filter_organization_users.assert_awaited_once_with(
        [UUID(identifier) for identifier in identifiers], "org"
    )


@pytest.mark.asyncio
async def test_search_candidate_team_admins_refuses_without_can_create_team() -> None:
    rebac = _FakeRebac(granted=set())
    store = _FakeMetadataStore()

    with pytest.raises(AuthorizationError):
        await search_candidate_team_admins(_user(), "coh", _deps(rebac, store))


@pytest.mark.asyncio
async def test_search_candidate_team_admins_never_degrades_into_a_directory_dump() -> (
    None
):
    """The route's `min_length=2` validates the raw string, so a whitespace-only
    query would otherwise reach Keycloak un-narrowed."""
    rebac = _FakeRebac(granted={SpacePermission.CREATE_TEAM})
    store = _FakeMetadataStore()
    calls: list[str] = []

    async def _search(query: str) -> list[UserSummary]:
        calls.append(query)
        return []

    assert (
        await search_candidate_team_admins(
            _user(), "  ", _deps(rebac, store, search_users=_search)
        )
        == []
    )
    assert calls == []


@pytest.mark.asyncio
async def test_candidate_admins_route_is_not_swallowed_by_team_id_path_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GET /teams/candidate-admins` must be registered before
    `GET /teams/{team_id}`, or the literal segment is captured as a team id."""
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")

    calls: list[str] = []

    async def _fake_search(user, query, deps):
        calls.append(query)
        return []

    monkeypatch.setattr(
        "control_plane_backend.teams.api.search_candidate_team_admins_from_service",
        _fake_search,
    )

    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/candidate-admins?query=coh")

    assert resp.status_code == 200
    assert resp.json() == []
    assert calls == ["coh"]
