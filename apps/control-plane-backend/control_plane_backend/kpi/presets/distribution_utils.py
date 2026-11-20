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

"""Bucketing, median and concentration of per-entity counts, kept pure for unit tests."""

from __future__ import annotations

import math
from typing import Sequence

from control_plane_backend.kpi.presets.common import LabelValuePoint

# `terms` size of the per-user and per-conversation counts. A larger platform
# loses the low-count tail of a period (terms keep the highest counts).
TERMS_SIZE = 10000

# (lower bound, upper bound inclusive or None for open-ended, label). Contiguous
# over [1, +inf); labels are numeric ranges the UI shows as they are.
Buckets = tuple[tuple[int, int | None, str], ...]
CONVERSATION_BUCKETS: Buckets = (
    (1, 1, "1"),
    (2, 3, "2-3"),
    (4, 10, "4-10"),
    (11, 30, "11-30"),
    (31, None, "31+"),
)


def bucket_counts(counts: Sequence[int], buckets: Buckets) -> list[LabelValuePoint]:
    """How many entities fall in each bucket; every bucket present, in order."""
    tallies = [0] * len(buckets)
    for count in counts:
        for index, (low, high, _label) in enumerate(buckets):
            if count >= low and (high is None or count <= high):
                tallies[index] += 1
                break
    return [
        LabelValuePoint(label=label, value=tallies[index])
        for index, (_low, _high, label) in enumerate(buckets)
    ]


def median_of(counts: Sequence[float]) -> float | None:
    """Median, None for no entity at all (shown as no data, not 0)."""
    if not counts:
        return None
    ordered = sorted(counts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def top_decile_share(counts: Sequence[int]) -> float | None:
    """Share of the total carried by the 10 % highest counts (at least one entity)."""
    total = sum(counts)
    if not total:
        return None
    top = sorted(counts, reverse=True)[: max(1, math.ceil(len(counts) / 10))]
    return sum(top) / total


def terms_counts(bucket: dict, agg: str) -> list[int]:
    """Doc counts of a `terms` agg named `agg` inside `bucket`."""
    return [int(b["doc_count"]) for b in bucket.get(agg, {}).get("buckets", [])]
