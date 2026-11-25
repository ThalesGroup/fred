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

from dataclasses import dataclass
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.platform_ui_settings_models import (
    PLATFORM_UI_SETTINGS_SINGLETON_ID,
    PlatformHomeFeaturedAgentRow,
    PlatformUiSettingsRow,
)


@dataclass(frozen=True)
class StoredPlatformUiSettings:
    """The stored platform UI settings row."""

    default_theme: str | None
    hidden_themes: list[str]
    onboarding_tour_enabled: bool
    updated_by: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class StoredFeaturedAgent:
    """One saved carousel agent, in display order."""

    agent_instance_id: str
    badge: str | None
    highlights: list[str]


@dataclass(frozen=True)
class StoredPlatformHome:
    """The stored home mode and featured agents."""

    layout: str
    featured: list[StoredFeaturedAgent]
    ask_agent_instance_id: str | None
    updated_by: str | None
    updated_at: datetime | None


class PlatformUiSettingsStore:
    """CRUD over ``platform_ui_settings`` (at most one row). No authorization here;
    that is `platform_ui_settings/service.py`'s job, as for `PlatformPromptStore`."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(
        self, *, session: AsyncSession | None = None
    ) -> StoredPlatformUiSettings | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(PlatformUiSettingsRow).where(
                        PlatformUiSettingsRow.id == PLATFORM_UI_SETTINGS_SINGLETON_ID
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return StoredPlatformUiSettings(
                default_theme=row.default_theme,
                hidden_themes=list(row.hidden_themes),
                onboarding_tour_enabled=row.onboarding_tour_enabled,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )

    async def set(
        self,
        *,
        default_theme: str | None,
        hidden_themes: list[str],
        updated_by: str | None,
        onboarding_tour_enabled: bool = True,
        session: AsyncSession | None = None,
    ) -> StoredPlatformUiSettings:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(PlatformUiSettingsRow).where(
                        PlatformUiSettingsRow.id == PLATFORM_UI_SETTINGS_SINGLETON_ID
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = PlatformUiSettingsRow(id=PLATFORM_UI_SETTINGS_SINGLETON_ID)
                s.add(row)
            row.default_theme = default_theme
            row.hidden_themes = list(hidden_themes)
            row.onboarding_tour_enabled = onboarding_tour_enabled
            row.updated_by = updated_by
            # Explicit, as in PlatformPromptStore: onupdate only fires on a dirty row.
            row.updated_at = utcnow()
            await s.flush()
            updated_at = row.updated_at
        return StoredPlatformUiSettings(
            default_theme=default_theme,
            hidden_themes=list(hidden_themes),
            onboarding_tour_enabled=onboarding_tour_enabled,
            updated_by=updated_by,
            updated_at=updated_at,
        )

    async def get_home(
        self, *, session: AsyncSession | None = None
    ) -> StoredPlatformHome:
        """Home mode ("classic" when never set), featured agents in order and question agent."""
        async with use_session(self._sessions, session) as s:
            settings = await s.get(
                PlatformUiSettingsRow, PLATFORM_UI_SETTINGS_SINGLETON_ID
            )
            rows = (
                (
                    await s.execute(
                        select(PlatformHomeFeaturedAgentRow).order_by(
                            PlatformHomeFeaturedAgentRow.position
                        )
                    )
                )
                .scalars()
                .all()
            )
            return StoredPlatformHome(
                layout=settings.home_layout if settings is not None else "classic",
                featured=[
                    StoredFeaturedAgent(
                        agent_instance_id=row.agent_instance_id,
                        badge=row.badge,
                        highlights=list(row.highlights),
                    )
                    for row in rows
                ],
                ask_agent_instance_id=(
                    settings.home_ask_agent_instance_id
                    if settings is not None
                    else None
                ),
                updated_by=settings.updated_by if settings is not None else None,
                updated_at=settings.updated_at if settings is not None else None,
            )

    async def set_home(
        self,
        *,
        layout: str,
        featured: list[StoredFeaturedAgent],
        ask_agent_instance_id: str | None,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredPlatformHome:
        """Replace the home mode, featured list and question agent in one transaction."""
        async with use_session(self._sessions, session) as s:
            settings = await s.get(
                PlatformUiSettingsRow, PLATFORM_UI_SETTINGS_SINGLETON_ID
            )
            if settings is None:
                settings = PlatformUiSettingsRow(id=PLATFORM_UI_SETTINGS_SINGLETON_ID)
                s.add(settings)
            settings.home_layout = layout
            settings.home_ask_agent_instance_id = ask_agent_instance_id
            settings.updated_by = updated_by
            settings.updated_at = utcnow()
            await s.execute(delete(PlatformHomeFeaturedAgentRow))
            s.add_all(
                PlatformHomeFeaturedAgentRow(
                    agent_instance_id=entry.agent_instance_id,
                    position=position,
                    badge=entry.badge,
                    highlights=list(entry.highlights),
                    updated_by=updated_by,
                )
                for position, entry in enumerate(featured)
            )
            await s.flush()
            updated_at = settings.updated_at
        return StoredPlatformHome(
            layout=layout,
            featured=list(featured),
            ask_agent_instance_id=ask_agent_instance_id,
            updated_by=updated_by,
            updated_at=updated_at,
        )
