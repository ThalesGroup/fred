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

"""#2065 follow-up: `require_team_access` must authorize a team without ever
projecting `Team`/`TeamWithPermissions` — no membership enrichment, no
14-permission UI projection, no role resolution. Budget for a collaborative
team: zero `list_relations` (the `organization -> team` edge is established
once at team creation and repaired only on cold paths — never read or
repaired by this per-request path, see `RebacEngine.
check_user_team_permissions_or_raise`) + 1 `has_permission` `Check` per
requested permission. A personal space owned by the caller: zero OpenFGA
calls.

This file wires a real, call-counting `RebacEngine` (same pattern as
`test_teams_bulk_membership_call_count.py`) rather than mocking
`_validate_team_and_check_permission` away, so a regression back to the full
`get_team_by_id` projection (14 `Check`s, 4 `list_relations`, 3
`lookup_subjects`) would fail these tests instead of passing silently.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from _rebac_test_doubles import CountingRebacEngine, assert_no_openfga_calls
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import TeamNotFoundError
from control_plane_backend.teams.service import require_team_access
from fred_core import (
    AuthorizationError,
    KeycloakUser,
    TeamPermission,
)
from fred_core.common import TeamId, personal_team_id
from fred_core.teams.metadata_store import TeamMetadata


class _FakeMetadataStore:
    def __init__(self, teams: dict[str, TeamMetadata]) -> None:
        self._teams = teams

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata | None:
        return self._teams.get(str(team_id))


def _user(uid: str = "u") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=["viewer"], email=None)


def _deps(
    rebac: CountingRebacEngine, metadata_store: _FakeMetadataStore
) -> TeamServiceDependencies:
    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=lambda: cast(Any, metadata_store),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, lambda *_a, **_k: {}),
        search_users=cast(Any, lambda *_a, **_k: []),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


@pytest.mark.asyncio
async def test_collaborative_team_authorized_returns_canonical_team_id() -> None:
    """1: existing, authorized collaborative team — 0 Read + 1 Check, no more."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions={TeamPermission.CAN_READ},
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    resolved = await require_team_access(
        _user(), TeamId("fredlab"), _deps(engine, store)
    )

    assert resolved == TeamId("fredlab")
    assert engine.list_relations_calls == []
    assert engine.has_permission_calls == [("u", TeamPermission.CAN_READ, "fredlab")]
    assert engine.add_relations_calls == []  # edge already existed: zero writes
    assert engine.lookup_resources_calls == 0
    assert engine.lookup_subjects_calls == 0


@pytest.mark.asyncio
async def test_unknown_collaborative_team_raises_not_found() -> None:
    """2: unknown team_id — 404 before any OpenFGA call is made."""
    engine = CountingRebacEngine(org_linked_team_ids=set(), granted_permissions=set())
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await require_team_access(_user(), TeamId("ghost"), _deps(engine, store))

    assert engine.list_relations_calls == []
    assert engine.has_permission_calls == []


@pytest.mark.asyncio
async def test_permission_denied_raises_authorization_error() -> None:
    """3: team exists, but the caller lacks the requested permission."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"}, granted_permissions=set()
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    with pytest.raises(AuthorizationError):
        await require_team_access(
            _user(),
            TeamId("fredlab"),
            _deps(engine, store),
            required_permissions=[TeamPermission.CAN_UPDATE_AGENTS],
        )

    assert engine.has_permission_calls == [
        ("u", TeamPermission.CAN_UPDATE_AGENTS, "fredlab")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id_arg", ["personal", None])
async def test_own_personal_space_zero_openfga_calls(team_id_arg: str | None) -> None:
    """4: the caller's own personal space — zero OpenFGA calls, canonical id
    returned regardless of whether the literal `"personal"` alias or the
    already-canonical `personal-<uid>` form was passed."""
    user = _user("alice")
    team_id = TeamId(team_id_arg) if team_id_arg else personal_team_id(user.uid)
    engine = CountingRebacEngine()
    store = _FakeMetadataStore({})

    resolved = await require_team_access(user, team_id, _deps(engine, store))

    assert resolved == personal_team_id("alice")
    assert_no_openfga_calls(engine)


@pytest.mark.asyncio
async def test_other_users_personal_space_denied_same_as_before() -> None:
    """5: another user's personal space never matches the short-circuit and
    falls through to the collaborative path, where the metadata store holds no
    row for it — same 404 `get_team_by_id` produces today, no OpenFGA call
    ever attempted."""
    engine = CountingRebacEngine()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await require_team_access(
            _user("alice"), personal_team_id("bob"), _deps(engine, store)
        )

    assert_no_openfga_calls(engine)


@pytest.mark.asyncio
async def test_multiple_required_permissions_checked_independently() -> None:
    """6 + 8: several required permissions run one Check each — call count
    tracks the requested list, never the full 14-entry `TeamPermission` set."""
    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions={
            TeamPermission.CAN_READ,
            TeamPermission.CAN_UPDATE_RESOURCES,
        },
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )

    resolved = await require_team_access(
        _user(),
        TeamId("fredlab"),
        _deps(engine, store),
        required_permissions=[
            TeamPermission.CAN_READ,
            TeamPermission.CAN_UPDATE_RESOURCES,
        ],
    )

    assert resolved == TeamId("fredlab")
    # Zero Read regardless of permission count — the org edge is never
    # consulted here (#2065).
    assert engine.list_relations_calls == []
    # Exactly one Check per requested permission — not `len(list(TeamPermission))`.
    assert len(engine.has_permission_calls) == 2
    assert {perm for _uid, perm, _rid in engine.has_permission_calls} == {
        TeamPermission.CAN_READ,
        TeamPermission.CAN_UPDATE_RESOURCES,
    }


@pytest.mark.asyncio
async def test_product_route_no_longer_triggers_full_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7: a representative product route (`GET /teams/{id}/agent-instances`)
    keeps its functional response while the OpenFGA call budget collapses to
    0 Read + 1 Check — no membership enrichment, no 14-permission batch, no
    role resolution `lookup_subjects` fan-out."""
    from types import SimpleNamespace

    from control_plane_backend.product import api as product_api

    engine = CountingRebacEngine(
        org_linked_team_ids={"fredlab"},
        granted_permissions={TeamPermission.CAN_USE_TEAM_AGENTS},
    )
    store = _FakeMetadataStore(
        {"fredlab": TeamMetadata(id=TeamId("fredlab"), name="Fredlab")}
    )
    team_deps = _deps(engine, store)

    expected_instances = ["sentinel-instance-list"]
    list_instances = AsyncMock(return_value=expected_instances)
    monkeypatch.setattr(product_api, "list_managed_agent_instances", list_instances)

    deps = cast(Any, SimpleNamespace(team_dependencies=team_deps))
    result = await product_api.get_team_agent_instances(
        TeamId("fredlab"), deps, _user()
    )

    assert result == expected_instances
    list_instances.assert_awaited_once_with(TeamId("fredlab"), deps)
    assert engine.list_relations_calls == []
    assert engine.has_permission_calls == [
        ("u", TeamPermission.CAN_USE_TEAM_AGENTS, "fredlab")
    ]
    assert engine.lookup_subjects_calls == 0
    assert engine.lookup_resources_calls == 0
