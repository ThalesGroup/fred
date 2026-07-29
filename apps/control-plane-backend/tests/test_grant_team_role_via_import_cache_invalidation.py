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

"""PR #2160 review finding (Codex, P2): `_grant_team_role_via_import` writes a
team-scoped role directly via `RebacEngine.add_relation`, bypassing
`teams.service._add_team_member_relation` by design (see its docstring). That
also meant it bypassed `invalidate_team_relations_cache` (#2148) — a bundle
import could report success while `/teams`/`/frontend/bootstrap` kept serving
the pre-import membership for up to the cache's 45s TTL. This test proves the
fix: a team's cached relations are invalidated by an import-time grant."""

from __future__ import annotations

from typing import cast

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.import_export.importer import _grant_team_role_via_import
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import _get_team_relations_cached
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.common import TeamId


@pytest.mark.asyncio
async def test_grant_team_role_via_import_invalidates_team_relations_cache() -> None:
    team_id = TeamId("team-import-1")
    engine = CountingRebacEngine(
        direct_relations=[
            Relation(
                subject=RebacReference(Resource.USER, "existing-admin"),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        ]
    )

    # Warm the cache the same way a `/teams`/`/frontend/bootstrap` load
    # would, before the import runs.
    warm = await _get_team_relations_cached(engine, team_id)
    assert {rel.subject.id for rel in cast(list[Relation], warm)} == {"existing-admin"}
    assert len(engine.list_direct_relations_calls) == 1

    await _grant_team_role_via_import(
        engine, "new-member", UserTeamRelation.TEAM_MEMBER, team_id
    )

    # Without invalidation, this would still be served from the 45s-TTL
    # cache and would not see "new-member" at all.
    refreshed = await _get_team_relations_cached(engine, team_id)
    assert len(engine.list_direct_relations_calls) == 2, (
        "import-time grant must invalidate the team's cached relations"
    )
    assert {rel.subject.id for rel in cast(list[Relation], refreshed)} == {
        "existing-admin",
        "new-member",
    }
