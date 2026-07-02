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
from fred_core import ORGANIZATION_ID, KeycloakUser, OrganizationPermission
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import LabelValuePoint, LabelValueResponse

logger = logging.getLogger(__name__)


async def query_sessions_by_scope(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> LabelValueResponse:
    await (
        get_application_container(request)
        .get_rebac_engine()
        .check_user_permission_or_raise(
            user, OrganizationPermission.CAN_READ_KPI_GLOBAL, ORGANIZATION_ID
        )
    )

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
            "by_scope": {
                "terms": {
                    "field": "dims.scope_type",
                    "size": 10,
                }
            }
        },
    }

    resp = store.client.search(index=store.index, body=body)
    buckets = resp.get("aggregations", {}).get("by_scope", {}).get("buckets", [])

    rows = [
        LabelValuePoint(label=bucket["key"], value=bucket["doc_count"])
        for bucket in buckets
    ]

    return LabelValueResponse(rows=rows, since=since, until=until)


SESSIONS_BY_SCOPE_PRESET = PresetDef(
    name="sessions_by_scope",
    response_model=LabelValueResponse,
    handler=query_sessions_by_scope,
    summary="Conversation count split by scope (personal vs team) over the selected time range",
)
