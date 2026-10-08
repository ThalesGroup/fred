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

"""Platform-wide creation assistant token consumption and number of drafts.

`drafts` counts the calls the provider answered (usable or not); timeouts and
provider errors carry no tokens and are left to the latency/status analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from fred_core import KeycloakUser
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import (
    CREATION_ASSISTANT_ANSWERED_FILTER,
    CreationAssistantUsageResponse,
)


async def query_creation_assistant_usage(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> CreationAssistantUsageResponse:
    # Authorization already resolved by the router (kpi/api.py, KpiScope).
    del user, request

    body: dict[str, Any] = {
        "size": 0,
        "track_total_hits": True,
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
                    CREATION_ASSISTANT_ANSWERED_FILTER,
                ]
            }
        },
        "aggs": {
            "sum_input": {"sum": {"field": "quantities.input_tokens"}},
            "sum_output": {"sum": {"field": "quantities.output_tokens"}},
        },
    }

    resp = store.client.search(index=store.index, body=body)
    aggs = resp.get("aggregations", {})
    input_tokens = int(aggs.get("sum_input", {}).get("value") or 0)
    output_tokens = int(aggs.get("sum_output", {}).get("value") or 0)
    drafts = int(resp.get("hits", {}).get("total", {}).get("value", 0))

    return CreationAssistantUsageResponse(
        total_tokens=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        drafts=drafts,
        since=since,
        until=until,
    )


CREATION_ASSISTANT_USAGE_PRESET = PresetDef(
    name="creation_assistant_usage",
    response_model=CreationAssistantUsageResponse,
    handler=query_creation_assistant_usage,
    summary="Creation assistant token consumption and number of drafts, platform-wide",
)
