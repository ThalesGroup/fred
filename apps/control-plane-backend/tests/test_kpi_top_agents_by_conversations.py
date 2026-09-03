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
`top_agents_by_conversations` series-assembly regressions.

Both bugs covered here made the drawn lines disagree with the phase-1 ranking
that chose them:

1. Phase 2's per-bucket `by_agent` terms agg had no `include`, so every date
   bucket independently returned *its own* top N. A globally-top agent that
   lost one bucket to N busier ones silently dropped that bucket's turns.
2. Series were keyed by `agent_instance_name`, so two distinct instances
   sharing a name were merged into one line whose counts were the sum of both.

Only the series assembly is under test — the OpenSearch client is faked, since
the aggregation itself is the store's contract, not this preset's.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from control_plane_backend.kpi.presets import (
    top_agents_by_conversations as preset_module,
)
from control_plane_backend.kpi.presets.top_agents_by_conversations import (
    TOP_N,
    query_top_agents_by_conversations,
)

SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)
UNTIL = SINCE + timedelta(days=3)


class _FakeClient:
    """Returns the phase-1 then the phase-2 response, recording both bodies."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.bodies: list[dict[str, Any]] = []

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        del index
        self.bodies.append(body)
        return self._responses.pop(0)


class _FakeStore:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.client = _FakeClient(responses)
        self.index = "kpi-test"


def _top_response(
    agents: list[tuple[str, str, int]],
    teams: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Phase-1 shape: (instance_id, instance_name, doc_count) per bucket.

    `teams` maps instance_id → the team_id its latest event carried; an
    instance left out of it stands in for an event emitted without one.
    """
    teams = teams or {}
    return {
        "aggregations": {
            "by_agent": {
                "buckets": [
                    {
                        "key": instance_id,
                        "doc_count": count,
                        "latest_dims": {
                            "hits": {
                                "hits": [
                                    {
                                        "_source": {
                                            "dims": {
                                                "agent_instance_name": name,
                                                **(
                                                    {"team_id": teams[instance_id]}
                                                    if instance_id in teams
                                                    else {}
                                                ),
                                            }
                                        }
                                    }
                                ]
                            }
                        },
                    }
                    for instance_id, name, count in agents
                ]
            }
        }
    }


def _series_response(buckets: list[tuple[str, dict[str, int]]]) -> dict[str, Any]:
    """Phase-2 shape: (bucket timestamp, {instance_id: doc_count}) per bucket."""
    return {
        "aggregations": {
            "by_time": {
                "buckets": [
                    {
                        "key_as_string": key_as_string,
                        "by_agent": {
                            "buckets": [
                                {"key": instance_id, "doc_count": count}
                                for instance_id, count in per_agent.items()
                            ]
                        },
                    }
                    for key_as_string, per_agent in buckets
                ]
            }
        }
    }


