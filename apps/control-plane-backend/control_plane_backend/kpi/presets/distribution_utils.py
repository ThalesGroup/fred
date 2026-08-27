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

`conversations_per_user`, `conversation_depth` and `agents_per_user` (issue
#2426) reduce a `terms` aggregation to the same shape: a list of per-entity
counts turned into a fixed 11-bucket histogram plus a median. The maths lives
here, pure and unit-testable, so the presets cannot drift apart — the preset
modules keep only their OpenSearch query.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from fred_core.common import TeamId

from control_plane_backend.kpi.presets.common import (
    DistributionResponse,
    LabelValuePoint,
)

# `terms` size cap shared by the engagement presets. Same large-size precedent
# as `agent_prompt_length_distribution`: a platform with more than this many
# distinct users (or conversations) in one window silently loses the tail of the
# distribution — and not uniformly: `terms` keeps the highest doc_counts, so
# what drops is the *low*-count tail, undercounting the "1" bucket and biasing
# the median upward. (For a `cardinality_of` body the kept entities are still
# those with the most rows — only a proxy for the distinct-count actually
# bucketed.) Acceptable for a dashboard histogram, and cheaper than a
# composite-agg pagination loop — revisit if a deployment ever gets close.
TERMS_SIZE = 10000

# (lower bound, upper bound inclusive or None for open-ended, display label).
# Ordered, contiguous and exhaustive over [1, +inf): every count coming out of a
# `terms` agg lands in exactly one bucket. Labels are display-ready and are sent
# to the frontend verbatim — they are numeric ranges, so they need no
# translation.
BUCKETS: tuple[tuple[int, int | None, str], ...] = (
    (1, 1, "1"),
    (2, 3, "2-3"),
    (4, 5, "4-5"),
    (6, 7, "6-7"),
    (8, 9, "8-9"),
    (10, 11, "10-11"),
    (12, 13, "12-13"),
    (14, 15, "14-15"),
    (16, 17, "16-17"),
    (18, 19, "18-19"),
    (20, None, "20+"),
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


AGG_NAME = "by_entity"

# Sub-agg name for the cardinality variant. `agents_per_user` does not ask "how
# many rows does this user have" but "how many *distinct* agents do those rows
# mention", so its per-entity number is a cardinality, not a doc_count — same
# bucketing and median afterwards.
CARDINALITY_AGG_NAME = "distinct"


def metric_filters(
    *,
    metric_name: str,
    since: datetime,
    until: datetime,
    team_id: TeamId | None,
    exists_fields: Sequence[str | None] = (),
) -> list[dict[str, Any]]:
    """The `bool.filter` clauses every engagement query shares.

    Written in one place because of the `kpi/README.md` warning: a preset that
    silently returns unfiltered data for a `team_id` it doesn't honour is worse
    than one that refuses team scoping outright. `trend_utils` builds on this
    too, so the trend presets cannot filter differently from their distribution
    siblings. `None` entries in `exists_fields` are skipped, so callers can pass
    their optional dims straight through.
    """
    filters: list[dict[str, Any]] = [
        {
            "range": {
                "@timestamp": {
                    "gte": since.isoformat(),
                    "lte": until.isoformat(),
                }
            }
        },
        {"term": {"metric.name": metric_name}},
    ]
    filters.extend(
        {"exists": {"field": field}} for field in exists_fields if field is not None
    )
    if team_id is not None:
        filters.append({"term": {"dims.team_id": str(team_id)}})
    return filters


def distribution_body(
    *,
    metric_name: str,
    group_by: str,
    since: datetime,
    until: datetime,
    team_id: TeamId | None,
    require_group_by: bool = False,
    cardinality_of: str | None = None,
) -> dict[str, Any]:
    """Build the OpenSearch body for a "count per entity" distribution.

    The engagement presets ask the same question of different fields — count
    `metric_name` rows in the window, grouped by `group_by` — so the body is
    built once here, over the shared `metric_filters` clauses.

    `require_group_by` adds an `exists` filter, for a dim that only some rows
    carry.

    `cardinality_of` switches the per-entity number from the bucket doc_count to
    the number of distinct values of that field. Rows missing the field never
    affect a cardinality agg; the `exists` filter is for entities whose rows
    *all* lack it — kept, they would reduce to a cardinality of 0, which
    `bucket_counts` drops but `median_of` would count, leaving the histogram and
    the median describing different populations.
    """
    filters = metric_filters(
        metric_name=metric_name,
        since=since,
        until=until,
        team_id=team_id,
        exists_fields=(group_by if require_group_by else None, cardinality_of),
    )

    # One bucket per entity; its doc_count is that entity's count.
    by_entity: dict[str, Any] = {"terms": {"field": group_by, "size": TERMS_SIZE}}
    if cardinality_of is not None:
        by_entity["aggs"] = {
            CARDINALITY_AGG_NAME: {"cardinality": {"field": cardinality_of}}
        }

    return {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {AGG_NAME: by_entity},
    }


def distribution_from_terms_agg(
    response: dict[str, Any],
    *,
    since: datetime,
    until: datetime,
    agg_name: str = AGG_NAME,
) -> DistributionResponse:
    """Reduce a `distribution_body` response to a `DistributionResponse`.

    One bucket per entity, its `doc_count` being that entity's count — or the
    `CARDINALITY_AGG_NAME` sub-agg's value when the body was built with
    `cardinality_of`, detected per bucket so the two call sites cannot fall out
    of agreement. Kept here so the presets share one reduction instead of
    copies that can drift.
    """
    buckets = response.get("aggregations", {}).get(agg_name, {}).get("buckets", [])
    counts = [
        int(bucket[CARDINALITY_AGG_NAME]["value"])
        if CARDINALITY_AGG_NAME in bucket
        else int(bucket["doc_count"])
        for bucket in buckets
    ]
    return DistributionResponse(
        rows=bucket_counts(counts),
        median=median_of(counts),
        since=since,
        until=until,
    )
