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

"""#2065 follow-up: `TeamWithPermissions` projection for a collaborative team
must cost exactly 3 logical OpenFGA operations — 1 `has_permission` Check
(the route's own access gate), 1 `list_direct_relations` exact Read, and 1
`has_permissions` BatchCheck (14 `TeamPermission`s in one call) — never a
`ListUsers`/`ListObjects` fan-out, never one-Check-per-permission, and never
the `list_relations` bulk scan `ensure_team_organization_relations` used to
add: the `organization -> team` edge is established once at team creation
(`teams.service.create_team`) and repaired only on cold paths (control-plane
startup, import), never read or repaired by this per-request projection.

3 logical operations is a floor on physical HTTP requests, not a ceiling: the
`list_direct_relations` exact Read paginates, so a very large team can still
cost several HTTP round trips for that one logical operation. "3 logical ops"
means 3 distinct OpenFGA RPCs are invoked at most once each — never that the
whole projection is capped at 3 HTTP requests.

This file wires a real, call-counting `RebacEngine` (same pattern as
`test_teams_bulk_membership_call_count.py`/`test_require_team_access.py`)
rather than mocking `_build_team_with_permissions` away, so a regression back
to the old bulk-scan/14-Check projection fails these tests instead of passing
silently.
"""

from __future__ import annotations

from typing import Any, Iterable, cast
from unittest.mock import MagicMock

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import CreateTeamRequest, UserTeamRelation
from control_plane_backend.teams.service import (
    _list_teams,
    create_team,
    get_team_by_id,
    update_team,
)
from control_plane_backend.users.schemas import UserSummary
from fred_core import (
    AuthorizationError,
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    TeamVisibility,
)
from fred_core.common import TeamId
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.teams.metadata_store import TeamMetadata

_ALL_PERMISSIONS = frozenset(TeamPermission)


def _user(uid: str = "alice") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=["viewer"], email=None)


def _team_ref(team_id: str) -> RebacReference:
    return RebacReference(Resource.TEAM, team_id)


def _user_ref(user_id: str) -> RebacReference:
    return RebacReference(Resource.USER, user_id)


class _FakeMetadataStore:
    def __init__(self, teams: dict[str, TeamMetadata]) -> None:
        self._teams = dict(teams)

    async def get_by_team_id(
        self, team_id: TeamId, session=None
    ) -> TeamMetadata | None:
        return self._teams.get(str(team_id))

    async def get_by_name(self, name: str, session=None) -> TeamMetadata | None:
        return next((t for t in self._teams.values() if t.name == name), None)

    async def create(self, team_id: TeamId, name: str, session=None) -> TeamMetadata:
        metadata = TeamMetadata(id=team_id, name=name)
        self._teams[str(team_id)] = metadata
        return metadata

    async def upsert(self, team_id: TeamId, patch, session=None) -> TeamMetadata:
        existing = self._teams.get(str(team_id)) or TeamMetadata(
            id=team_id, name="Fredlab"
        )
        updated = existing.model_copy(update=patch.to_store_values())
        self._teams[str(team_id)] = updated
        return updated

    async def list_all(self) -> list[TeamMetadata]:
        return list(self._teams.values())


def _deps(
    rebac: CountingRebacEngine | NoopRebacEngine,
    store: _FakeMetadataStore,
    *,
    admin_summaries: dict[str, UserSummary] | None = None,
) -> TeamServiceDependencies:
    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    config.app.default_team_max_resources_storage_size = 5368709120

    async def _get_users_by_ids(ids: Iterable[str]) -> dict[str, UserSummary]:
        return {
            uid: (admin_summaries or {}).get(uid, UserSummary(id=uid)) for uid in ids
        }

    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=lambda: cast(Any, store),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, ConversationPolicyCatalog),
        get_users_by_ids=cast(Any, _get_users_by_ids),
        search_users=cast(Any, lambda *_a, **_k: []),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


