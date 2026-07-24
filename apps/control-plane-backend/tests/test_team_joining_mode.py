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
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from control_plane_backend.teams.schemas import TeamNotOpenForJoiningError
from control_plane_backend.teams.service import join_team
from fred_core import (
    JoiningMode,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
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
        get_users_by_ids=cast(Any, lambda *_a, **_k: {}),
        search_users=cast(Any, lambda *_a, **_k: []),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


@pytest.mark.parametrize(
    "joining_mode",
    [JoiningMode.REQUEST_ONLY, JoiningMode.INVITE_ONLY, JoiningMode.CLOSED],
)
async def test_join_team_rejects_when_not_open(
    joining_mode: JoiningMode,
) -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {
            "guarded-team": TeamMetadata(
                id=TeamId("guarded-team"), name="Guarded", joining_mode=joining_mode
            )
        }
    )

    with pytest.raises(TeamNotOpenForJoiningError) as excinfo:
        await join_team(_user(), TeamId("guarded-team"), _deps(rebac, store))

    assert excinfo.value.joining_mode == joining_mode
    assert rebac.added_relations == []  # never writes when the gate fails


async def test_join_team_raises_not_found_for_unknown_team() -> None:
    from control_plane_backend.teams.schemas import TeamNotFoundError

    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await join_team(_user(), TeamId("ghost-team"), _deps(rebac, store))

    assert rebac.added_relations == []


async def test_join_team_grants_team_member_to_self_only_when_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {
            "open-team": TeamMetadata(
                id=TeamId("open-team"), name="Open", joining_mode=JoiningMode.OPEN
            )
        }
    )
    sentinel = object()

    async def _fake_get_team_by_id(user, team_id, deps, required_permissions=None):
        # join_team must delegate the final read to the standard getter
        # rather than building its own response shape.
        return sentinel

    monkeypatch.setattr(
        "control_plane_backend.teams.service.get_team_by_id", _fake_get_team_by_id
    )

    result = await join_team(_user("alice"), TeamId("open-team"), _deps(rebac, store))

    assert result is sentinel
    assert len(rebac.added_relations) == 1
    written = rebac.added_relations[0]
    assert written.subject == RebacReference(Resource.USER, "alice")
    assert written.relation == RelationType.TEAM_MEMBER
    assert written.resource == RebacReference(Resource.TEAM, "open-team")
