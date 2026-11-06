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

from typing import Literal

from fred_core.sql import make_session_factory, use_session
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.users_preferences_models import UserPreferencesRow
from control_plane_backend.platform_ui_settings.schemas import UiThemeId

ThemeMode = Literal["light", "dark", "system"]
Language = Literal["en", "fr"]
TeamSortMode = Literal["recent", "alpha"]
AgentSort = Literal["name", "created_at:desc", "updated_at:desc"]


class UserPreferences(BaseModel):
    """Typed display choices returned by the self-service API."""

    model_config = ConfigDict(extra="forbid")

    initialized: bool = False
    ui_theme_id: str | None = None
    theme_mode: ThemeMode = "system"
    language: Language | None = None
    sidebar_collapsed: bool = False
    team_sort_mode: TeamSortMode = "recent"
    agent_sort: AgentSort = "name"


class PatchUserPreferences(BaseModel):
    """Omitted fields keep their saved value; null resets a field to its default."""

    model_config = ConfigDict(extra="forbid")

    ui_theme_id: UiThemeId | None = None
    theme_mode: ThemeMode | None = None
    language: Language | None = None
    sidebar_collapsed: bool | None = None
    team_sort_mode: TeamSortMode | None = None
    agent_sort: AgentSort | None = None

    @model_validator(mode="after")
    def _nonempty(self) -> PatchUserPreferences:
        if not self.model_fields_set:
            raise ValueError("at least one preference is required")
        return self


def _to_preferences(row: UserPreferencesRow | None) -> UserPreferences:
    if row is None:
        return UserPreferences()
    return UserPreferences.model_validate(
        {
            "initialized": True,
            "ui_theme_id": row.ui_theme_id,
            "theme_mode": row.theme_mode,
            "language": row.language,
            "sidebar_collapsed": row.sidebar_collapsed,
            "team_sort_mode": row.team_sort_mode,
            "agent_sort": row.agent_sort,
        }
    )


class UserPreferencesStore:
    """Read and patch only the authenticated subject's preference row."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    async def get(self, user_id: str) -> UserPreferences:
        async with use_session(self._sessions) as session:
            row = await session.scalar(
                select(UserPreferencesRow).where(UserPreferencesRow.user_id == user_id)
            )
            return _to_preferences(row)

    async def patch(self, user_id: str, patch: PatchUserPreferences) -> UserPreferences:
        async with use_session(self._sessions) as session:
            if self._engine.dialect.name == "postgresql":
                stmt = pg_insert(UserPreferencesRow).values(user_id=user_id)
            elif self._engine.dialect.name == "sqlite":
                stmt = sqlite_insert(UserPreferencesRow).values(user_id=user_id)
            else:
                raise RuntimeError("Unsupported preferences database")
            await session.execute(
                stmt.on_conflict_do_nothing(index_elements=["user_id"])
            )
            row = await session.scalar(
                select(UserPreferencesRow)
                .where(UserPreferencesRow.user_id == user_id)
                .with_for_update()
            )
            assert row is not None
            fields = patch.model_fields_set
            if "ui_theme_id" in fields:
                row.ui_theme_id = patch.ui_theme_id
            if "theme_mode" in fields:
                row.theme_mode = patch.theme_mode or "system"
            if "language" in fields:
                row.language = patch.language
            if "sidebar_collapsed" in fields:
                row.sidebar_collapsed = patch.sidebar_collapsed or False
            if "team_sort_mode" in fields:
                row.team_sort_mode = patch.team_sort_mode or "recent"
            if "agent_sort" in fields:
                row.agent_sort = patch.agent_sort or "name"
            row.updated_at = utcnow()
            await session.flush()
            return _to_preferences(row)

    async def delete(self, user_id: str) -> None:
        async with use_session(self._sessions) as session:
            await session.execute(
                delete(UserPreferencesRow).where(UserPreferencesRow.user_id == user_id)
            )
