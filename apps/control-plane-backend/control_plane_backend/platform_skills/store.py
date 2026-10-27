# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Shared per-skill state with atomic updates on PostgreSQL and local SQLite."""

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.platform_skill_policy_models import (
    PlatformSkillPolicyRow,
)


class PlatformSkillPolicyStore:
    """Persist global activation; services own authorization and catalog validation."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Reuse the configured engine and its connection pool for policy reads."""
        self._engine = engine
        self._sessions = make_session_factory(engine)

    async def list_disabled_skill_names(
        self, *, session: AsyncSession | None = None
    ) -> set[str]:
        """Resolve fresh opt-outs for a turn, optionally in its existing read session."""
        async with use_session(self._sessions, session) as s:
            names = await s.scalars(
                select(PlatformSkillPolicyRow.skill_name).where(
                    PlatformSkillPolicyRow.enabled.is_(False)
                )
            )
            return set(names)

    async def get_enabled(
        self, name: str, *, session: AsyncSession | None = None
    ) -> bool | None:
        """Read one stored state by primary key; None distinguishes an unknown name."""
        async with use_session(self._sessions, session) as s:
            return await s.scalar(
                select(PlatformSkillPolicyRow.enabled).where(
                    PlatformSkillPolicyRow.skill_name == name
                )
            )

    async def set_enabled(
        self,
        *,
        name: str,
        enabled: bool,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> bool:
        """Atomically update one skill; concurrent writes never replace other names."""
        insert = (
            pg_insert if self._engine.dialect.name == "postgresql" else sqlite_insert
        )
        statement = insert(PlatformSkillPolicyRow).values(
            skill_name=name, enabled=enabled, updated_by=updated_by, updated_at=utcnow()
        )
        statement = statement.on_conflict_do_update(
            index_elements=[PlatformSkillPolicyRow.skill_name],
            set_={
                "enabled": statement.excluded.enabled,
                "updated_by": statement.excluded.updated_by,
                "updated_at": statement.excluded.updated_at,
            },
        )
        async with use_session(self._sessions, session) as s:
            await s.execute(statement)
        return enabled
