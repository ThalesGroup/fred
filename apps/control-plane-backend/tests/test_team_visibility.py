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

"""TEAM-10 (FRED-TEAM-CONFIG-RFC.md §5.1.2): team visibility gates
marketplace discoverability (the ReBAC `public` relation), independent of
`joining_mode`. `_list_teams` is the lazy backfill/correction point — on
every listing, every `PUBLIC` team must be (re-)granted `public` and every
`PRIVATE` team must have it revoked, so a team that was flipped to private
after already being granted `public` actually loses non-member read access.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from control_plane_backend.teams.service import list_all_teams_unfiltered
from fred_core import JoiningMode, KeycloakUser, RebacDisabledResult, TeamVisibility
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata

pytestmark = pytest.mark.asyncio


class _FakeRebac:
    def __init__(self) -> None:
        self.granted_team_ids: list[str] = []
        self.revoked_team_ids: list[str] = []

    async def ensure_team_public_relations(self, team_ids) -> str | None:
        self.granted_team_ids.extend(team_ids)
        return None

    async def revoke_team_public_relations(self, team_ids) -> str | None:
        self.revoked_team_ids.extend(team_ids)
        return None

    async def lookup_subjects(self, *_args, **_kwargs):
        return RebacDisabledResult()

    async def list_relations(self, *_args, **_kwargs):
        # Backs `ensure_team_public_relations`/`revoke_team_public_relations`'s
        # existence-check read (never the organization relation — #2065 removed
        # that call from `_list_teams` entirely).
        return RebacDisabledResult()

    async def list_direct_relations(self, *_args, **_kwargs):
        # #2065: `_bulk_team_membership` now reads one exact object per team
        # (`list_direct_relations`) instead of bulk `list_relations` — same
        # disabled-reads stance.
        return RebacDisabledResult()


class _FakeMetadataStore:
    def __init__(self, teams: list[TeamMetadata]) -> None:
        self.teams = teams

    async def list_all(self, session=None) -> list[TeamMetadata]:
        return self.teams


def _user(uid: str = "alice") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


async def _no_users_by_ids(*_args, **_kwargs) -> dict:
    return {}


def _deps(rebac: _FakeRebac, store: _FakeMetadataStore):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, _no_users_by_ids),
        search_users=cast(Any, lambda *_a, **_k: []),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


async def test_list_teams_grants_public_and_revokes_private() -> None:
    store = _FakeMetadataStore(
        [
            TeamMetadata(
                id=TeamId("public-team"),
                name="Public",
                joining_mode=JoiningMode.INVITE_ONLY,
                visibility=TeamVisibility.PUBLIC,
            ),
            TeamMetadata(
                id=TeamId("private-team"),
                name="Private",
                joining_mode=JoiningMode.INVITE_ONLY,
                visibility=TeamVisibility.PRIVATE,
            ),
        ]
    )
    rebac = _FakeRebac()

    teams = await list_all_teams_unfiltered(_user(), _deps(rebac, store))

    assert rebac.granted_team_ids == ["public-team"]
    assert rebac.revoked_team_ids == ["private-team"]
    by_id = {str(team.id): team for team in teams}
    assert by_id["public-team"].visibility == TeamVisibility.PUBLIC
    assert by_id["private-team"].visibility == TeamVisibility.PRIVATE


async def test_list_teams_with_no_teams_calls_neither_grant_nor_revoke() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore([])

    await list_all_teams_unfiltered(_user(), _deps(rebac, store))

    assert rebac.granted_team_ids == []
    assert rebac.revoked_team_ids == []
