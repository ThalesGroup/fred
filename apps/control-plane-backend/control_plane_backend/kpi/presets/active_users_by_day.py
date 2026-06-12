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
# support `cardinality` aggregations or filtering on `dims.actor_type`. Tracked
# for a future fred-core library extension.

from __future__ import annotations

import logging
from typing import Any

from fred_core import KeycloakUser, require_admin
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
from pydantic import BaseModel

from control_plane_backend.kpi.presets.base import PresetDef

logger = logging.getLogger(__name__)


class ActiveUsersByDayRow(BaseModel):
    date: str
    unique_users: int
    doc_count: int


class ActiveUsersByDayResponse(BaseModel):
    rows: list[ActiveUsersByDayRow]
    since: str
    until: str


def query_active_users_by_day(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: str = "now-30d",
    until: str = "now",
) -> ActiveUsersByDayResponse:
    require_admin(user)
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": since, "lte": until}}},
                    {"term": {"metric.name": "api.request_latency_ms"}},
                    {"term": {"dims.actor_type": "human"}},
                ]
            }
        },
        "aggs": {
            "by_day": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": "1d",
                    "min_doc_count": 0,
                },
                "aggs": {"unique_users": {"cardinality": {"field": "dims.user_id"}}},
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_day", {}).get("buckets", [])

    rows = [
        ActiveUsersByDayRow(
            date=bucket["key_as_string"][:10],
            unique_users=bucket["unique_users"]["value"],
            doc_count=bucket["doc_count"],
        )
        for bucket in buckets
    ]

    return ActiveUsersByDayResponse(rows=rows, since=since, until=until)


ACTIVE_USERS_BY_DAY_PRESET = PresetDef(
    name="active_users_by_day",
    response_model=ActiveUsersByDayResponse,
    handler=query_active_users_by_day,
    summary="Distinct active users per day (cardinality of user_id per day bucket)",
)
