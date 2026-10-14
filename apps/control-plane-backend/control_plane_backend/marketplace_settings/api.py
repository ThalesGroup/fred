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

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fred_core import KeycloakUser, get_current_user
from fred_core.common import TeamId

from control_plane_backend.marketplace_settings import service
from control_plane_backend.marketplace_settings.schemas import (
    MarketplaceSettings,
    MarketplaceSettingsImpact,
    MarketplaceSettingsUpdateResult,
    SetAgentsMarketplaceDefaultRequest,
    SetTeamMarketplaceSettingsRequest,
)
from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    get_team_service_dependencies,
)

router = APIRouter(tags=["MarketplaceSettings"])
TeamDependencies = Annotated[
    TeamServiceDependencies, Depends(get_team_service_dependencies)
]


@router.get(
    "/admin/marketplace-settings",
    response_model=MarketplaceSettings,
    summary="Get the agents marketplace default and every team's settings (platform admin).",
)
async def get_marketplace_settings(
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceSettings:
    return await service.get_marketplace_settings(user=user, deps=deps)


@router.get(
    "/admin/marketplace-settings/default/impact",
    response_model=MarketplaceSettingsImpact,
    summary="Preview what changing default publication would remove (platform admin).",
)
async def preview_marketplace_default_change(
    deps: TeamDependencies,
    agents_publishing_enabled: bool = Query(...),
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceSettingsImpact:
    return await service.preview_default_change(
        user=user, agents_publishing_enabled=agents_publishing_enabled, deps=deps
    )


@router.put(
    "/admin/marketplace-settings/default",
    response_model=MarketplaceSettingsUpdateResult,
    summary="Replace the agents marketplace default (platform admin).",
)
async def set_marketplace_default(
    request: SetAgentsMarketplaceDefaultRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceSettingsUpdateResult:
    return await service.set_marketplace_default(user=user, request=request, deps=deps)


@router.get(
    "/admin/teams/{team_id}/marketplace-settings/impact",
    response_model=MarketplaceSettingsImpact,
    summary="Preview what a team's publication change would remove; omit the switch for Default (platform admin).",
)
async def preview_team_marketplace_settings_change(
    team_id: TeamId,
    deps: TeamDependencies,
    agents_publishing_enabled: bool | None = Query(default=None),
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceSettingsImpact:
    return await service.preview_team_change(
        user=user,
        team_id=team_id,
        agents_publishing_enabled=agents_publishing_enabled,
        deps=deps,
    )


@router.put(
    "/admin/teams/{team_id}/marketplace-settings",
    response_model=MarketplaceSettingsUpdateResult,
    summary="Replace a team's agents marketplace overrides; null = back to Default (platform admin).",
)
async def set_team_marketplace_settings(
    team_id: TeamId,
    request: SetTeamMarketplaceSettingsRequest,
    deps: TeamDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> MarketplaceSettingsUpdateResult:
    return await service.set_team_marketplace_settings(
        user=user, team_id=team_id, request=request, deps=deps
    )
