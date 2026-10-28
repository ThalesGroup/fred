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

from __future__ import annotations

from typing import Any, cast

import pytest
from _kpi_test_doubles import (
    SINCE,
    TEAM_TERMS,
    UNTIL,
    USER,
    FakeKpiStore,
    periods,
    value,
)
from control_plane_backend.kpi.presets import analytics_teams
from control_plane_backend.kpi.presets.analytics_common import TEAM_SPACE
from control_plane_backend.kpi.presets.analytics_teams import query_analytics_teams
from fred_core.common import TeamId


def _period(
    teams: list[tuple[str, int, int]], team: int, personal: int
) -> dict[str, Any]:
    return {
        "by_scope": {
            "scopes": {
                "buckets": [
                    {"key": "team", "doc_count": team},
                    {"key": "personal", "doc_count": personal},
                ]
            }
        },
        "team_turns": {
            "teams": {
                "buckets": [
                    {"key": t, "doc_count": messages, "users": value(users)}
                    for t, messages, users in teams
                ]
            }
        },
    }


@pytest.fixture(autouse=True)
def names(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _names(_request: Any, team_ids: list[str]) -> dict[str, str]:
        return {t: t.upper() for t in team_ids}

    monkeypatch.setattr(analytics_teams, "resolve_team_names", _names)


def _response() -> dict[str, Any]:
    return periods(
        _period([("a", 50, 5), ("b", 10, 2)], team=60, personal=40),
        _period([("a", 25, 4)], team=30, personal=70),
    )


@pytest.mark.asyncio
async def test_rows_compare_messages_with_the_previous_period() -> None:
    store = FakeKpiStore(periods=_response())
    result = await query_analytics_teams(
        cast(Any, store), user=USER, since=SINCE, until=UNTIL, request=cast(Any, None)
    )
    team_turns = store.body()["aggs"]["periods"]["aggs"]["team_turns"]
    assert TEAM_SPACE in team_turns["filter"]["bool"]["filter"]
    assert [
        (r.team_id, r.name, r.active_members, r.messages, r.messages_previous)
        for r in result.rows
    ] == [
        ("a", "A", 5, 50, 25),
        ("b", "B", 2, 10, 0),
    ]
    assert result.active_teams.current == 2 and result.active_teams.previous == 1
    assert result.team_share is not None
    assert result.team_share.current == pytest.approx(0.6)
    assert result.team_share.previous == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_team_scope_has_no_collective_split() -> None:
    store = FakeKpiStore(periods=_response())
    result = await query_analytics_teams(
        cast(Any, store),
        user=USER,
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("a"), TeamId("b")),
    )
    assert TEAM_TERMS in store.filters()
    assert result.team_share is None and result.personal_conversations is None
    assert len(result.rows) == 2
