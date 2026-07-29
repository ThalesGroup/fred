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

"""Regression coverage for #2065: `_enrich_teams_with_membership` must resolve
admins/members without the `2 * len(team_ids)` per-team `ListUsers` fan-out
that produced 4-9s `/frontend/bootstrap` latency at S3NS's 99-team production
scale.

This file originally asserted a *constant* number of bulk `list_relations`
calls (4, one per team role relation, regardless of team count). That design
does not work against a real OpenFGA store: confirmed live against OpenFGA
v1.12.1 and v1.15.1, a `list_relations` Read whose object is type-only (no id) and whose
`user` is also empty is rejected with HTTP 400 ("the 'tuple_key' field was
provided but the object type field is required and both the object id and
user cannot be empty") — there is no exact "any user" subject to anchor
"every team_admin/editor/analyst/member tuple across every team" on. The
corrected design (`_bulk_team_membership`) is one exact
`list_direct_relations(team:<id>)` per team — O(team_count) round-trips, not
O(1), but each one a valid, already-used Read shape, and still a `Read` (not
`ListUsers`) per team, i.e. still half the round-trips of the original
`2 * len(team_ids)` fan-out this replaced.

No prior test exercised either the real fan-out or the real OpenFGA
constraint: every earlier `_enrich_teams_with_membership` test monkeypatches
`_get_team_users_by_relation`/`_bulk_team_membership` away entirely, so a
regression back to `ListUsers` per team — or back to the invalid bulk
`list_relations` shape — would pass silently. This file wires a real,
call-counting `RebacEngine` instead.
"""

from __future__ import annotations

from typing import Any, Iterable, cast
from unittest.mock import MagicMock

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.service import _enrich_teams_with_membership
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata


def _fake_deps() -> TeamServiceDependencies:
    mock_config = MagicMock()
    mock_config.app.default_team_max_resources_storage_size = 5368709120
    mock_config.app.personal_max_resources_storage_size = 5368709120
    mock_config.scheduler.enabled = False

    async def _fake_get_users_by_ids(_ids: Iterable[str]) -> dict[str, Any]:
        return {}

    async def _fake_search_users(_query: str) -> list[Any]:
        return []

    class _FakeContentStore:
        def get_presigned_url(self, key: str, expires=None) -> str:
            raise AssertionError("no banner in this test")

    return TeamServiceDependencies(
        configuration=mock_config,
        rebac=cast(Any, object()),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, object),
        get_content_store=lambda: cast(Any, _FakeContentStore()),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, _fake_get_users_by_ids),
        search_users=cast(Any, _fake_search_users),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _input: object()),
    )


def _teams(count: int) -> list[TeamMetadata]:
    return [
        TeamMetadata(id=TeamId(f"team-{i}"), name=f"Team {i}") for i in range(count)
    ]


def _membership_tuples(team_ids: list[str]) -> list[Relation]:
    """One admin + one plain member per team, so admins/member_count are
    non-trivial (not just "everything empty, trivially bounded")."""
    tuples: list[Relation] = []
    for team_id in team_ids:
        tuples.append(
            Relation(
                subject=RebacReference(Resource.USER, f"{team_id}-admin"),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
        tuples.append(
            Relation(
                subject=RebacReference(Resource.USER, f"{team_id}-member"),
                relation=RelationType.TEAM_MEMBER,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
    return tuples


@pytest.mark.asyncio
@pytest.mark.parametrize("team_count", [3, 50])
async def test_enrich_teams_with_membership_uses_one_exact_read_per_team(
    team_count: int,
) -> None:
    teams_metadata = _teams(team_count)
    team_ids = [str(metadata.id) for metadata in teams_metadata]
    engine = CountingRebacEngine(direct_relations=_membership_tuples(team_ids))

    teams = await _enrich_teams_with_membership(
        engine,
        user=cast(Any, type("User", (), {"uid": "someone"})()),
        teams_metadata=teams_metadata,
        deps=_fake_deps(),
    )

    # #2065 correction: never `list_relations` (the shape OpenFGA rejects for
    # this "any user, many teams" case) — exactly one exact
    # `list_direct_relations(team:<id>)` per team instead.
    assert engine.list_relations_calls == []
    assert len(engine.list_direct_relations_calls) == team_count
    assert {ref.id for ref, _subject in engine.list_direct_relations_calls} == set(
        team_ids
    )
    assert engine.lookup_subjects_calls == 0
    assert engine.lookup_resources_calls == 0

    assert len(teams) == team_count
    for team in teams:
        assert team.member_count == 2
        assert {admin.id for admin in team.admins} == {f"{team.id}-admin"}
