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
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.agent_marketplace.notifications import notify_unpublished
from control_plane_backend.agent_marketplace.store import (
    RemovalReason,
    RemovedEntry,
    emit_unpublished,
)
from control_plane_backend.marketplace_settings.effective import (
    count_published_agents,
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
from control_plane_backend.notifications.service import display_name
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
    team_ids = [team.id for team in teams]
    published_counts = await count_published_agents(
        team_ids, deps.get_agent_marketplace_store
    )
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
                published_count=published_counts.get(team.id, 0),
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


async def _impact(
    deps: TeamServiceDependencies, team_ids: list[TeamId]
) -> MarketplaceSettingsImpact:
    published_counts = await count_published_agents(
        team_ids, deps.get_agent_marketplace_store
    )
    return MarketplaceSettingsImpact(
        affected_team_ids=team_ids,
        removed_published_agents=sum(published_counts.values()),
    )


async def _apply_switch_off(
    deps: TeamServiceDependencies, team_ids: list[TeamId], session: AsyncSession
) -> tuple[MarketplaceSettingsImpact, list[RemovedEntry]]:
    """Take down the published agents of teams whose switch turned off."""
    if deps.get_agent_marketplace_store is None or not team_ids:
        return MarketplaceSettingsImpact(affected_team_ids=team_ids), []
    removed = await deps.get_agent_marketplace_store().remove_team_entries(
        team_ids, RemovalReason.SWITCH_OFF, session=session
    )
    return (
        MarketplaceSettingsImpact(
            affected_team_ids=team_ids, removed_published_agents=len(removed)
        ),
        removed,
    )


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
    return await _impact(deps, affected)


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
    team_store = deps.get_team_metadata_store()
    async with team_store.transaction() as session:
        async with team_store.advisory_lock(
            "agents_marketplace_settings", session=session
        ):
            before = await load_marketplace_default(store, session=session)
            await store().set(
                agents_publishing_enabled=request.agents_publishing_enabled,
                agents_publish_quota=request.agents_publish_quota,
                updated_by=user.uid,
                session=session,
            )
            teams = await team_store.list_all(session=session)
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
            impact, removed = await _apply_switch_off(deps, affected, session)
    emit_unpublished(removed, actor_uid=user.uid)
    await notify_unpublished(
        deps.get_notification_service() if deps.get_notification_service else None,
        removed,
        actor_uid=user.uid,
        actor_name=display_name(user),
    )
    emit_audit_log(
        "marketplace.settings.default_updated",
        actor_uid=user.uid,
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
        removed_published_agents=impact.removed_published_agents,
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
    return await _impact(deps, affected)


async def set_team_marketplace_settings(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: SetTeamMarketplaceSettingsRequest,
    deps: TeamServiceDependencies,
) -> MarketplaceSettingsUpdateResult:
    await _require_manage_platform(deps, user)
    team_store = deps.get_team_metadata_store()
    async with team_store.transaction() as session:
        async with team_store.advisory_lock(
            "agents_marketplace_settings", session=session
        ):
            team = await team_store.get_by_team_id(team_id, session=session)
            if team is None:
                raise TeamNotFoundError(team_id)
            default = await load_marketplace_default(
                deps.get_marketplace_settings_store, session=session
            )
            affected = (
                [team.id]
                if _turned_off(default, team, _with_overrides(team, request))
                else []
            )
            updated = await team_store.set_marketplace_overrides(
                team_id,
                agents_publishing_enabled=request.agents_publishing_enabled,
                agents_publish_quota=request.agents_publish_quota,
                session=session,
            )
            if updated is None:
                raise TeamNotFoundError(team_id)
            impact, removed = await _apply_switch_off(deps, affected, session)
    emit_unpublished(removed, actor_uid=user.uid)
    await notify_unpublished(
        deps.get_notification_service() if deps.get_notification_service else None,
        removed,
        actor_uid=user.uid,
        actor_name=display_name(user),
    )
    emit_audit_log(
        "marketplace.settings.team_updated",
        actor_uid=user.uid,
        team_id=str(team_id),
        agents_publishing_enabled=request.agents_publishing_enabled,
        agents_publish_quota=request.agents_publish_quota,
        removed_published_agents=impact.removed_published_agents,
    )
    return MarketplaceSettingsUpdateResult(
        settings=await _build_settings(deps, default), impact=impact
    )
