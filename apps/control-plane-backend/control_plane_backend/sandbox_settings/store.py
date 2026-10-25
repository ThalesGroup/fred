# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.sandbox_settings_models import SandboxSettingsRow


@dataclass(frozen=True)
class StoredSandboxSettings:
    idle_minutes: int
    max_active_sessions: int
    updated_by: str | None = None
    updated_at: datetime | None = None


class SandboxSettingsStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(self) -> StoredSandboxSettings:
        async with use_session(self._sessions) as session:
            row = await session.scalar(
                select(SandboxSettingsRow).where(SandboxSettingsRow.id == "default")
            )
            return self._stored(row)

    async def set(
        self,
        *,
        idle_minutes: int,
        max_active_sessions: int,
        updated_by: str,
    ) -> StoredSandboxSettings:
        async with use_session(self._sessions) as session:
            row = await session.scalar(
                select(SandboxSettingsRow).where(SandboxSettingsRow.id == "default")
            )
            if row is None:
                row = SandboxSettingsRow(id="default")
                session.add(row)
            row.idle_minutes = idle_minutes
            row.max_active_sessions = max_active_sessions
            row.updated_by = updated_by
            row.updated_at = utcnow()
            await session.flush()
            return self._stored(row)

    @staticmethod
    def _stored(row: SandboxSettingsRow | None) -> StoredSandboxSettings:
        if row is None:
            return StoredSandboxSettings(20, 8)
        return StoredSandboxSettings(
            row.idle_minutes,
            row.max_active_sessions,
            row.updated_by,
            row.updated_at,
        )
