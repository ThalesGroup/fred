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

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    get_current_user,
)
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.export import add_export_route
from control_plane_backend.kpi.presets import PRESETS
from control_plane_backend.kpi.scope import resolve_kpi_scope
from control_plane_backend.kpi.user_filter import (
    UserFilterParam,
    UserFilterSummary,
    parse_user_filter,
    user_filter_summary,
)
from control_plane_backend.kpi.utils import Bucket


def get_kpi_store(request: Request) -> OpenSearchKPIStore:
    container = get_application_container(request)
    store = container.get_kpi_store()
    if store is None:
        raise HTTPException(status_code=503, detail="KPI store not available")
    return store


def build_kpi_router() -> APIRouter:
    router = APIRouter(prefix="/kpi", tags=["KPI"])

    for preset in PRESETS:

        def make_handler(p=preset):
            async def handler(
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
                    description=(
                        "Scope the query to these teams instead of the whole platform "
                        "(repeat the parameter). Platform observers may pass any teams; "
                        "others need can_read_members on each. Rejected with 400 for "
                        "presets whose data carries no team dimension."
                    ),
                ),
                bucket: Bucket = Query(
                    default="auto",
                    description="Calendar bucket of over-time presets; auto follows the period length.",
                ),
                tz: str = Query(
                    default="Europe/Paris",
                    description="IANA time zone of calendar buckets and days (over-time presets).",
                ),
                user_filter: UserFilterParam = None,
                user: KeycloakUser = Depends(get_current_user),
                store: OpenSearchKPIStore = Depends(get_kpi_store),
            ):
                if team_ids and not p.team_scopable:
                    raise HTTPException(
                        status_code=400,
                        detail=f"preset {p.name!r} does not support team_ids scoping",
                    )
                parsed_filter = parse_user_filter(user_filter)
                if parsed_filter is not None and not p.user_filterable:
                    raise HTTPException(
                        status_code=400,
                        detail=f"preset {p.name!r} does not support user_filter",
                    )
                # Single authorization chokepoint: handlers never check permissions.
                scope = await resolve_kpi_scope(
                    request,
                    user,
                    team_ids,
                    self_scoped=p.self_scoped,
                    user_filter=parsed_filter,
                )

                now = datetime.now(tz=timezone.utc)
                resolved_since = since or (now - timedelta(days=30))
                resolved_until = until or now
                kwargs: dict[str, Any] = dict(
                    user=user,
                    since=resolved_since,
                    until=resolved_until,
                    request=request,
                )
                if p.team_scopable:
                    kwargs["team_ids"] = scope.team_ids
                if p.user_filterable:
                    kwargs["user_ids"] = scope.user_ids
                if p.bucketable or p.zoned:
                    try:
                        ZoneInfo(tz)
                    except (ZoneInfoNotFoundError, ValueError, OSError):
                        raise HTTPException(
                            status_code=400, detail=f"unknown time zone {tz!r}"
                        ) from None
                    kwargs["tz"] = tz
                if p.bucketable:
                    kwargs["bucket"] = bucket
                return await p.handler(store, **kwargs)

            return handler

        router.add_api_route(
            f"/presets/{preset.name}",
            make_handler(),
            methods=["GET"],
            response_model=preset.response_model,
            summary=preset.summary,
            response_model_exclude_none=True,
        )

    @router.get(
        "/user-filter",
        response_model=UserFilterSummary,
        summary="Account attribute paths a user filter can use, and how many users a filter matches",
    )
    async def get_user_filter_summary(
        request: Request,
        user_filter: UserFilterParam = None,
        user: KeycloakUser = Depends(get_current_user),
    ) -> UserFilterSummary:
        rebac = get_application_container(request).get_rebac_engine()
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID
        )
        return await user_filter_summary(parse_user_filter(user_filter))

    add_export_route(router, get_kpi_store)
    return router
