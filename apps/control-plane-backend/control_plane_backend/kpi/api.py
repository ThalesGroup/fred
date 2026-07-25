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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId
from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.kpi.presets import PRESETS
from control_plane_backend.kpi.scope import resolve_kpi_scope


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
                team_id: TeamId | None = Query(
                    default=None,
                    description=(
                        "Scope the query to one team instead of the whole platform. "
                        "Requires can_read_members on that team. Only accepted for "
                        "presets whose underlying data actually carries a team "
                        "dimension — others reject it with 400."
                    ),
                ),
                user: KeycloakUser = Depends(get_current_user),
                store: OpenSearchKPIStore = Depends(get_kpi_store),
            ):
                if team_id is not None and not p.team_scopable:
                    raise HTTPException(
                        status_code=400,
                        detail=f"preset {p.name!r} does not support team_id scoping",
                    )
                # Single authorization chokepoint for every preset (§2.3/§2.4,
                # KPI-ANALYTICS-RFC.md v3) — handlers never check permissions
                # themselves.
                scope = await resolve_kpi_scope(request, user, team_id)

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
                    kwargs["team_id"] = scope.team_id
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

    return router
