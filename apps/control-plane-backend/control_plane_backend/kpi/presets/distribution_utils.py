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

"""Shared bucketing/median helpers for the engagement distribution presets.

Both `conversations_per_user` and `conversation_depth` (issue #2426) reduce a
`terms` aggregation to the same shape: a list of per-entity doc_counts turned
into a fixed 5-bucket histogram plus a median. The maths lives here, pure and
unit-testable, so the two presets cannot drift apart — the preset modules keep
only their OpenSearch query.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from control_plane_backend.kpi.presets.common import (
    DistributionResponse,
    LabelValuePoint,
)

# `terms` size cap shared by both engagement presets. Same large-size precedent
# as `agent_prompt_length_distribution`: a platform with more than this many
# distinct users (or conversations) in one window silently loses the tail of the
# distribution. Acceptable for a dashboard histogram, and cheaper than a
# composite-agg pagination loop — revisit if a deployment ever gets close.
TERMS_SIZE = 10000

# (lower bound, upper bound inclusive or None for open-ended, display label).
# Ordered, contiguous and exhaustive over [1, +inf): every count coming out of a
# `terms` agg lands in exactly one bucket. Labels are display-ready and are sent
# to the frontend verbatim — they are numeric ranges, so they need no
# translation.
BUCKETS: tuple[tuple[int, int | None, str], ...] = (
    (1, 1, "1"),
    (2, 5, "2-5"),
    (6, 10, "6-10"),
    (11, 20, "11-20"),
    (21, None, "21+"),
)


def bucket_counts(counts: Sequence[int]) -> list[LabelValuePoint]:
    """Bucket per-entity counts into `BUCKETS`, in `BUCKETS` order.

    Every bucket is always present (value 0 when empty) so the histogram keeps
    a stable x axis whatever the time range holds. A count below the first
    bucket's lower bound cannot come from a `terms` agg (a bucket exists only
    because it has at least one doc) but is ignored rather than misfiled if it
    ever does.
    """
    tallies = [0] * len(BUCKETS)
    for count in counts:
        for index, (low, high, _label) in enumerate(BUCKETS):
            if count >= low and (high is None or count <= high):
                tallies[index] += 1
                break
    return [
        LabelValuePoint(label=label, value=tallies[index])
        for index, (_low, _high, label) in enumerate(BUCKETS)
    ]


def median_of(counts: Sequence[int]) -> float | None:
    """Median of `counts` — the average of the two middle values for an even
    population. None for an empty input: no entity means no median, which the
    frontend renders as "no data" rather than as 0."""
    if not counts:
        return None
    ordered = sorted(counts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def distribution_from_terms_agg(
    response: dict[str, Any],
    *,
    agg_name: str,
    since: datetime,
    until: datetime,
) -> DistributionResponse:
    """Reduce a single-level `terms` aggregation to a `DistributionResponse`.

    One bucket per entity, its `doc_count` being that entity's count — the
    shape both engagement presets query for. Kept here so the two presets share
    one reduction instead of two copies that can drift.
    """
    counts = [
        int(bucket["doc_count"])
        for bucket in response.get("aggregations", {})
        .get(agg_name, {})
        .get("buckets", [])
    ]
    return DistributionResponse(
        rows=bucket_counts(counts),
        median=median_of(counts),
        since=since,
        until=until,
    )
