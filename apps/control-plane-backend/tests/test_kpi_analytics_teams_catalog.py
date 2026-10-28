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

"""`analytics_teams_catalog`: teams for the scope selector, observer-gated."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.kpi.presets import analytics_teams_catalog as catalog
from control_plane_backend.kpi.presets.analytics_teams_catalog import (
    ANALYTICS_TEAMS_CATALOG_PRESET,
    query_analytics_teams_catalog,
)
from control_plane_backend.teams import service as team_service
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata

_SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2026, 10, 27, tzinfo=timezone.utc)


def _team(team_id: str, name: str) -> TeamMetadata:
    return TeamMetadata(id=TeamId(team_id), name=name)


@pytest.mark.asyncio
async def test_catalog_lists_real_teams_with_member_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [
        _team("t-b", "beta"),
        _team("personal-u1", "personal"),
        _team("t-a", "Alpha"),
        _team("t-c", "Gamma"),
    ]
    store = SimpleNamespace(list_all=lambda: _async(teams))
    rebac = object()
    monkeypatch.setattr(
        catalog,
        "get_application_container",
        lambda request: SimpleNamespace(
            get_team_metadata_store=lambda: store, get_rebac_engine=lambda: rebac
        ),
    )
    seen: list[list[TeamId]] = []

    async def _bulk(engine: Any, team_ids: list[TeamId], user_id: str):
        assert engine is rebac
        seen.append(team_ids)
        members = {
            TeamId("t-a"): {"u1", "u2", "u3"},
            TeamId("t-b"): {"u1"},
            TeamId("t-c"): set(),
        }
        return {}, members, {}, {}

    monkeypatch.setattr(team_service, "_bulk_team_membership", _bulk)

    result = await query_analytics_teams_catalog(
        cast(Any, None),
        user=cast(Any, None),
        since=_SINCE,
        until=_UNTIL,
        request=cast(Any, None),
    )

    # Personal spaces are excluded; small teams stay listed.
    assert [(r.team_id, r.name, r.member_count) for r in result.rows] == [
        ("t-a", "Alpha", 3),
        ("t-b", "beta", 1),
        ("t-c", "Gamma", 0),
    ]
    assert len(seen) == 1 and TeamId("personal-u1") not in seen[0]

    # Scoped to a team (a team admin's own): only that row, only its members read.
    scoped = await query_analytics_teams_catalog(
        cast(Any, None),
        user=cast(Any, None),
        since=_SINCE,
        until=_UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("t-a"),),
    )
    assert [(r.team_id, r.member_count) for r in scoped.rows] == [("t-a", 3)]
    assert seen[-1] == [TeamId("t-a")]


def test_catalog_is_a_scoped_preset() -> None:
    """The router checks can_observe_platform, or can_read_analytics per team."""
    assert ANALYTICS_TEAMS_CATALOG_PRESET.team_scopable is True
    assert ANALYTICS_TEAMS_CATALOG_PRESET.self_scoped is False


async def _async(value: Any) -> Any:
    return value
