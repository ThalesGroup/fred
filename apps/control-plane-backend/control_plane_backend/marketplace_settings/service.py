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

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID
from fred_core.teams.metadata_store import TeamMetadata

from control_plane_backend.marketplace_settings.effective import (
    effective_marketplace_settings,
    load_marketplace_default,
)
from control_plane_backend.marketplace_settings.schemas import (
    AgentsMarketplaceDefault,
    MarketplaceSettings,
    MarketplaceSettingsImpact,
    MarketplaceSettingsUpdateResult,
    SetAgentsMarketplaceDefaultRequest,
    SetTeamMarketplaceSettingsRequest,
    TeamMarketplaceSettings,
)
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import TeamNotFoundError


async def _require_manage_platform(
    deps: TeamServiceDependencies, user: KeycloakUser
) -> None:
    await deps.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


async def _build_settings(
    deps: TeamServiceDependencies, default: AgentsMarketplaceDefault
) -> MarketplaceSettings:
    teams = await deps.get_team_metadata_store().list_all()
    rows: list[TeamMarketplaceSettings] = []
    for team in sorted(teams, key=lambda team: team.name.lower()):
        effective = effective_marketplace_settings(default, team)
        rows.append(
            TeamMarketplaceSettings(
                team_id=team.id,
                team_name=team.name,
                agents_publishing_enabled_override=team.agents_publishing_enabled,
                agents_publish_quota_override=team.agents_publish_quota,
                agents_publishing_enabled=effective.agents_publishing_enabled,
                agents_publish_quota=effective.agents_publish_quota,
            )
        )
    return MarketplaceSettings(default=default, teams=rows)


def _turned_off(
    default: AgentsMarketplaceDefault,
    before: TeamMetadata,
    after: TeamMetadata,
    *,
    default_switch_after: bool | None = None,
) -> bool:
    was_on = effective_marketplace_settings(default, before).agents_publishing_enabled
    is_on = effective_marketplace_settings(
        default, after, agents_publishing_enabled=default_switch_after
    ).agents_publishing_enabled
    return was_on and not is_on


def _with_overrides(
    team: TeamMetadata, request: SetTeamMarketplaceSettingsRequest
) -> TeamMetadata:
    return team.model_copy(
        update={
            "agents_publishing_enabled": request.agents_publishing_enabled,
            "agents_publish_quota": request.agents_publish_quota,
        }
    )


async def _require_team(deps: TeamServiceDependencies, team_id: TeamId) -> TeamMetadata:
    team = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if team is None:
        raise TeamNotFoundError(team_id)
    return team


async def get_marketplace_settings(
    *, user: KeycloakUser, deps: TeamServiceDependencies
) -> MarketplaceSettings:
    await _require_manage_platform(deps, user)
    default = await load_marketplace_default(deps.get_marketplace_settings_store)
    return await _build_settings(deps, default)


async def preview_default_change(
    *,
    user: KeycloakUser,
    agents_publishing_enabled: bool,
    deps: TeamServiceDependencies,
) -> MarketplaceSettingsImpact:
    await _require_manage_platform(deps, user)
    default = await load_marketplace_default(deps.get_marketplace_settings_store)
    teams = await deps.get_team_metadata_store().list_all()
    affected = [
        team.id
        for team in teams
        if _turned_off(
            default, team, team, default_switch_after=agents_publishing_enabled
        )
    ]
    return MarketplaceSettingsImpact(affected_team_ids=affected)


async def set_marketplace_default(
    *,
    user: KeycloakUser,
    request: SetAgentsMarketplaceDefaultRequest,
    deps: TeamServiceDependencies,
) -> MarketplaceSettingsUpdateResult:
    await _require_manage_platform(deps, user)
    store = deps.get_marketplace_settings_store
    if store is None:
        raise RuntimeError("marketplace settings store is not configured")
    before = await load_marketplace_default(store)
    teams = await deps.get_team_metadata_store().list_all()
    affected = [
        team.id
        for team in teams
        if _turned_off(
            before,
            team,
            team,
            default_switch_after=request.agents_publishing_enabled,
        )
    ]
    # Saved first: a publication racing this change then reads the new switch.
    await store().set(
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
        updated_by=user.uid,
    )
    impact = MarketplaceSettingsImpact(affected_team_ids=affected)
    emit_audit_log(
        "marketplace.settings.default_updated",
        actor_uid=user.uid,
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
    )
    default = await load_marketplace_default(store)
    return MarketplaceSettingsUpdateResult(
        settings=await _build_settings(deps, default), impact=impact
    )


async def preview_team_change(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agents_publishing_enabled: bool | None,
    deps: TeamServiceDependencies,
) -> MarketplaceSettingsImpact:
    await _require_manage_platform(deps, user)
    team = await _require_team(deps, team_id)
    default = await load_marketplace_default(deps.get_marketplace_settings_store)
    after = team.model_copy(
        update={"agents_publishing_enabled": agents_publishing_enabled}
    )
    affected = [team.id] if _turned_off(default, team, after) else []
    return MarketplaceSettingsImpact(affected_team_ids=affected)


async def set_team_marketplace_settings(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: SetTeamMarketplaceSettingsRequest,
    deps: TeamServiceDependencies,
) -> MarketplaceSettingsUpdateResult:
    await _require_manage_platform(deps, user)
    team = await _require_team(deps, team_id)
    default = await load_marketplace_default(deps.get_marketplace_settings_store)
    affected = (
        [team.id] if _turned_off(default, team, _with_overrides(team, request)) else []
    )
    updated = await deps.get_team_metadata_store().set_marketplace_overrides(
        team_id,
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
    )
    if updated is None:
        raise TeamNotFoundError(team_id)
    impact = MarketplaceSettingsImpact(affected_team_ids=affected)
    emit_audit_log(
        "marketplace.settings.team_updated",
        actor_uid=user.uid,
        team_id=str(team_id),
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
    )
    return MarketplaceSettingsUpdateResult(
        settings=await _build_settings(deps, default), impact=impact
    )
