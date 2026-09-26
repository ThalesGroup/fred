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

"""Self-service joining requires OPEN mode and membership of the team's organization.

Membership writes target only the caller. The response reuses the write's
consistency token and avoids a redundant post-write authorization check.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.teams.schemas import TeamNotOpenForJoiningError
from control_plane_backend.teams.service import join_team
from fred_core import (
    AuthorizationError,
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


@pytest.fixture(autouse=True)
def organization_onboarding(monkeypatch):
    """Exercise the join gate separately from organization onboarding persistence."""
    from control_plane_backend.organizations import service

    onboarding = AsyncMock(return_value={"fred"})
    monkeypatch.setattr(service, "ensure_user_organizations", onboarding, raising=False)
    return onboarding


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

    config.app.team_admin_charter_version = None
    config.app.personal_max_resources_storage_size = 5368709120
    config.app.default_team_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_default_team_store=cast(Any, object),
        get_team_admin_charter_store=cast(Any, object),
        get_prompt_store=cast(Any, object),
        get_prompt_category_store=cast(Any, object),
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
    rebac = CountingRebacEngine(
        org_linked_team_ids={"open-team"}, granted_permissions={TeamPermission.CAN_JOIN}
    )
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
    """One pre-write organization check, no redundant post-write check."""
    rebac = CountingRebacEngine(
        org_linked_team_ids={"open-team"}, granted_permissions={TeamPermission.CAN_JOIN}
    )
    store = _FakeMetadataStore(
        {
            "open-team": TeamMetadata(
                id=TeamId("open-team"), name="Open", joining_mode=JoiningMode.OPEN
            )
        }
    )

    await join_team(_user("alice"), TeamId("open-team"), _deps(rebac, store))

    assert rebac.list_relations_calls == []
    assert rebac.has_permission_calls == [
        ("alice", TeamPermission.CAN_JOIN, "open-team")
    ]
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


async def test_cross_organization_join_is_denied_before_membership_write(
    organization_onboarding,
):
    organization_onboarding.return_value = {"a"}
    rebac = CountingRebacEngine(org_linked_team_ids={"open-b"})
    store = _FakeMetadataStore(
        {
            "open-b": TeamMetadata(
                id=TeamId("open-b"),
                name="Open B",
                organization_id="b",
                joining_mode=JoiningMode.OPEN,
            )
        }
    )
    user = _user("alice")
    with pytest.raises(AuthorizationError):
        await join_team(user, TeamId("open-b"), _deps(rebac, store))
    organization_onboarding.assert_awaited_once_with(user, rebac)
    assert rebac.has_permission_calls == [("alice", TeamPermission.CAN_JOIN, "open-b")]
    assert rebac.direct_relations == []


async def test_private_open_team_accepts_organization_member():
    from fred_core.teams.metadata_store import TeamVisibility

    rebac = CountingRebacEngine(granted_permissions={TeamPermission.CAN_JOIN})
    store = _FakeMetadataStore(
        {
            "private-open": TeamMetadata(
                id=TeamId("private-open"),
                name="Private open",
                visibility=TeamVisibility.PRIVATE,
                joining_mode=JoiningMode.OPEN,
            )
        }
    )
    result = await join_team(
        _user("alice"), TeamId("private-open"), _deps(rebac, store)
    )
    assert result.is_member
