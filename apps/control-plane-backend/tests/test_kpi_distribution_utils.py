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

"""Unit tests for the engagement-distribution helpers (issue #2426).

Only the pure reduction is covered here — the preset handlers' OpenSearch
queries are integration-tested against a live OpenSearch, never mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from control_plane_backend.kpi.presets.distribution_utils import (
    BUCKETS,
    bucket_counts,
    distribution_from_terms_agg,
    median_of,
)

BUCKET_LABELS = ["1", "2-5", "6-10", "11-20", "21+"]


def _values(counts: list[int]) -> dict[str, int]:
    return {row.label: row.value for row in bucket_counts(counts)}


def test_buckets_are_the_agreed_five() -> None:
    assert [label for _low, _high, label in BUCKETS] == BUCKET_LABELS


def test_every_bucket_is_present_with_zeros_for_empty_input() -> None:
    rows = bucket_counts([])
    assert [row.label for row in rows] == BUCKET_LABELS
    assert all(row.value == 0 for row in rows)


def test_bucket_order_is_stable_regardless_of_input_order() -> None:
    assert [row.label for row in bucket_counts([30, 1, 7])] == BUCKET_LABELS


@pytest.mark.parametrize(
    ("count", "expected_label"),
    [
        (1, "1"),
        (2, "2-5"),
        (5, "2-5"),
        (6, "6-10"),
        (10, "6-10"),
        (11, "11-20"),
        (20, "11-20"),
        (21, "21+"),
        (10_000, "21+"),
    ],
)
def test_bucket_edges(count: int, expected_label: str) -> None:
    values = _values([count])
    assert values[expected_label] == 1
    assert sum(values.values()) == 1


def test_counts_accumulate_per_bucket() -> None:
    assert _values([1, 1, 3, 4, 5, 12, 99]) == {
        "1": 2,
        "2-5": 3,
        "6-10": 0,
        "11-20": 1,
        "21+": 1,
    }


def test_counts_below_the_first_bucket_are_ignored() -> None:
    # A terms agg never yields 0 (a bucket exists only because it has docs),
    # but a stray value must not be misfiled into the "1" bucket.
    assert sum(_values([0, -3]).values()) == 0


def test_median_of_empty_is_none() -> None:
    assert median_of([]) is None


def test_median_odd_population() -> None:
    assert median_of([5, 1, 3]) == 3.0


def test_median_even_population_averages_the_two_middles() -> None:
    assert median_of([1, 2, 3, 4]) == 2.5


def test_median_even_population_can_be_a_whole_number() -> None:
    assert median_of([2, 2, 4, 4]) == 3.0


def test_median_single_value() -> None:
    assert median_of([7]) == 7.0


def test_distribution_from_terms_agg_reduces_doc_counts() -> None:
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = datetime(2026, 8, 25, tzinfo=timezone.utc)
    response = {
        "aggregations": {
            "by_user": {
                "buckets": [
                    {"key": "alice", "doc_count": 1},
                    {"key": "bob", "doc_count": 7},
                    {"key": "carol", "doc_count": 22},
                ]
            }
        }
    }

    result = distribution_from_terms_agg(
        response, agg_name="by_user", since=since, until=until
    )

    assert {row.label: row.value for row in result.rows} == {
        "1": 1,
        "2-5": 0,
        "6-10": 1,
        "11-20": 0,
        "21+": 1,
    }
    assert result.median == 7.0
    assert result.since == since
    assert result.until == until


def test_distribution_from_terms_agg_handles_a_missing_aggregation() -> None:
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    until = datetime(2026, 8, 25, tzinfo=timezone.utc)

    result = distribution_from_terms_agg(
        {}, agg_name="by_session", since=since, until=until
    )

    assert [row.value for row in result.rows] == [0, 0, 0, 0, 0]
    assert result.median is None
