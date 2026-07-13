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
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fred_core import ORGANIZATION_ID, KeycloakUser, OrganizationPermission
from fred_core.documents import PostgresDocumentMetadataStore
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets.base import PresetDef
from control_plane_backend.kpi.presets.common import ScalarWithDeltaResponse

logger = logging.getLogger(__name__)

_DOCUMENT_METRICS = ["document.created_total", "document.deleted_total"]


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


def _has_any_document_events_before(
    store: OpenSearchKPIStore, cutoff: datetime
) -> bool:
    """Return True if any document lifecycle KPI event was recorded before `cutoff`.

    When False, instrumentation had not yet been deployed at that point in time
    and historical reconstruction is impossible.
    """
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"lt": cutoff.isoformat()}}},
                    {"terms": {"metric.name": _DOCUMENT_METRICS}},
                ]
            }
        },
    }
    resp = store.client.search(index=store.index, body=body)
    return int(resp.get("hits", {}).get("total", {}).get("value", 0)) > 0


async def _count_all_documents(request: Request) -> int:
    container = get_application_container(request)
    engine = container.get_pg_async_engine()
    store = PostgresDocumentMetadataStore(engine)
    return await store.count_all()


async def query_documents_total(
    store: OpenSearchKPIStore,
    *,
    user: KeycloakUser,
    since: datetime,
    until: datetime,
    request: Request,
) -> ScalarWithDeltaResponse:
    await (
        get_application_container(request)
        .get_rebac_engine()
        .check_user_permission_or_raise(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
    )

    now = datetime.now(tz=timezone.utc)

    # If no document lifecycle events exist before `until`, instrumentation was not
    # deployed yet for this period — we cannot reconstruct the historical count.
    if not _has_any_document_events_before(store, until):
        return ScalarWithDeltaResponse(unavailable=True, since=since, until=until)

    current_count = await _count_all_documents(request)
    created_in_range = _count_events(store, "document.created_total", since, until)
    deleted_in_range = _count_events(store, "document.deleted_total", since, until)
    created_after = _count_events(store, "document.created_total", until, now)
    deleted_after = _count_events(store, "document.deleted_total", until, now)

    count_at_until = current_count - created_after + deleted_after

    return ScalarWithDeltaResponse(
        value=count_at_until,
        delta=created_in_range - deleted_in_range,
        since=since,
        until=until,
    )


DOCUMENTS_TOTAL_PRESET = PresetDef(
    name="documents_total",
    response_model=ScalarWithDeltaResponse,
    handler=query_documents_total,
    summary="Total number of uploaded documents and net change over the selected time range",
)
