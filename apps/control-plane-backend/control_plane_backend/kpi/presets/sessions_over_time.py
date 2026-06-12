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

# NOTE: Builds raw OpenSearch queries directly — the KPIQuery DSL does not yet
# support `date_histogram` with `doc_count` extraction. Tracked for a future
# fred-core library extension.

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fred_core import KeycloakUser, require_admin
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import TimeSeriesPoint, TimeSeriesResponse
from control_plane_backend.kpi.utils import resolve_interval

logger = logging.getLogger(__name__)


def query_sessions_over_time(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
) -> TimeSeriesResponse:
    require_admin(user)

    interval, date_fmt = resolve_interval(since, until)

    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": since.isoformat(),
                                "lte": until.isoformat(),
                            }
                        }
                    },
                    {"term": {"metric.name": "session.created_total"}},
                ]
            }
        },
        "aggs": {
            "by_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": interval,
                    "min_doc_count": 0,
                    "extended_bounds": {
                        "min": since.isoformat(),
                        "max": until.isoformat(),
                    },
                },
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_time", {}).get("buckets", [])

    rows = [
        TimeSeriesPoint(
            date=datetime.fromisoformat(
                bucket["key_as_string"].replace("Z", "+00:00")
            ).strftime(date_fmt),
            value=bucket["doc_count"],
        )
        for bucket in buckets
    ]

    return TimeSeriesResponse(
        rows=rows,
        since=since,
        until=until,
        interval=interval,
    )


SESSIONS_OVER_TIME_PRESET = PresetDef(
    name="sessions_over_time",
    response_model=TimeSeriesResponse,
    handler=query_sessions_over_time,
    summary="New sessions (conversations) over time, bucketed by auto-selected interval",
)
