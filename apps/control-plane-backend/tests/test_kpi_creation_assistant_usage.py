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

"""Creation assistant tokens count in every token-usage preset, never in turn counts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from control_plane_backend.kpi.presets.common import (
    BY_AGENT_SCOPE_FILTER,
    CREATION_ASSISTANT_ANSWERED_FILTER,
    CREATION_ASSISTANT_LABEL,
    CREATION_ASSISTANT_METRIC,
    TOKEN_USAGE_FILTER,
    TURN_COMPLETED_METRIC,
)
from control_plane_backend.kpi.presets.creation_assistant_usage import (
    query_creation_assistant_usage,
)
from control_plane_backend.kpi.presets.messages_over_time import (
    query_messages_over_time,
)
from control_plane_backend.kpi.presets.token_usage_by_agent import (
    query_token_usage_by_agent,
)
from control_plane_backend.kpi.presets.token_usage_by_model import (
    query_token_usage_by_model,
)
from control_plane_backend.kpi.presets.token_usage_over_time import (
    query_token_usage_over_time,
)
from control_plane_backend.kpi.presets.user_token_usage_by_agent import (
    query_user_token_usage_by_agent,
)
from control_plane_backend.kpi.presets.user_token_usage_by_model import (
    query_user_token_usage_by_model,
)
from control_plane_backend.kpi.presets.user_token_usage_over_time import (
    query_user_token_usage_over_time,
)
from fred_core import KeycloakUser


class _Store:
    index = "kpi-events"

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self._response = response or {}
        self.client = self

    def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        del index
        self.bodies.append(body)
        return self._response


_USER = KeycloakUser(uid="alice", username="alice", roles=[], email=None)
_WINDOW = {
    "since": datetime(2026, 10, 1, tzinfo=timezone.utc),
    "until": datetime(2026, 10, 8, tzinfo=timezone.utc),
    "request": None,
}


async def _filters(handler: Any, store: _Store | None = None) -> list[Any]:
    store = store or _Store()
    await handler(store, user=_USER, **_WINDOW)
    return store.bodies[0]["query"]["bool"]["filter"]


_TOKEN_PRESETS = [
    query_token_usage_over_time,
    query_user_token_usage_over_time,
    query_token_usage_by_model,
    query_user_token_usage_by_model,
    query_token_usage_by_agent,
    query_user_token_usage_by_agent,
]


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", _TOKEN_PRESETS)
async def test_token_presets_read_turns_and_creation_assistant_drafts(
    handler: Any,
) -> None:
    filters = await _filters(handler)
    assert TOKEN_USAGE_FILTER in filters
    assert {"term": {"metric.name": TURN_COMPLETED_METRIC}} not in filters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler", [query_token_usage_by_agent, query_user_token_usage_by_agent]
)
async def test_by_agent_buckets_creation_assistant_drafts_under_their_label(
    handler: Any,
) -> None:
    buckets = [
        {
            "key": CREATION_ASSISTANT_LABEL,
            "sum_input": {"value": 120.0},
            "sum_output": {"value": 80.0},
            "by_model": {"buckets": []},
        }
    ]
    store = _Store({"aggregations": {"by_agent": {"buckets": buckets}}})

    result = await handler(store, user=_USER, **_WINDOW)

    body = store.bodies[0]
    assert BY_AGENT_SCOPE_FILTER in body["query"]["bool"]["filter"]
    assert body["aggs"]["by_agent"]["terms"]["missing"] == CREATION_ASSISTANT_LABEL
    assert [(r.label, r.value) for r in result.rows] == [
        (CREATION_ASSISTANT_LABEL, 200)
    ]


@pytest.mark.asyncio
async def test_team_view_counts_the_team_where_the_agent_is_created() -> None:
    store = _Store()
    await query_token_usage_over_time(store, user=_USER, team_id="team-1", **_WINDOW)  # type: ignore[arg-type]
    filters = store.bodies[0]["query"]["bool"]["filter"]
    assert {"term": {"dims.team_id": "team-1"}} in filters
    assert TOKEN_USAGE_FILTER in filters


@pytest.mark.asyncio
async def test_turn_count_presets_ignore_creation_assistant_drafts() -> None:
    filters = await _filters(query_messages_over_time)
    assert {"term": {"metric.name": TURN_COMPLETED_METRIC}} in filters
    assert CREATION_ASSISTANT_METRIC not in repr(filters)


@pytest.mark.asyncio
async def test_creation_assistant_usage_sums_tokens_of_assistant_calls_only() -> None:
    store = _Store(
        {
            "hits": {"total": {"value": 3, "relation": "eq"}},
            "aggregations": {
                "sum_input": {"value": 900.0},
                "sum_output": {"value": 300.0},
            },
        }
    )

    result = await query_creation_assistant_usage(store, user=_USER, **_WINDOW)  # type: ignore[arg-type]

    body = store.bodies[0]
    filters = body["query"]["bool"]["filter"]
    assert CREATION_ASSISTANT_ANSWERED_FILTER in filters
    assert TURN_COMPLETED_METRIC not in repr(filters)
    assert {
        "range": {
            "@timestamp": {
                "gte": _WINDOW["since"].isoformat(),
                "lte": _WINDOW["until"].isoformat(),
            }
        }
    } in filters
    assert body["track_total_hits"] is True
    assert (result.total_tokens, result.input_tokens, result.output_tokens) == (
        1200,
        900,
        300,
    )
    assert result.drafts == 3


@pytest.mark.asyncio
async def test_creation_assistant_usage_is_zero_without_events() -> None:
    result = await query_creation_assistant_usage(_Store(), user=_USER, **_WINDOW)  # type: ignore[arg-type]
    assert (result.total_tokens, result.drafts) == (0, 0)


def _matches(clause: dict[str, Any], doc: dict[str, Any]) -> bool:
    """The few OpenSearch filter clauses these presets use, on a flat doc."""
    ((kind, arg),) = clause.items()
    if kind == "term":
        ((field, value),) = arg.items()
        return doc.get(field) == value
    if kind == "exists":
        return arg["field"] in doc
    if kind == "bool":
        must = all(_matches(c, doc) for c in arg.get("filter", []))
        should = arg.get("should", [])
        hits = sum(_matches(c, doc) for c in should)
        return must and hits >= arg.get("minimum_should_match", 0)
    raise AssertionError(f"unsupported clause {kind}")


_ANSWERED = {
    "metric.name": CREATION_ASSISTANT_METRIC,
    "dims.status": "error",
    "quantities.input_tokens": 120,
}
_TIMED_OUT = {"metric.name": CREATION_ASSISTANT_METRIC, "dims.status": "timeout"}
_TURN = {"metric.name": TURN_COMPLETED_METRIC}


def test_token_usage_skips_creation_assistant_events_without_tokens() -> None:
    # A timeout or provider error is emitted without tokens: no empty bucket.
    assert _matches(TOKEN_USAGE_FILTER, _ANSWERED)
    assert _matches(TOKEN_USAGE_FILTER, _TURN)
    assert not _matches(TOKEN_USAGE_FILTER, _TIMED_OUT)
    assert not _matches(TOKEN_USAGE_FILTER, {"metric.name": "agent.other"})


def test_creation_assistant_drafts_count_answered_calls_only() -> None:
    assert _matches(CREATION_ASSISTANT_ANSWERED_FILTER, _ANSWERED)
    assert not _matches(CREATION_ASSISTANT_ANSWERED_FILTER, _TIMED_OUT)
    assert not _matches(CREATION_ASSISTANT_ANSWERED_FILTER, _TURN)