def _admin_relation(team_id: str, user_id: str) -> Relation:
    return Relation(
        subject=_user_ref(user_id),
        relation=RelationType.TEAM_ADMIN,
        resource=_team_ref(team_id),
    )


def _member_relation(team_id: str, user_id: str) -> Relation:
    return Relation(
        subject=_user_ref(user_id),
        relation=RelationType.TEAM_MEMBER,
        resource=_team_ref(team_id),
    )


def _editor_relation(team_id: str, user_id: str) -> Relation:
    return Relation(
        subject=_user_ref(user_id),
        relation=RelationType.TEAM_EDITOR,
        resource=_team_ref(team_id),
    )


@pytest.mark.asyncio
async def test_collaborative_team_budget_is_exactly_three_logical_ops() -> None:
    """1 + 2 + 3: 1 Check (access gate) + 1 exact Read (projection) + 1
    BatchCheck of 14 — zero ListUsers/ListObjects, and zero `list_relations`
    (the org-link scan `ensure_team_organization_relations` used to add)."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions=_ALL_PERMISSIONS,
        direct_relations=[_admin_relation("fredlab", "alice")],
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert team.id == TeamId("fredlab")
    assert engine.list_relations_calls == []
    assert len(engine.has_permission_calls) == 1  # the CAN_READ access gate
    assert engine.has_permission_calls[0][1] == TeamPermission.CAN_READ
    assert len(engine.list_direct_relations_calls) == 1
    assert len(engine.has_permissions_calls) == 1
    assert len(engine.has_permissions_calls[0]) == len(_ALL_PERMISSIONS)
    assert engine.lookup_resources_calls == 0
    assert engine.lookup_subjects_calls == 0
    assert engine.add_relations_calls == []  # org edge already existed


@pytest.mark.asyncio
async def test_admin_is_rendered_with_user_summary() -> None:
    """5: a direct `team_admin` tuple renders into `Team.admins`."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions=_ALL_PERMISSIONS,
        direct_relations=[_admin_relation("fredlab", "bob")],
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )
    summaries = {"bob": UserSummary(id="bob", username="bob", email="bob@x.test")}

    team = await get_team_by_id(
        _user("alice"),
        TeamId("fredlab"),
        _deps(engine, store, admin_summaries=summaries),
    )

    assert [a.id for a in team.admins] == ["bob"]
    assert team.admins[0].username == "bob"


@pytest.mark.asyncio
async def test_member_count_is_a_deduplicated_union() -> None:
    """6: a user holding both `team_admin` and `team_editor` counts once in
    `member_count`, not twice."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions=_ALL_PERMISSIONS,
        direct_relations=[
            _admin_relation("fredlab", "bob"),
            _editor_relation("fredlab", "bob"),
            _member_relation("fredlab", "carol"),
        ],
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert team.member_count == 2  # {bob, carol}, not 3


@pytest.mark.asyncio
async def test_caller_with_member_and_editor_tuples_keeps_both_roles() -> None:
    """7: a direct `team_member` tuple alongside `team_editor` — both survive
    in `my_relations`, never collapsed to just one."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions=_ALL_PERMISSIONS,
        direct_relations=[
            _member_relation("fredlab", "alice"),
            _editor_relation("fredlab", "alice"),
        ],
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert set(team.my_relations) == {
        UserTeamRelation.TEAM_MEMBER,
        UserTeamRelation.TEAM_EDITOR,
    }


@pytest.mark.asyncio
async def test_elevated_caller_without_direct_member_tuple_counts_as_member_only() -> (
    None
):
    """8: a caller holding only `team_editor` (no direct `team_member` tuple)
    counts as a member (`is_member=True`) but must NOT receive an artificial
    `TEAM_MEMBER` entry in `my_relations` — that would misrepresent a
    literal tuple that was never written."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions=_ALL_PERMISSIONS,
        direct_relations=[_editor_relation("fredlab", "alice")],
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert team.is_member is True
    assert set(team.my_relations) == {UserTeamRelation.TEAM_EDITOR}
    assert UserTeamRelation.TEAM_MEMBER not in team.my_relations


@pytest.mark.asyncio
async def test_permission_denied_short_circuits_before_the_projection() -> None:
    """9: a denied access check must never reach the exact Read or the
    BatchCheck — the expensive projection is never built for a denied caller."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions=set()
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    with pytest.raises(AuthorizationError):
        await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert engine.list_direct_relations_calls == []
    assert engine.has_permissions_calls == []


