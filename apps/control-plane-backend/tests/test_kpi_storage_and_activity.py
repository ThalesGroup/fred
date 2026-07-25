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

"""
`storage_by_team` and `team_activity_summary` (OBSERV-02 v3, §2.9/§2.5).

`storage_by_team` covers the three-way quota resolution (per-team override >
platform config default > unlimited) — the one piece of real business logic
in that preset, everything else is a direct field read. `team_activity_summary`
covers its one behavioral rule: team_id is required, unlike every other
team_scopable preset.
"""

# pyright: reportArgumentType=false
# ^ this suite passes `store=None`/`request=None` — neither preset under test
#   uses them (storage_by_team is Postgres-only, and the 400-before-any-query
#   validation in team_activity_summary never reaches its store/request use)
#   — same convention as test_capability_enablement_1980.py.
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from control_plane_backend.kpi.presets import storage_by_team
from control_plane_backend.kpi.presets.storage_by_team import query_storage_by_team
from control_plane_backend.kpi.presets.team_activity_summary import (
    query_team_activity_summary,
)
from fastapi import HTTPException
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u1", roles=["viewer"], email=None)


def _team(
    team_id: str,
    *,
    used: int | None,
    quota: int | None,
) -> TeamMetadata:
    return TeamMetadata(
        id=TeamId(team_id),
        name=f"Team {team_id}",
        current_resources_storage_size=used,
        max_resources_storage_size=quota,
    )


class _FakeMetadataStore:
    def __init__(self, teams: list[TeamMetadata]) -> None:
        self._by_id = {str(t.id): t for t in teams}

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata | None:
        return self._by_id.get(str(team_id))

    async def list_all(self) -> list[TeamMetadata]:
        return list(self._by_id.values())


def _container(
    teams: list[TeamMetadata], *, default_quota: int | None
) -> SimpleNamespace:
    return SimpleNamespace(
        get_team_metadata_store=lambda: _FakeMetadataStore(teams),
        configuration=SimpleNamespace(
            app=SimpleNamespace(default_team_max_resources_storage_size=default_quota)
        ),
    )


_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2026, 1, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_storage_uses_per_team_override_over_platform_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [_team("t1", used=500, quota=1000)]
    monkeypatch.setattr(
        storage_by_team,
        "get_application_container",
        lambda request: _container(teams, default_quota=99999),
    )

    result = await query_storage_by_team(
        store=None,  # not used by this preset
        user=_user(),
        since=_SINCE,
        until=_UNTIL,
        request=None,
        team_id=TeamId("t1"),
    )

    assert result.rows == [
        _expected_row("t1", "Team t1", used=500, quota=1000),
    ]


@pytest.mark.asyncio
async def test_storage_falls_back_to_platform_default_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [_team("t1", used=500, quota=None)]
    monkeypatch.setattr(
        storage_by_team,
        "get_application_container",
        lambda request: _container(teams, default_quota=99999),
    )

    result = await query_storage_by_team(
        store=None,
        user=_user(),
        since=_SINCE,
        until=_UNTIL,
        request=None,
        team_id=TeamId("t1"),
    )

    assert result.rows[0].quota_bytes == 99999


@pytest.mark.asyncio
async def test_storage_unlimited_when_neither_override_nor_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [_team("t1", used=500, quota=None)]
    monkeypatch.setattr(
        storage_by_team,
        "get_application_container",
        lambda request: _container(teams, default_quota=None),
    )

    result = await query_storage_by_team(
        store=None,
        user=_user(),
        since=_SINCE,
        until=_UNTIL,
        request=None,
        team_id=TeamId("t1"),
    )

    assert result.rows[0].quota_bytes is None


@pytest.mark.asyncio
async def test_storage_platform_wide_ranks_by_usage_descending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [
        _team("small", used=100, quota=None),
        _team("big", used=900, quota=None),
        _team("medium", used=500, quota=None),
    ]
    monkeypatch.setattr(
        storage_by_team,
        "get_application_container",
        lambda request: _container(teams, default_quota=None),
    )

    result = await query_storage_by_team(
        store=None,
        user=_user(),
        since=_SINCE,
        until=_UNTIL,
        request=None,
        team_id=None,
    )

    assert [row.team_id for row in result.rows] == ["big", "medium", "small"]


@pytest.mark.asyncio
async def test_storage_unknown_team_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        storage_by_team,
        "get_application_container",
        lambda request: _container([], default_quota=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_storage_by_team(
            store=None,
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=None,
            team_id=TeamId("ghost"),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_team_activity_summary_requires_team_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await query_team_activity_summary(
            store=None,
            user=_user(),
            since=_SINCE,
            until=_UNTIL,
            request=None,
            team_id=None,
        )
    assert exc_info.value.status_code == 400


def _expected_row(team_id: str, label: str, *, used: int, quota: int | None):
    from control_plane_backend.kpi.presets.common import TeamStorageRow

    return TeamStorageRow(
        team_id=team_id, label=label, used_bytes=used, quota_bytes=quota
    )
