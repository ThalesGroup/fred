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

"""Bucketing, median and concentration of per-entity counts."""

from __future__ import annotations

import pytest
from control_plane_backend.kpi.presets.distribution_utils import (
    CONVERSATION_BUCKETS,
    bucket_counts,
    median_of,
    terms_counts,
    top_decile_share,
)


def _tallies(counts: list[int]) -> dict[str, int]:
    return {p.label: p.value for p in bucket_counts(counts, CONVERSATION_BUCKETS)}


def test_every_bucket_is_present_in_order_with_zeros() -> None:
    assert list(_tallies([])) == ["1", "2-3", "4-10", "11-30", "31+"]
    assert set(_tallies([]).values()) == {0}


@pytest.mark.parametrize(
    ("count", "label"),
    [
        (1, "1"),
        (2, "2-3"),
        (3, "2-3"),
        (4, "4-10"),
        (10, "4-10"),
        (11, "11-30"),
        (30, "11-30"),
        (31, "31+"),
        (500, "31+"),
    ],
)
def test_bucket_edges(count: int, label: str) -> None:
    assert _tallies([count])[label] == 1


def test_counts_below_the_first_bucket_are_ignored() -> None:
    assert sum(_tallies([0, -1]).values()) == 0


def test_median() -> None:
    assert median_of([]) is None
    assert median_of([3, 1, 2]) == 2.0
    assert median_of([4, 1, 3, 2]) == 2.5


def test_top_decile_share() -> None:
    assert top_decile_share([]) is None
    # 20 users: the top 2 carry 60 of 96 conversations.
    assert top_decile_share([30, 30] + [2] * 18) == pytest.approx(60 / 96)
    assert top_decile_share([5]) == 1.0


def test_terms_counts_reads_doc_counts_and_tolerates_absence() -> None:
    bucket = {
        "by_user": {
            "buckets": [{"key": "a", "doc_count": 3}, {"key": "b", "doc_count": 1}]
        }
    }
    assert terms_counts(bucket, "by_user") == [3, 1]
    assert terms_counts({}, "by_user") == []
