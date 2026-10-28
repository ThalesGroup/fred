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

"""`GET /kpi/analytics/export`: the analytics view of a scope and period as `.xlsx`.

It reuses the section preset functions, so the workbook shows the same
figures as the page; authorization is the presets' `resolve_kpi_scope`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.kpi.counted_days import (
    EXCLUDE_HOLIDAYS_QUERY,
    EXCLUDE_WEEKENDS_QUERY,
    check_time_zone,
    counted_days,
)
from control_plane_backend.kpi.export_workbook import (
    XLSX_MEDIA_TYPE,
    ExportData,
    build_workbook,
    export_filename,
)
from control_plane_backend.kpi.presets.analytics_activity_over_time import (
    query_analytics_activity_over_time,
)
from control_plane_backend.kpi.presets.analytics_adoption import (
    query_analytics_adoption,
)
from control_plane_backend.kpi.presets.analytics_agents import query_analytics_agents
from control_plane_backend.kpi.presets.analytics_quality_cost import (
    query_analytics_quality_cost,
)
from control_plane_backend.kpi.presets.analytics_teams import query_analytics_teams
from control_plane_backend.kpi.presets.analytics_teams_catalog import team_catalog
from control_plane_backend.kpi.presets.analytics_usage import query_analytics_usage
from control_plane_backend.kpi.scope import resolve_kpi_scope
from control_plane_backend.kpi.user_filter import UserFilterParam, parse_user_filter
from control_plane_backend.kpi.utils import Bucket


def add_export_route(
    router: APIRouter, get_store: Callable[..., OpenSearchKPIStore]
) -> None:
    async def export_analytics(
        request: Request,
        since: datetime | None = Query(
            default=None,
            description="Start of the time range (ISO 8601 datetime). Defaults to 30 days ago.",
        ),
        until: datetime | None = Query(
            default=None,
            description="End of the time range (ISO 8601 datetime). Defaults to now.",
        ),
        team_ids: list[TeamId] = Query(
            default_factory=list,
            description="Scope the export to these teams (repeat the parameter); same rules as the presets.",
        ),
        bucket: Bucket = Query(
            default="auto", description="Calendar bucket of the Over time sheet."
        ),
        tz: str = Query(
            default="Europe/Paris",
            description="IANA time zone of dates, calendar buckets and days.",
        ),
        lang: Literal["fr", "en"] = Query(
            default="fr", description="Language of the workbook."
        ),
        user_filter: UserFilterParam = None,
        exclude_weekends: bool = EXCLUDE_WEEKENDS_QUERY,
        exclude_holidays: bool = EXCLUDE_HOLIDAYS_QUERY,
        user: KeycloakUser = Depends(get_current_user),
        store: OpenSearchKPIStore = Depends(get_store),
    ) -> Response:
        check_time_zone(tz)
        scope = await resolve_kpi_scope(
            request, user, team_ids, user_filter=parse_user_filter(user_filter)
        )

        now = datetime.now(tz=timezone.utc)
        resolved_since = since or (now - timedelta(days=30))
        resolved_until = until or now
        days = counted_days(
            exclude_weekends, exclude_holidays, tz, resolved_until - resolved_since
        )
        common: dict[str, Any] = dict(
            user=user,
            since=resolved_since,
            until=resolved_until,
            request=request,
            team_ids=scope.team_ids,
            user_ids=scope.user_ids,
            days=days,
        )
        sections, catalog = await asyncio.gather(
            asyncio.gather(
                query_analytics_adoption(store, **common, tz=tz),
                query_analytics_usage(store, **common, tz=tz),
                query_analytics_teams(store, **common),
                query_analytics_agents(store, **common),
                query_analytics_quality_cost(store, **common),
                query_analytics_activity_over_time(
                    store, **common, bucket=bucket, tz=tz
                ),
            ),
            team_catalog(request, scope.team_ids),
        )
        adoption, usage, teams, agents, quality, activity = sections
        data = ExportData(
            since=resolved_since,
            until=resolved_until,
            previous_since=adoption.previous_since,
            tz=tz,
            team_ids=tuple(str(t) for t in scope.team_ids),
            exported_at=now,
            adoption=adoption,
            usage=usage,
            teams=teams,
            agents=agents,
            quality=quality,
            activity=activity,
            catalog=catalog,
            user_filter=scope.user_filter,
            days=days,
        )
        # openpyxl is CPU-bound and synchronous: keep it off the event loop.
        content = await asyncio.to_thread(build_workbook, data, lang)
        return Response(
            content=content,
            media_type=XLSX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{export_filename(data, lang)}"'
            },
        )

    router.add_api_route(
        "/analytics/export",
        export_analytics,
        methods=["GET"],
        summary="Export the analytics view of a scope and period as an Excel workbook",
        response_class=Response,
        responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
    )