@pytest.mark.asyncio
async def test_own_personal_space_is_zero_openfga_calls() -> None:
    """10: unchanged from before — the caller's own personal space never
    touches ReBAC at all."""

    class _UntouchableEngine(CountingRebacEngine):
        async def list_relations(self, **kwargs):
            raise AssertionError("no OpenFGA call expected for own personal space")

        async def list_direct_relations(self, *a, **k):
            raise AssertionError("no OpenFGA call expected for own personal space")

        async def has_permission(self, *a, **k):
            raise AssertionError("no OpenFGA call expected for own personal space")

        async def has_permissions(self, *a, **k):
            raise AssertionError("no OpenFGA call expected for own personal space")

    engine = _UntouchableEngine()
    store = _FakeMetadataStore({})

    team = await get_team_by_id(
        _user("alice"), TeamId("personal"), _deps(engine, store)
    )

    assert str(team.id).startswith("personal-")


@pytest.mark.asyncio
async def test_rebac_disabled_preserves_existing_behavior() -> None:
    """11: `NoopRebacEngine` — access always granted, projection resolves to
    empty membership (no tuples exist), all 14 permissions granted (Noop's
    `has_permission` always returns True, and the generic `has_permissions`
    fallback it inherits calls that 14 times)."""
    engine = NoopRebacEngine()
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert team.member_count == 0
    assert team.admins == []
    assert team.is_member is False
    assert team.my_relations == []
    assert set(team.permissions) == _ALL_PERMISSIONS


@pytest.mark.asyncio
@pytest.mark.parametrize("team_count", [3, 50])
async def test_list_teams_bulk_path_budget(team_count: int) -> None:
    """12: `_list_teams`'s OpenFGA budget, corrected for the real OpenFGA
    Read contract (confirmed live against v1.12.1 and v1.15.1, both reject a
    relation + object-type-only filter with no exact `user` — see
    `RebacEngine.list_relations`). The bulk
    organization/public existence-check (`_teams_with_relation`) still costs
    exactly one `list_relations` call per relation it actually needs to
    write/revoke — never the organization relation at all (#2065) — but
    admin/member resolution (`_bulk_team_membership`) can no longer be a
    constant number of bulk `list_relations` scans: that shape doesn't exist
    in OpenFGA for "any user" across many teams, so it is now one exact
    `list_direct_relations(team:<id>)` per team, still zero `lookup_subjects`/
    `lookup_resources` (ListUsers/ListObjects) fan-out."""
    team_ids = [f"team-{i}" for i in range(team_count)]
    engine = CountingRebacEngine(
        org_linked_team_ids=set(team_ids), public_team_ids=set(team_ids)
    )
    store = _FakeMetadataStore(
        {tid: TeamMetadata(id=TeamId(tid), name=tid) for tid in team_ids}
    )

    teams = await _list_teams(
        _user("alice"), _deps(engine, store), filter_by_can_read=False
    )

    assert len(teams) == team_count + 1  # + the caller's own personal team
    assert engine.lookup_subjects_calls == 0
    assert engine.lookup_resources_calls == 0
    # Never the organization relation (#2065); exactly the one PUBLIC
    # existence-check `list_relations` read (all teams already public here,
    # so it writes nothing; PRIVATE's `revoke_team_public_relations([])` is a
    # no-op short-circuit and never calls `list_relations` at all).
    assert engine.list_relations_calls == [(Resource.TEAM, RelationType.PUBLIC)]
    # One exact `list_direct_relations` per team — bounded by team_count, but
    # no longer O(1) in round-trips the way the (invalid) bulk-scan design
    # claimed to be.
    assert len(engine.list_direct_relations_calls) == team_count
    assert {ref.id for ref, _subject in engine.list_direct_relations_calls} == set(
        team_ids
    )


