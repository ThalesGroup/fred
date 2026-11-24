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

import asyncio
from typing import cast, get_args

from fred_core import KeycloakUser, OrganizationPermission
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.platform_ui_settings.schemas import (
    AdminFeaturedAgent,
    AdminHomeAgent,
    HomeAgentChoice,
    HomeLayout,
    PlatformHomeSettings,
    PlatformUiSettings,
    SetPlatformHomeRequest,
    SetPlatformUiSettingsRequest,
    UnknownFeaturedAgentError,
)
from control_plane_backend.platform_ui_settings.store import (
    StoredFeaturedAgent,
    StoredPlatformHome,
    StoredPlatformUiSettings,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies


async def _require_manage_platform(
    deps: ProductServiceDependencies, user: KeycloakUser
) -> None:
    # Same catch-all platform gate as announcements: a platform-wide presentation setting.
    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


def _to_settings(stored: StoredPlatformUiSettings | None) -> PlatformUiSettings:
    if stored is None:
        return PlatformUiSettings()
    return PlatformUiSettings(
        default_theme=stored.default_theme,
        hidden_themes=stored.hidden_themes,
        onboarding_tour_enabled=stored.onboarding_tour_enabled,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def get_platform_ui_settings(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformUiSettings:
    await _require_manage_platform(deps, user)
    return _to_settings(await deps.get_platform_ui_settings_store().get())


async def set_platform_ui_settings(
    *,
    user: KeycloakUser,
    request: SetPlatformUiSettingsRequest,
    deps: ProductServiceDependencies,
) -> PlatformUiSettings:
    await _require_manage_platform(deps, user)
    stored = await deps.get_platform_ui_settings_store().set(
        default_theme=request.default_theme,
        hidden_themes=request.hidden_themes,
        onboarding_tour_enabled=request.onboarding_tour_enabled,
        updated_by=user.uid,
    )
    emit_audit_log(
        "platform.ui_settings.updated",
        actor_uid=user.uid,
        default_theme=request.default_theme,
        hidden_themes=request.hidden_themes,
        onboarding_tour_enabled=request.onboarding_tour_enabled,
    )
    return _to_settings(stored)


def home_layout_or_classic(stored: str) -> HomeLayout:
    """A mode this backend does not know (written by a newer one) reads as classic."""
    return cast(HomeLayout, stored) if stored in get_args(HomeLayout) else "classic"


def is_featurable(record: AgentInstanceRecord, default_team_ids: set[str]) -> bool:
    """Enabled, not suspended, and in a default team: what users may see in the carousel."""
    return (
        record.enabled
        and record.suspension_reason is None
        and str(record.team_id) in default_team_ids
    )


def _saved_agent_ids(stored: StoredPlatformHome) -> list[str]:
    ids = [entry.agent_instance_id for entry in stored.featured]
    if stored.ask_agent_instance_id is not None:
        ids.append(stored.ask_agent_instance_id)
    return ids


async def _home_settings(
    deps: ProductServiceDependencies, stored: StoredPlatformHome
) -> PlatformHomeSettings:
    teams = deps.team_dependencies
    agent_store = deps.get_agent_instance_store()
    default_ids = await teams.get_default_team_store().list_team_ids()
    per_team, saved = await asyncio.gather(
        asyncio.gather(*(agent_store.list_by_team(TeamId(t)) for t in default_ids)),
        agent_store.get_many(_saved_agent_ids(stored)),
    )
    defaults = set(default_ids)
    candidates = sorted(
        (r for records in per_team for r in records if is_featurable(r, defaults)),
        key=lambda r: (r.display_name.casefold(), r.agent_instance_id),
    )
    team_ids = {str(r.team_id) for r in candidates} | {
        str(r.team_id) for r in saved.values()
    }
    names = await teams.get_team_metadata_store().get_by_team_ids(
        [TeamId(t) for t in team_ids]
    )

    def team_name(team_id: str) -> str | None:
        metadata = names.get(TeamId(team_id))
        return metadata.name if metadata is not None else None

    featured = [
        AdminFeaturedAgent(
            agent_instance_id=entry.agent_instance_id,
            display_name=record.display_name,
            team_id=str(record.team_id),
            team_name=team_name(str(record.team_id)),
            badge=entry.badge,
            highlights=entry.highlights,
            available=is_featurable(record, defaults),
        )
        for entry in stored.featured
        if (record := saved.get(entry.agent_instance_id)) is not None
    ]
    ask_record = (
        saved.get(stored.ask_agent_instance_id)
        if stored.ask_agent_instance_id is not None
        else None
    )
    ask_agent = (
        AdminHomeAgent(
            agent_instance_id=ask_record.agent_instance_id,
            display_name=ask_record.display_name,
            team_id=str(ask_record.team_id),
            team_name=team_name(str(ask_record.team_id)),
            available=is_featurable(ask_record, defaults),
        )
        if ask_record is not None
        else None
    )
    return PlatformHomeSettings(
        layout=home_layout_or_classic(stored.layout),
        featured=featured,
        ask_agent=ask_agent,
        candidates=[
            HomeAgentChoice(
                agent_instance_id=r.agent_instance_id,
                display_name=r.display_name,
                team_id=str(r.team_id),
                team_name=team_name(str(r.team_id)),
            )
            for r in candidates
        ],
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def get_platform_home(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformHomeSettings:
    await _require_manage_platform(deps, user)
    stored = await deps.get_platform_ui_settings_store().get_home()
    return await _home_settings(deps, stored)


async def set_platform_home(
    *,
    user: KeycloakUser,
    request: SetPlatformHomeRequest,
    deps: ProductServiceDependencies,
) -> PlatformHomeSettings:
    """Unknown agents are refused; unavailable ones may stay so other edits can be saved."""
    await _require_manage_platform(deps, user)
    ids = [entry.agent_instance_id for entry in request.featured]
    checked = ids + (
        [request.ask_agent_instance_id] if request.ask_agent_instance_id else []
    )
    found = await deps.get_agent_instance_store().get_many(checked)
    missing = next((agent_id for agent_id in checked if agent_id not in found), None)
    if missing is not None:
        raise UnknownFeaturedAgentError(missing)
    stored = await deps.get_platform_ui_settings_store().set_home(
        layout=request.layout,
        featured=[
            StoredFeaturedAgent(
                agent_instance_id=entry.agent_instance_id,
                badge=entry.badge,
                highlights=list(entry.highlights),
            )
            for entry in request.featured
        ],
        ask_agent_instance_id=request.ask_agent_instance_id,
        updated_by=user.uid,
    )
    emit_audit_log(
        "platform.home.updated",
        actor_uid=user.uid,
        layout=request.layout,
        featured=ids,
        ask_agent=request.ask_agent_instance_id,
    )
    return await _home_settings(deps, stored)