async def _run(store: _FakeStore, team_id: str | None = None) -> Any:
    return await query_top_agents_by_conversations(
        store,  # pyright: ignore[reportArgumentType]
        user=None,  # pyright: ignore[reportArgumentType]
        since=SINCE,
        until=UNTIL,
        request=None,  # pyright: ignore[reportArgumentType]
        team_id=team_id,  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture(autouse=True)
def _team_names(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Stand in for the team_metadata_store lookup the preset does for labels.

    The real helper resolves through a FastAPI request; these tests fake the
    OpenSearch client only, so the registry is faked here in the same spirit.
    """
    registry = {"team-swift": "Swiftpost", "team-lab": "Fredlab"}

    async def _fake(_request: Any, team_ids: list[str]) -> dict[str, str]:
        return {tid: registry.get(tid, tid) for tid in team_ids}

    monkeypatch.setattr(preset_module, "resolve_team_names", _fake)
    return registry


@pytest.mark.asyncio
async def test_series_query_is_pinned_to_the_phase_one_winners() -> None:
    """Without `include`, each date bucket returns its own top N and a
    globally-top agent can be crowded out of a bucket it had turns in."""
    store = _FakeStore(
        [
            _top_response([("id-a", "Alpha", 5), ("id-b", "Beta", 3)]),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 5, "id-b": 3})]),
        ]
    )

    await _run(store)

    series_body = store.client.bodies[1]
    terms = series_body["aggs"]["by_time"]["aggs"]["by_agent"]["terms"]
    assert terms["include"] == ["id-a", "id-b"]
    assert terms["size"] == TOP_N


@pytest.mark.asyncio
async def test_instances_sharing_a_name_stay_separate_series() -> None:
    """Keying by name merged two instances into one line summing both counts.
    Keying by id keeps them apart, and the owning team is what tells the two
    lines apart in the chart."""
    store = _FakeStore(
        [
            _top_response(
                [("id-aaaa1111", "Support", 7), ("id-bbbb2222", "Support", 4)],
                teams={"id-aaaa1111": "team-swift", "id-bbbb2222": "team-lab"},
            ),
            _series_response(
                [("2026-08-01T00:00:00.000Z", {"id-aaaa1111": 7, "id-bbbb2222": 4})]
            ),
        ]
    )

    result = await _run(store)

    assert result.series == ["Support - Swiftpost", "Support - Fredlab"]
    assert result.rows[-1].values == {
        "Support - Swiftpost": 7.0,
        "Support - Fredlab": 4.0,
    }


@pytest.mark.asyncio
async def test_same_name_inside_one_team_keeps_the_id_suffix() -> None:
    """The team cannot separate two same-named instances that share it, so the
    id suffix survives as the residual escape hatch."""
    store = _FakeStore(
        [
            _top_response(
                [("id-aaaa1111", "Support", 7), ("id-bbbb2222", "Support", 4)],
                teams={"id-aaaa1111": "team-swift", "id-bbbb2222": "team-swift"},
            ),
            _series_response(
                [("2026-08-01T00:00:00.000Z", {"id-aaaa1111": 7, "id-bbbb2222": 4})]
            ),
        ]
    )

    result = await _run(store)

    assert result.series == [
        "Support - Swiftpost (id-aaaa1)",
        "Support - Swiftpost (id-bbbb2)",
    ]


@pytest.mark.asyncio
async def test_unique_names_are_still_qualified_by_their_team() -> None:
    """The team suffix is the normal display, not a collision escape hatch —
    a cross-team ranking is unreadable without knowing whose agent is whose."""
    store = _FakeStore(
        [
            _top_response(
                [("id-a", "Alpha", 2), ("id-b", "Beta", 1)],
                teams={"id-a": "team-swift", "id-b": "team-lab"},
            ),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 2, "id-b": 1})]),
        ]
    )

    result = await _run(store)

    assert result.series == ["Alpha - Swiftpost", "Beta - Fredlab"]


@pytest.mark.asyncio
async def test_team_scoped_request_keeps_bare_names() -> None:
    """Every series in a team-scoped chart belongs to that team, so the suffix
    would just repeat the filter the caller already set."""
    store = _FakeStore(
        [
            _top_response(
                [("id-a", "Alpha", 2), ("id-b", "Beta", 1)],
                teams={"id-a": "team-swift", "id-b": "team-swift"},
            ),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 2, "id-b": 1})]),
        ]
    )

    result = await _run(store, team_id="team-swift")

    assert result.series == ["Alpha", "Beta"]


@pytest.mark.asyncio
async def test_event_without_a_team_id_falls_back_to_the_bare_name() -> None:
    store = _FakeStore(
        [
            _top_response(
                [("id-a", "Alpha", 2), ("id-b", "Beta", 1)],
                teams={"id-a": "team-swift"},
            ),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 2, "id-b": 1})]),
        ]
    )

    result = await _run(store)

    assert result.series == ["Alpha - Swiftpost", "Beta"]


@pytest.mark.asyncio
async def test_deleted_team_falls_back_to_its_id() -> None:
    """A team whose registry row is gone still labels its agent — the id is a
    worse label than a name, but better than dropping the line."""
    store = _FakeStore(
        [
            _top_response([("id-a", "Alpha", 2)], teams={"id-a": "team-ghost"}),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 2})]),
        ]
    )

    result = await _run(store)

    assert result.series == ["Alpha - team-ghost"]


@pytest.mark.asyncio
async def test_running_totals_accumulate_across_buckets() -> None:
    """Each point is the cumulative turn count up to that bucket, and a bucket
    an agent is absent from carries its previous total forward unchanged."""
    store = _FakeStore(
        [
            _top_response([("id-a", "Alpha", 5), ("id-b", "Beta", 2)]),
            _series_response(
                [
                    ("2026-08-01T00:00:00.000Z", {"id-a": 3, "id-b": 2}),
                    ("2026-08-02T00:00:00.000Z", {"id-a": 2}),
                ]
            ),
        ]
    )

    result = await _run(store)

    assert [row.values for row in result.rows] == [
        {"Alpha": 3.0, "Beta": 2.0},
        {"Alpha": 5.0, "Beta": 2.0},
    ]


@pytest.mark.asyncio
async def test_no_turns_returns_empty_without_a_second_query() -> None:
    store = _FakeStore([_top_response([])])

    result = await _run(store)

    assert result.rows == []
    assert result.series == []
    assert len(store.client.bodies) == 1
