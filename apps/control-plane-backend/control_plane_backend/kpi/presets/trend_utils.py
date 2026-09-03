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

"""Trailing-window median helpers for the engagement trend presets.

`conversations_per_user_trend`, `conversation_depth_trend` and
`agents_per_user_trend` (issue #2428) ask their distribution siblings' question
once per bucket: over the window ending at this bucket, what is the median
per-entity count? The maths lives here, pure and unit-testable, so the three
presets keep nothing but their OpenSearch query — the same split
`distribution_utils` already applies to the histograms.

**Pooling, not smoothing.** A point is the median of what each entity
accumulated *across the whole window*, not the average of the per-bucket
medians. Pooling enlarges the sample, keeps a meaning a reader can state out
loud ("median conversations per active user over the trailing 7 days"), and
survives sparse buckets — a moving average of per-bucket medians would flatten
to 1 the moment most entities appear in only one bucket.

**Active-only population**, as everywhere else in the Engagement section: an
entity with nothing in the window is not a 0, it is absent. A bucket whose
whole window is empty therefore has no median at all and is left out of `rows`
rather than reported as 0 — "no conversations to measure" and "conversations
that were 0 messages deep" are not the same statement.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

from fred_core.common import TeamId

from control_plane_backend.kpi.presets.common import (
    TimeSeriesPoint,
    TimeSeriesResponse,
)
from control_plane_backend.kpi.presets.distribution_utils import (
    median_of,
    metric_filters,
)
from control_plane_backend.kpi.utils import TREND_WINDOW_BUCKETS, TrendInterval

# `terms` size cap for the trend presets — deliberately tighter than
# `distribution_utils.TERMS_SIZE`, because here every kept entity costs a whole
# nested date_histogram rather than a single bucket. The cap counts distinct
# entities over the *whole queried range* (lookback included), not per window:
# a platform with more entities than this over the range loses the tail, and
# `terms` drops the *low*-doc-count tail first, which biases every point's
# median upward. For `conversation_depth_trend` the entities are sessions, so
# this cap is five times tighter than the histogram sibling's 10000 — on a
# platform past ~2000 conversations per range the trend line and the range-wide
# median tile describe measurably different populations, not "slightly"
# different ones. There is also a hard ceiling on the other side: the
# entity × (sub-entity ×) bucket product feeds OpenSearch's `search.max_buckets`
# (default 65 535), and crossing it rejects the whole request — the chart shows
# its error state while the histogram beside it still renders. Loud, not
# silent. Both limits are acceptable for a dashboard trend today and far
# cheaper than paginating a composite agg over every user × bucket pair —
# revisit with composite pagination if a deployment approaches either.
TREND_TERMS_SIZE = 2000

# Second-level `terms` cap, for the distinct-value trend only: how many distinct
# agents one user can contribute over the queried range. A user talking to more
# agents than this would have their count clipped; the realistic figure is
# under ten, so this is headroom rather than a live constraint.
SUB_TERMS_SIZE = 100

BY_ENTITY = "by_entity"
BY_SUB_ENTITY = "by_sub_entity"
BY_TIME = "by_time"

T = TypeVar("T")


def trend_body(
    *,
    metric_name: str,
    group_by: str,
    interval: str,
    since: datetime,
    until: datetime,
    team_id: TeamId | None,
    require_group_by: bool = False,
    distinct_of: str | None = None,
) -> dict[str, Any]:
    """Build the one OpenSearch body a trend preset needs.

    `since` here is already the lookback start (`display since - window`) — the
    caller subtracts it, the reducer trims the extra buckets back off.

    The nested `date_histogram` carries `min_doc_count: 1` on purpose: its
    default is 0, which would pad every entity's series with empty buckets from
    its first activity to its last and turn a small response into an
    entities × buckets one. Empty buckets carry no information here — an entity
    absent from a bucket contributes nothing to the windows containing it.

    `distinct_of` switches the per-entity number from a row count to a count of
    distinct values, by breaking the entity down one level further before
    bucketing by time. Unlike a `cardinality` sub-agg (what the histogram
    sibling uses) this survives the rolling window: distinct counts cannot be
    summed across buckets, so the reducer needs the identities, not a per-bucket
    total.
    """
    filters = metric_filters(
        metric_name=metric_name,
        since=since,
        until=until,
        team_id=team_id,
        exists_fields=(group_by if require_group_by else None, distinct_of),
    )

    by_time: dict[str, Any] = {
        "date_histogram": {
            "field": "@timestamp",
            "fixed_interval": interval,
            "min_doc_count": 1,
        }
    }
    inner: dict[str, Any] = (
        {BY_TIME: by_time}
        if distinct_of is None
        else {
            BY_SUB_ENTITY: {
                "terms": {"field": distinct_of, "size": SUB_TERMS_SIZE},
                "aggs": {BY_TIME: by_time},
            }
        }
    )

    return {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            BY_ENTITY: {
                "terms": {"field": group_by, "size": TREND_TERMS_SIZE},
                "aggs": inner,
            }
        },
    }


def bucket_index(when: datetime, bucket: timedelta) -> int:
    """Index of the bucket containing `when`, on OpenSearch's own grid.

    A `fixed_interval` date_histogram floors each doc's timestamp to a multiple
    of the interval counted from the epoch, so dividing an epoch second count by
    the bucket length reproduces exactly the same grid — which lets the reducer
    line up buckets by arithmetic instead of trusting every entity's sub-agg to
    have returned the same set of keys.
    """
    return int(when.timestamp()) // int(bucket.total_seconds())


def _index_of_key(key_millis: int, bucket: timedelta) -> int:
    return key_millis // int(bucket.total_seconds() * 1000)


def count_slices(
    response: dict[str, Any], *, bucket: timedelta
) -> Iterator[tuple[str, int, int]]:
    """(entity, bucket index, row count) from a `terms → date_histogram` body."""
    for entity in (
        response.get("aggregations", {}).get(BY_ENTITY, {}).get("buckets", [])
    ):
        for slot in entity.get(BY_TIME, {}).get("buckets", []):
            yield (
                str(entity["key"]),
                _index_of_key(int(slot["key"]), bucket),
                int(slot["doc_count"]),
            )


def distinct_slices(
    response: dict[str, Any], *, bucket: timedelta
) -> Iterator[tuple[str, int, str]]:
    """(entity, bucket index, distinct value) from `terms → terms → date_histogram`.

    One triple per bucket the sub-entity appears in, so the same value can show
    up several times inside one window — that is the point: `pool_distinct`
    collapses them back to one, which is what "distinct agents over the trailing
    window" means and what summing per-bucket cardinalities would get wrong.
    """
    for entity in (
        response.get("aggregations", {}).get(BY_ENTITY, {}).get("buckets", [])
    ):
        for sub in entity.get(BY_SUB_ENTITY, {}).get("buckets", []):
            for slot in sub.get(BY_TIME, {}).get("buckets", []):
                yield (
                    str(entity["key"]),
                    _index_of_key(int(slot["key"]), bucket),
                    str(sub["key"]),
                )


def pool_counts(slices: Sequence[int]) -> int:
    """Row counts pool by addition."""
    return sum(slices)


def pool_distinct(slices: Sequence[str]) -> int:
    """Distinct values pool by union — an agent seen in three buckets of the
    same window is one agent, not three."""
    return len(set(slices))


def rolling_medians(
    slices: Iterable[tuple[str, int, T]],
    *,
    pool: Callable[[Sequence[T]], int],
    first_index: int,
    last_index: int,
    window_buckets: int = TREND_WINDOW_BUCKETS,
) -> dict[int, float]:
    """Median of the pooled per-entity counts, per bucket in the display range.

    Each slice is pushed forward into the (at most `window_buckets`) windows
    that contain it, so the cost follows the size of the OpenSearch response
    rather than buckets × entities — a preset never re-queries per bucket.
    Windows outside `[first_index, last_index]` are dropped on the way in: the
    lookback buckets are there to fill the early windows, never to be displayed.

    A bucket with no active entity is absent from the result, not 0 — see the
    module docstring.
    """
    pooled: defaultdict[int, defaultdict[str, list[T]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for entity, index, contribution in slices:
        window_start = max(index, first_index)
        window_end = min(index + window_buckets - 1, last_index)
        for target in range(window_start, window_end + 1):
            pooled[target][entity].append(contribution)

    medians: dict[int, float] = {}
    for index, per_entity in pooled.items():
        # `>= 1` keeps the population identical to the histogram's: an entity
        # that pools to nothing is not part of the median's sample.
        counts = [
            count
            for contributions in per_entity.values()
            if (count := pool(contributions))
        ]
        median = median_of(counts)
        if median is not None:
            medians[index] = median
    return medians


def trend_response(
    slices: Iterable[tuple[str, int, T]],
    *,
    pool: Callable[[Sequence[T]], int],
    resolved: TrendInterval,
    since: datetime,
    until: datetime,
) -> TimeSeriesResponse:
    """Reduce one `trend_body` response to a `TimeSeriesResponse`.

    The displayed range runs from the bucket containing `since` to the last
    *complete* bucket at or before `until`. The final bucket is trimmed when
    `until` falls inside it (it almost always does — `until` is usually "now"):
    its window would pool one short bucket among full ones, and a median that
    systematically dips at the right edge reads as a collapse, where a short
    last *bar* on the plain series charts reads as merely partial. Unlike those
    charts the rows are also sparse — only buckets whose window holds at least
    one active entity are emitted (see the module docstring).
    """
    first_index = bucket_index(since, resolved.bucket)
    last_index = bucket_index(until, resolved.bucket)
    bucket_seconds = int(resolved.bucket.total_seconds())
    if until.timestamp() < (last_index + 1) * bucket_seconds:
        last_index -= 1
    medians = rolling_medians(
        slices,
        pool=pool,
        first_index=first_index,
        last_index=last_index,
        window_buckets=resolved.window_buckets,
    )

    rows = [
        TimeSeriesPoint(
            date=datetime.fromtimestamp(
                index * int(resolved.bucket.total_seconds()), tz=timezone.utc
            ).strftime(resolved.date_fmt),
            value=medians[index],
        )
        for index in sorted(medians)
    ]

    return TimeSeriesResponse(
        rows=rows,
        since=since,
        until=until,
        interval=resolved.interval,
        window=resolved.window,
    )
