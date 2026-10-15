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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.marketplace_settings_models import (
    PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID,
    PlatformMarketplaceSettingsRow,
)


@dataclass(frozen=True)
class StoredMarketplaceDefault:
    agents_publishing_enabled: bool
    agents_publish_quota: int
    updated_by: str | None
    updated_at: datetime | None


class PlatformMarketplaceSettingsStore:
    """CRUD over ``platform_marketplace_settings`` (at most one row). No
    authorization here; that is `marketplace_settings/service.py`'s job."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    @staticmethod
    def _select():
        return select(PlatformMarketplaceSettingsRow).where(
            PlatformMarketplaceSettingsRow.id
            == PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID
        )

    async def get(
        self, *, session: AsyncSession | None = None
    ) -> StoredMarketplaceDefault | None:
        async with use_session(self._sessions, session) as s:
            row = (await s.execute(self._select())).scalar_one_or_none()
            if row is None:
                return None
            return StoredMarketplaceDefault(
                agents_publishing_enabled=row.agents_publishing_enabled,
                agents_publish_quota=row.agents_publish_quota,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )

    async def set(
        self,
        *,
        agents_publishing_enabled: bool,
        agents_publish_quota: int,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredMarketplaceDefault:
        async with use_session(self._sessions, session) as s:
            # Waits for publications holding the share lock (agent marketplace store).
            row = (
                await s.execute(self._select().with_for_update())
            ).scalar_one_or_none()
            if row is None:
                row = PlatformMarketplaceSettingsRow(
                    id=PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID
                )
                s.add(row)
            row.agents_publishing_enabled = agents_publishing_enabled
            row.agents_publish_quota = agents_publish_quota
            row.updated_by = updated_by
            # Explicit: onupdate only fires on a dirty row.
            row.updated_at = utcnow()
            await s.flush()
            updated_at = row.updated_at
        return StoredMarketplaceDefault(
            agents_publishing_enabled=agents_publishing_enabled,
            agents_publish_quota=agents_publish_quota,
            updated_by=updated_by,
            updated_at=updated_at,
        )
