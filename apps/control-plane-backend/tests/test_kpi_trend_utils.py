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

"""Unit tests for the engagement-trend helpers (issue #2428).

Only the pure reduction is covered here — the preset handlers' OpenSearch
queries are integration-tested against a live OpenSearch, never mocked, the
same split `test_kpi_distribution_utils.py` uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from control_plane_backend.kpi.presets.trend_utils import (
    BY_ENTITY,
    BY_SUB_ENTITY,
    BY_TIME,
    SUB_TERMS_SIZE,
    TREND_TERMS_SIZE,
    bucket_index,
    count_slices,
    distinct_slices,
    pool_counts,
    pool_distinct,
    rolling_medians,
    trend_body,
    trend_response,
)
from control_plane_backend.kpi.utils import (
    TREND_WINDOW_BUCKETS,
    resolve_trend_interval,
)

DAY = timedelta(days=1)
DAY_MS = 86_400_000


def _day_key(day: int) -> int:
    """Epoch millis for 2026-08-<day> — the key OpenSearch puts on a daily bucket."""
    return int(datetime(2026, 8, day, tzinfo=timezone.utc).timestamp()) * 1000


# --- window resolution -------------------------------------------------------


@pytest.mark.parametrize(
    ("span", "interval", "window", "lookback"),
    [
        (timedelta(seconds=5), "1s", "7s", timedelta(seconds=7)),
        (timedelta(hours=5), "1m", "7m", timedelta(minutes=7)),
        (timedelta(days=2), "1h", "7h", timedelta(hours=7)),
        (timedelta(days=30), "1d", "7d", timedelta(days=7)),
    ],
)
def test_window_is_seven_buckets_whatever_the_interval(
    span: timedelta, interval: str, window: str, lookback: timedelta
) -> None:
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    resolved = resolve_trend_interval(since, since + span)

    assert resolved.interval == interval
    assert resolved.window == window
    assert resolved.lookback == lookback


def test_window_and_interval_cannot_drift() -> None:
    # The whole point of resolving both in one call: the window is the interval
    # multiplied by the bucket count, never an independently-chosen duration.
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for span in (timedelta(hours=5), timedelta(days=2), timedelta(days=90)):
        resolved = resolve_trend_interval(since, since + span)
        assert resolved.lookback == TREND_WINDOW_BUCKETS * resolved.bucket
        assert resolved.window == f"{TREND_WINDOW_BUCKETS}{resolved.interval[1:]}"


def test_bucket_index_matches_opensearchs_epoch_aligned_grid() -> None:
    # A fixed_interval date_histogram floors to a multiple of the interval
    # counted from the epoch — any time inside 2026-08-10 must land on the key
    # OpenSearch stamps that bucket with.
    for moment in (
        datetime(2026, 8, 10, tzinfo=timezone.utc),
        datetime(2026, 8, 10, 13, 37, tzinfo=timezone.utc),
        datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
    ):
        assert bucket_index(moment, DAY) == _day_key(10) // DAY_MS


# --- rolling pooling ---------------------------------------------------------


def _slices(*triples: tuple[str, int, int]) -> list[tuple[str, int, int]]:
    return list(triples)


def test_an_entity_spanning_several_buckets_pools_into_one_count() -> None:
    # alice has 2 + 3 + 1 rows across three buckets of the same window; the
    # window's population is a single entity whose count is 6, not three
    # entities of 2, 3 and 1.
    medians = rolling_medians(
        _slices(("alice", 10, 2), ("alice", 11, 3), ("alice", 12, 1)),
        pool=pool_counts,
        first_index=12,
        last_index=12,
    )

    assert medians == {12: 6.0}


def test_a_slice_falls_out_once_the_window_has_moved_past_it() -> None:
    # With a 7-bucket window, bucket 0 feeds windows 0..6 and no further.
    medians = rolling_medians(
        _slices(("alice", 0, 4)),
        pool=pool_counts,
        first_index=0,
        last_index=8,
    )

    assert sorted(medians) == [0, 1, 2, 3, 4, 5, 6]
    assert all(value == 4.0 for value in medians.values())


def test_lookback_buckets_are_pooled_into_but_never_emitted() -> None:
    # Bucket 3 is before the display range and must not produce a row of its
    # own, yet its rows still count towards the first displayed point.
    medians = rolling_medians(
        _slices(("alice", 3, 5), ("alice", 6, 1)),
        pool=pool_counts,
        first_index=6,
        last_index=7,
    )

    assert medians == {6: 6.0, 7: 6.0}


def test_medians_keep_their_half_counts() -> None:
    medians = rolling_medians(
        _slices(("alice", 0, 1), ("bob", 0, 2), ("carol", 0, 3), ("dave", 0, 4)),
        pool=pool_counts,
        first_index=0,
        last_index=0,
    )

    assert medians == {0: 2.5}


def test_a_bucket_with_no_active_entity_has_no_median() -> None:
    # Absent, not 0: "nothing to measure" and "measured 0" are different claims.
    medians = rolling_medians(
        _slices(("alice", 0, 3)),
        pool=pool_counts,
        first_index=0,
        last_index=20,
    )

    assert 7 not in medians
    assert max(medians) == 6


def test_an_entity_pooling_to_nothing_leaves_the_population() -> None:
    # Same rule as the histogram's `exists` filters: a 0 must not sit in the
    # median's sample and drag it down as a phantom active entity.
    medians = rolling_medians(
        [("alice", 0, 0), ("bob", 0, 4)],
        pool=pool_counts,
        first_index=0,
        last_index=0,
    )

    assert medians == {0: 4.0}


# --- distinct pooling --------------------------------------------------------


def test_a_repeated_agent_counts_once_per_window() -> None:
    # alice reached the same agent in two buckets of one window — one distinct
    # agent, which is exactly what summing per-bucket cardinalities gets wrong.
    medians = rolling_medians(
        [("alice", 4, "agent-a"), ("alice", 5, "agent-a")],
        pool=pool_distinct,
        first_index=5,
        last_index=5,
    )

    assert medians == {5: 1.0}


def test_distinct_agents_across_a_window_are_unioned() -> None:
    medians = rolling_medians(
        [
            ("alice", 4, "agent-a"),
            ("alice", 5, "agent-a"),
            ("alice", 5, "agent-b"),
            ("alice", 10, "agent-c"),
        ],
        pool=pool_distinct,
        first_index=5,
        last_index=10,
    )

    assert medians[5] == 2.0
    # Bucket 10 still sees agent-b (bucket 5 is inside its 7-bucket window)
    # plus agent-c.
    assert medians[10] == 3.0


def test_pool_helpers_agree_with_their_names() -> None:
    assert pool_counts([2, 3, 1]) == 6
    assert pool_distinct(["a", "a", "b"]) == 2


# --- response shaping --------------------------------------------------------


def _resolved_daily():
    return resolve_trend_interval(
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 31, tzinfo=timezone.utc),
    )


def test_trend_response_labels_rows_on_the_bucket_grid() -> None:
    since = datetime(2026, 8, 10, tzinfo=timezone.utc)
    until = datetime(2026, 8, 12, tzinfo=timezone.utc)
    resolved = _resolved_daily()
    first = bucket_index(since, DAY)

    result = trend_response(
        [("alice", first, 3), ("bob", first + 1, 5)],
        pool=pool_counts,
        resolved=resolved,
        since=since,
        until=until,
    )

    # `until` sits exactly on the 2026-08-12 bucket boundary, so that bucket
    # covers none of the range and is trimmed like any partial trailing bucket.
    assert [(row.date, row.value) for row in result.rows] == [
        ("2026-08-10", 3.0),
        ("2026-08-11", 4.0),
    ]
    assert result.interval == "1d"
    assert result.window == "7d"
    assert result.since == since
    assert result.until == until


def test_trend_response_drops_buckets_outside_the_display_range() -> None:
    since = datetime(2026, 8, 10, tzinfo=timezone.utc)
    until = datetime(2026, 8, 12, tzinfo=timezone.utc)
    resolved = _resolved_daily()
    first = bucket_index(since, DAY)

    result = trend_response(
        # One lookback slice, one in range, one past `until`.
        [("alice", first - 3, 2), ("alice", first, 1), ("alice", first + 4, 9)],
        pool=pool_counts,
        resolved=resolved,
        since=since,
        until=until,
    )

    assert [(row.date, row.value) for row in result.rows] == [
        ("2026-08-10", 3.0),
        ("2026-08-11", 3.0),
    ]


def test_trend_response_trims_the_partial_trailing_bucket() -> None:
    # `until` is usually "now", mid-bucket: that bucket's window would pool one
    # short bucket among full ones, and the median would systematically dip at
    # the right edge — so it is trimmed rather than displayed.
    since = datetime(2026, 8, 10, tzinfo=timezone.utc)
    until = datetime(2026, 8, 12, 9, 30, tzinfo=timezone.utc)
    resolved = _resolved_daily()
    first = bucket_index(since, DAY)

    result = trend_response(
        [("alice", first, 3), ("alice", first + 1, 3), ("alice", first + 2, 1)],
        pool=pool_counts,
        resolved=resolved,
        since=since,
        until=until,
    )

    assert [row.date for row in result.rows] == ["2026-08-10", "2026-08-11"]


def test_trend_response_of_an_empty_response_has_no_rows() -> None:
    since = datetime(2026, 8, 10, tzinfo=timezone.utc)
    until = datetime(2026, 8, 12, tzinfo=timezone.utc)
    resolved = _resolved_daily()

    result = trend_response(
        count_slices({}, bucket=resolved.bucket),
        pool=pool_counts,
        resolved=resolved,
        since=since,
        until=until,
    )

    assert result.rows == []
    assert result.window == "7d"


# --- aggregation extraction --------------------------------------------------


def test_count_slices_reads_one_triple_per_entity_bucket() -> None:
    response = {
        "aggregations": {
            BY_ENTITY: {
                "buckets": [
                    {
                        "key": "alice",
                        BY_TIME: {
                            "buckets": [
                                {"key": _day_key(10), "doc_count": 2},
                                {"key": _day_key(11), "doc_count": 3},
                            ]
                        },
                    },
                    {
                        "key": "bob",
                        BY_TIME: {"buckets": [{"key": _day_key(11), "doc_count": 1}]},
                    },
                ]
            }
        }
    }

    assert list(count_slices(response, bucket=DAY)) == [
        ("alice", _day_key(10) // DAY_MS, 2),
        ("alice", _day_key(11) // DAY_MS, 3),
        ("bob", _day_key(11) // DAY_MS, 1),
    ]


def test_distinct_slices_reads_one_triple_per_entity_value_bucket() -> None:
    response = {
        "aggregations": {
            BY_ENTITY: {
                "buckets": [
                    {
                        "key": "alice",
                        BY_SUB_ENTITY: {
                            "buckets": [
                                {
                                    "key": "agent-a",
                                    BY_TIME: {
                                        "buckets": [
                                            {"key": _day_key(10), "doc_count": 4},
                                            {"key": _day_key(11), "doc_count": 1},
                                        ]
                                    },
                                },
                                {
                                    "key": "agent-b",
                                    BY_TIME: {
                                        "buckets": [
                                            {"key": _day_key(11), "doc_count": 2}
                                        ]
                                    },
                                },
                            ]
                        },
                    }
                ]
            }
        }
    }

    assert list(distinct_slices(response, bucket=DAY)) == [
        ("alice", _day_key(10) // DAY_MS, "agent-a"),
        ("alice", _day_key(11) // DAY_MS, "agent-a"),
        ("alice", _day_key(11) // DAY_MS, "agent-b"),
    ]


def test_slice_readers_handle_a_missing_aggregation() -> None:
    assert list(count_slices({}, bucket=DAY)) == []
    assert list(distinct_slices({}, bucket=DAY)) == []


# --- query body --------------------------------------------------------------


def _body(**overrides) -> dict:
    kwargs = {
        "metric_name": "session.created_total",
        "group_by": "dims.user_id",
        "interval": "1d",
        "since": datetime(2026, 7, 25, tzinfo=timezone.utc),
        "until": datetime(2026, 8, 25, tzinfo=timezone.utc),
        "team_id": None,
    }
    kwargs.update(overrides)
    return trend_body(**kwargs)


def test_trend_body_buckets_each_entity_over_time() -> None:
    body = _body()
    assert body["size"] == 0
    assert body["aggs"][BY_ENTITY]["terms"] == {
        "field": "dims.user_id",
        "size": TREND_TERMS_SIZE,
    }
    assert body["aggs"][BY_ENTITY]["aggs"][BY_TIME]["date_histogram"] == {
        "field": "@timestamp",
        "fixed_interval": "1d",
        # Explicitly 1: date_histogram defaults to 0, which would pad every
        # entity's series with empty buckets and blow the response up.
        "min_doc_count": 1,
    }


def test_trend_body_filters_the_window_and_the_metric() -> None:
    filters = _body()["query"]["bool"]["filter"]
    assert {"term": {"metric.name": "session.created_total"}} in filters
    assert filters[0]["range"]["@timestamp"] == {
        "gte": "2026-07-25T00:00:00+00:00",
        "lte": "2026-08-25T00:00:00+00:00",
    }


def test_trend_body_scopes_to_a_team_when_given_one() -> None:
    filters = _body(team_id="fredlab")["query"]["bool"]["filter"]
    assert {"term": {"dims.team_id": "fredlab"}} in filters


def test_trend_body_omits_the_team_filter_when_platform_wide() -> None:
    filters = _body(team_id=None)["query"]["bool"]["filter"]
    assert not any("dims.team_id" in f.get("term", {}) for f in filters)


def test_trend_body_excludes_rows_without_the_group_by_dim() -> None:
    filters = _body(
        metric_name="agent.turn_completed",
        group_by="dims.session_id",
        require_group_by=True,
    )["query"]["bool"]["filter"]
    assert {"exists": {"field": "dims.session_id"}} in filters


def test_trend_body_breaks_down_by_the_distinct_field_before_bucketing() -> None:
    # The nesting order is the whole point: identities first, time second, so a
    # window can union them. terms → date_histogram → cardinality could not.
    inner = _body(distinct_of="dims.agent_instance_id")["aggs"][BY_ENTITY]["aggs"]
    assert inner[BY_SUB_ENTITY]["terms"] == {
        "field": "dims.agent_instance_id",
        "size": SUB_TERMS_SIZE,
    }
    assert BY_TIME in inner[BY_SUB_ENTITY]["aggs"]


def test_trend_body_excludes_rows_missing_the_distinct_field() -> None:
    filters = _body(distinct_of="dims.agent_instance_id")["query"]["bool"]["filter"]
    assert {"exists": {"field": "dims.agent_instance_id"}} in filters
