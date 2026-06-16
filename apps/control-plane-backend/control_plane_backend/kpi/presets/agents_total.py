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

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser, require_admin
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import ScalarWithDeltaResponse

logger = logging.getLogger(__name__)


async def _count_all_agents(request: Request) -> int:
    container = get_application_container(request)
    store = container.get_agent_instance_store()
    return await store.count_all()


def _count_events(
    store: OpenSearchKPIStore, metric_name: str, since: datetime, until: datetime
) -> int:
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
                    {"term": {"metric.name": metric_name}},
                ]
            }
        },
        "aggs": {"total": {"value_count": {"field": "metric.name"}}},
    }
    resp = store.client.search(index=store.index, body=body)
    return int(resp.get("aggregations", {}).get("total", {}).get("value", 0))


async def query_agents_total(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> ScalarWithDeltaResponse:
    require_admin(user)

    current_count = await _count_all_agents(request)
    created = _count_events(store, "agent.created_total", since, until)
    deleted = _count_events(store, "agent.deleted_total", since, until)

    return ScalarWithDeltaResponse(
        value=current_count,
        delta=created - deleted,
        since=since,
        until=until,
    )


AGENTS_TOTAL_PRESET = PresetDef(
    name="agents_total",
    response_model=ScalarWithDeltaResponse,
    handler=query_agents_total,
    summary="Current total number of enrolled agents and net change over the selected time range",
)
