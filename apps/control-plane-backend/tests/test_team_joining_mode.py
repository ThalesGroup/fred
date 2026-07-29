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

"""TEAM-09 (FRED-TEAM-CONFIG-RFC.md §5.1.1): self-service team joining.

`join_team` is the only membership-write path that does not require the
caller to already hold an administer-permission over the target team — every
other route (`add_team_member` and friends) is intentionally team-admin-gated.
That makes its two safety properties load-bearing and worth locking in with
tests: it must (1) only ever succeed when the stored `joining_mode` is `OPEN`
(never trusting the client's belief about it), and (2) only ever grant
`team_member` to the caller themselves, never another user or another role.

#2065 follow-up: `join_team` builds its response directly through
`_build_team_with_permissions` instead of re-running `get_team_by_id` (a
second `ensure_team_organization_relations` Read + `CAN_READ` Check cycle) —
the write that just succeeded already establishes `can_read` (schema.fga:
`team_member or public`), so re-checking it is a redundant round-trip, not an
extra safety property. The budget test below locks that in: exactly the
`team_member` write, the projection's exact `list_direct_relations` Read, and
its `has_permissions` BatchCheck — zero extra `list_relations`/`has_permission`
calls — with the write's own consistency token reaching both reads.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.teams.schemas import TeamNotOpenForJoiningError
from control_plane_backend.teams.service import join_team
from fred_core import (
    JoiningMode,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata

pytestmark = pytest.mark.asyncio


class _FakeRebac:
    def __init__(self) -> None:
        self.added_relations: list[Relation] = []

    async def add_relation(self, relation: Relation, **kwargs: object):
        self.added_relations.append(relation)
        return None


class _FakeMetadataStore:
    def __init__(self, teams: dict[str, TeamMetadata] | None = None) -> None:
        self.teams = dict(teams or {})

    async def get_by_team_id(self, team_id, session=None):
        return self.teams.get(str(team_id))


def _user(uid: str = "wannabe-member") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


async def _no_users_by_ids(*_a, **_k) -> dict:
    return {}


def _deps(rebac: object, store: _FakeMetadataStore):
    from control_plane_backend.scheduler.policies.policy_models import (
        ConversationPolicyCatalog,
    )
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    config.app.default_team_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, ConversationPolicyCatalog),
        get_users_by_ids=cast(Any, _no_users_by_ids),
        search_users=cast(Any, lambda *_a, **_k: []),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


async def test_join_team_rejects_when_not_open() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {
            "guarded-team": TeamMetadata(
                id=TeamId("guarded-team"),
                name="Guarded",
                joining_mode=JoiningMode.INVITE_ONLY,
            )
        }
    )

    with pytest.raises(TeamNotOpenForJoiningError) as excinfo:
        await join_team(_user(), TeamId("guarded-team"), _deps(rebac, store))

    assert excinfo.value.joining_mode == JoiningMode.INVITE_ONLY
    assert rebac.added_relations == []  # never writes when the gate fails


async def test_join_team_raises_not_found_for_unknown_team() -> None:
    from control_plane_backend.teams.schemas import TeamNotFoundError

    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await join_team(_user(), TeamId("ghost-team"), _deps(rebac, store))

    assert rebac.added_relations == []


async def test_join_team_grants_team_member_to_self_only_when_open() -> None:
    rebac = CountingRebacEngine(org_linked_team_ids={"open-team"})
    store = _FakeMetadataStore(
        {
            "open-team": TeamMetadata(
                id=TeamId("open-team"), name="Open", joining_mode=JoiningMode.OPEN
            )
        }
    )

    team = await join_team(_user("alice"), TeamId("open-team"), _deps(rebac, store))

    assert len(rebac.add_relations_calls) == 0  # join_team writes via add_relation
    written = rebac.direct_relations[-1]
    assert written.subject == RebacReference(Resource.USER, "alice")
    assert written.relation == RelationType.TEAM_MEMBER
    assert written.resource == RebacReference(Resource.TEAM, "open-team")

    # The write already establishes `can_read` (team_member or public) — the
    # response reflects it immediately, with no extra round trip.
    assert team.is_member is True
    from control_plane_backend.teams.schemas import UserTeamRelation

    assert UserTeamRelation.TEAM_MEMBER in team.my_relations


async def test_join_team_budget_skips_the_redundant_ensure_org_and_check_cycle() -> (
    None
):
    """The old `join_team` delegated to `get_team_by_id`, which re-runs
    `ensure_team_organization_relations` (a `list_relations` Read) and a
    `CAN_READ` `has_permission` Check. Neither is needed: the org edge was
    already established when the team was created/listed, and a fresh
    `team_member` write already satisfies `can_read` unconditionally. Budget:
    just the membership write, the projection's one exact
    `list_direct_relations` Read, and its `has_permissions` BatchCheck — zero
    `list_relations`/`has_permission` calls."""
    rebac = CountingRebacEngine(org_linked_team_ids={"open-team"})
    store = _FakeMetadataStore(
        {
            "open-team": TeamMetadata(
                id=TeamId("open-team"), name="Open", joining_mode=JoiningMode.OPEN
            )
        }
    )

    await join_team(_user("alice"), TeamId("open-team"), _deps(rebac, store))

    assert rebac.list_relations_calls == []
    assert rebac.has_permission_calls == []
    assert len(rebac.list_direct_relations_calls) == 1
    assert len(rebac.has_permissions_calls) == 1


async def test_join_team_propagates_the_write_token_to_the_projection_reads() -> None:
    """The membership write's own consistency token must reach both the
    projection's exact Read and its BatchCheck, so the just-granted
    membership is guaranteed visible there instead of racing eventual
    consistency."""
    rebac = CountingRebacEngine(
        org_linked_team_ids={"open-team"}, granted_permissions=frozenset(TeamPermission)
    )
    store = _FakeMetadataStore(
        {
            "open-team": TeamMetadata(
                id=TeamId("open-team"), name="Open", joining_mode=JoiningMode.OPEN
            )
        }
    )

    await join_team(_user("alice"), TeamId("open-team"), _deps(rebac, store))

    assert rebac.list_direct_relations_tokens == ["consistency-token"]
    assert rebac.has_permissions_tokens == ["consistency-token"]
