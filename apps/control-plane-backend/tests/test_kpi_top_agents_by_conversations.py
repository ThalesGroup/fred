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


def _top_response(agents: list[tuple[str, str, int]]) -> dict[str, Any]:
    """Phase-1 shape: (instance_id, instance_name, doc_count) per bucket."""
    return {
        "aggregations": {
            "by_agent": {
                "buckets": [
                    {
                        "key": instance_id,
                        "doc_count": count,
                        "latest_name": {
                            "hits": {
                                "hits": [
                                    {"_source": {"dims": {"agent_instance_name": name}}}
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


async def _run(store: _FakeStore) -> Any:
    return await query_top_agents_by_conversations(
        store,  # pyright: ignore[reportArgumentType]
        user=None,  # pyright: ignore[reportArgumentType]
        since=SINCE,
        until=UNTIL,
        request=None,  # pyright: ignore[reportArgumentType]
    )


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
    Keying by id keeps them apart; the colliding names get an id suffix so the
    two lines remain distinguishable in the chart."""
    store = _FakeStore(
        [
            _top_response(
                [("id-aaaa1111", "Support", 7), ("id-bbbb2222", "Support", 4)]
            ),
            _series_response(
                [("2026-08-01T00:00:00.000Z", {"id-aaaa1111": 7, "id-bbbb2222": 4})]
            ),
        ]
    )

    result = await _run(store)

    assert result.series == ["Support (id-aaaa1)", "Support (id-bbbb2)"]
    assert result.rows[-1].values == {
        "Support (id-aaaa1)": 7.0,
        "Support (id-bbbb2)": 4.0,
    }


@pytest.mark.asyncio
async def test_unique_names_are_not_suffixed() -> None:
    """The id suffix is a collision escape hatch, not the normal display."""
    store = _FakeStore(
        [
            _top_response([("id-a", "Alpha", 2), ("id-b", "Beta", 1)]),
            _series_response([("2026-08-01T00:00:00.000Z", {"id-a": 2, "id-b": 1})]),
        ]
    )

    result = await _run(store)

    assert result.series == ["Alpha", "Beta"]


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