@pytest.mark.asyncio
async def test_create_get_update_share_the_same_assembler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13: `create_team`/`get_team_by_id`/`update_team` all call
    `_build_team_with_permissions` exactly once each, while keeping their own
    distinct authorization rule (create_team: org-level `CAN_CREATE_TEAM`,
    no CAN_READ on the just-created team; get_team_by_id: the caller-supplied
    `required_permissions`; update_team: `CAN_UPDATE_INFO` specifically)."""
    import control_plane_backend.teams.service as service

    calls: list[str] = []
    real_assembler = service._build_team_with_permissions

    async def _spy(user, metadata, deps, consistency_token):
        calls.append(metadata.id)
        return await real_assembler(user, metadata, deps, consistency_token)

    monkeypatch.setattr(service, "_build_team_with_permissions", _spy)

    # create_team: platform_admin is not a member of the team they create —
    # must succeed without ever being checked for CAN_READ. Only the
    # org-level CAN_CREATE_TEAM is granted; no TeamPermission at all.
    engine = CountingRebacEngine(
        granted_permissions={OrganizationPermission.CAN_CREATE_TEAM}
    )
    store = _FakeMetadataStore({})
    created = await create_team(
        _user("platform-admin"),
        CreateTeamRequest(name="new-team", initial_team_admin_ids=["alice"]),
        _deps(engine, store),
    )
    assert calls == [created.id]

    # get_team_by_id: denies when the caller lacks the requested permission.
    engine2 = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions=set()
    )
    store2 = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )
    with pytest.raises(AuthorizationError):
        await get_team_by_id(
            _user("alice"),
            TeamId("fredlab"),
            _deps(engine2, store2),
            required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
        )
    assert calls == [created.id]  # denied before the assembler ever runs

    engine3 = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions=_ALL_PERMISSIONS
    )
    fetched = await get_team_by_id(
        _user("alice"), TeamId("fredlab"), _deps(engine3, store2)
    )
    assert calls == [created.id, fetched.id]

    # update_team: requires CAN_UPDATE_INFO specifically — denied when the
    # caller only holds CAN_READ.
    engine4 = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions={TeamPermission.CAN_READ}
    )
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    with pytest.raises(AuthorizationError):
        await update_team(
            _user("alice"),
            TeamId("fredlab"),
            UpdateTeamRequest(description="x"),
            _deps(engine4, store2),
        )
    assert calls == [created.id, fetched.id]  # still denied before the assembler

    engine5 = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions=_ALL_PERMISSIONS
    )
    updated = await update_team(
        _user("alice"),
        TeamId("fredlab"),
        UpdateTeamRequest(description="Updated"),
        _deps(engine5, store2),
    )
    assert calls == [created.id, fetched.id, updated.id]
    assert updated.description == "Updated"


@pytest.mark.asyncio
async def test_missing_organization_edge_is_never_read_or_repaired() -> None:
    """3: #2065 removed the self-heal this test used to cover — a team whose
    `organization -> team` edge doesn't exist yet (e.g. one created before the
    invariant existed, not yet reached by control-plane startup
    reconciliation) is no longer detected or repaired by `get_team_by_id`:
    nothing in schema.fga's computed team permissions reads that edge, so the
    projection succeeds exactly the same with or without it. Zero
    `list_relations`, zero writes, and — since the caller's own access check
    performs no write anymore — both the exact `list_direct_relations` Read
    and the `has_permissions` BatchCheck receive `None`, not a token."""
    engine = CountingRebacEngine(
        org_linked_team_ids=set(), granted_permissions=_ALL_PERMISSIONS
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    team = await get_team_by_id(_user("alice"), TeamId("fredlab"), _deps(engine, store))

    assert team.id == TeamId("fredlab")
    assert engine.list_relations_calls == []
    assert engine.add_relations_calls == []
    assert engine.list_direct_relations_tokens == [None]
    assert engine.has_permissions_tokens == [None]


@pytest.mark.asyncio
async def test_get_user_roles_in_team_reads_only_the_target_user() -> None:
    """6: `_get_user_roles_in_team` (used by `remove_team_member`/
    `revoke_team_member_role`) must issue a `list_direct_relations` Read
    scoped to `subject=user:<id>` — never a transfer of every member's
    relations filtered down client-side afterward."""
    from control_plane_backend.teams.service import _get_user_roles_in_team

    engine = CountingRebacEngine(
        direct_relations=[
            _admin_relation("fredlab", "bob"),
            _member_relation("fredlab", "carol"),
        ],
    )

    roles = await _get_user_roles_in_team(engine, TeamId("fredlab"), "bob")

    assert roles == {UserTeamRelation.TEAM_ADMIN}
    assert engine.list_direct_relations_calls == [
        (_team_ref("fredlab"), _user_ref("bob"))
    ]


@pytest.mark.asyncio
async def test_create_team_response_includes_admins_immediately() -> None:
    """7: `create_team`'s response must reflect the just-written
    `initial_team_admin_ids` in `admins`, `member_count`, and the direct
    relations it renders from — proving the write is actually visible to the
    projection's Read, not just that a token value was threaded through
    unused. #2065: the same bootstrap write also carries the organization
    structural edge — written exactly once, with no prior existence-check
    read — and its token (there being nothing else to prefer it over) is what
    propagates to the projection's Read and BatchCheck."""
    engine = CountingRebacEngine(
        granted_permissions={OrganizationPermission.CAN_CREATE_TEAM}
    )
    store = _FakeMetadataStore({})
    summaries = {"alice": UserSummary(id="alice", username="alice")}

    created = await create_team(
        _user("platform-admin"),
        CreateTeamRequest(name="new-team", initial_team_admin_ids=["alice"]),
        _deps(engine, store, admin_summaries=summaries),
    )

    assert [a.id for a in created.admins] == ["alice"]
    assert created.member_count == 1
    assert set(created.my_relations) == set()  # the creator isn't a member
    assert _admin_relation(str(created.id), "alice") in engine.direct_relations
    # The only `list_relations` call left is the (unrelated) TEAM-09 public
    # existence-check — never an organization existence-check read.
    assert engine.list_relations_calls == [(Resource.TEAM, RelationType.PUBLIC)]
    org_relations = [
        r for r in engine.direct_relations if r.relation == RelationType.ORGANIZATION
    ]
    assert org_relations == [
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, "fred"),
            relation=RelationType.ORGANIZATION,
            resource=_team_ref(str(created.id)),
        )
    ]
    assert engine.list_direct_relations_tokens == ["consistency-token"]
    assert engine.has_permissions_tokens == ["consistency-token"]


@pytest.mark.asyncio
async def test_update_team_visibility_write_propagates_its_own_token() -> None:
    """3: `update_team`'s PATCH may write the `public` relation (a visibility
    change) after the caller's own access check already ran — in a steady
    state where that earlier check wrote nothing (`consistency_token=None`),
    the visibility write's own token must win for the projection's Read and
    BatchCheck, never the stale `None` from before the write."""
    from control_plane_backend.teams.schemas import UpdateTeamRequest

    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},  # steady state: access check writes nothing
        granted_permissions=_ALL_PERMISSIONS,
    )
    store = _FakeMetadataStore(
        {
            "fredlab": TeamMetadata(
                id=TeamId("fredlab"), name="Fredlab", visibility=TeamVisibility.PRIVATE
            )
        }
    )

    await update_team(
        _user("alice"),
        TeamId("fredlab"),
        UpdateTeamRequest(visibility=TeamVisibility.PUBLIC),
        _deps(engine, store),
    )

    assert engine.add_relations_calls  # the public relation write actually happened
    assert engine.list_direct_relations_tokens == ["consistency-token"]
    assert engine.has_permissions_tokens == ["consistency-token"]
