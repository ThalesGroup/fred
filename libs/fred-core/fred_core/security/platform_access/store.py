# SPDX-License-Identifier: Apache-2.0
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fred_pod.security.structure import KeycloakUser
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.security.platform_access.models import (
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.sql import make_session_factory, use_session
from fred_core.sql.base_sql import advisory_lock_key
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow


class PlatformAccessStore:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.sessions = make_session_factory(engine)

    @asynccontextmanager
    async def mutation(self, key: str = "policy") -> AsyncIterator[AsyncSession]:
        async with use_session(self.sessions) as session:
            if self.engine.dialect.name == "postgresql":
                await session.execute(text("SET LOCAL lock_timeout = '5s'"))
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(f"platform_access:{key}")},
                )
            yield session

    async def settings(
        self, session: AsyncSession | None = None
    ) -> PlatformAccessSettingsRow | None:
        async with use_session(self.sessions, session) as s:
            return await s.get(PlatformAccessSettingsRow, 1)

    async def user(
        self, uid: UUID, session: AsyncSession | None = None
    ) -> UserRow | None:
        async with use_session(self.sessions, session) as s:
            return await s.get(UserRow, uid)

    async def exception(
        self, uid: UUID, session: AsyncSession | None = None
    ) -> PlatformAccessUserRow | None:
        async with use_session(self.sessions, session) as s:
            return await s.get(PlatformAccessUserRow, uid)

    async def teams(
        self, session: AsyncSession | None = None, *, eligible_only: bool = False
    ) -> list[TeamMetadataRow]:
        async with use_session(self.sessions, session) as s:
            query = select(TeamMetadataRow).where(
                ~TeamMetadataRow.id.startswith("personal-")
            )
            if eligible_only:
                query = query.where(
                    or_(
                        TeamMetadataRow.platform_access_allowed,
                        TeamMetadataRow.platform_access_free,
                    )
                )
            return list((await s.scalars(query.order_by(TeamMetadataRow.id))).all())

    async def users(
        self,
        offset: int,
        limit: int,
        query: str = "",
        session: AsyncSession | None = None,
    ) -> list[UserRow]:
        async with use_session(self.sessions, session) as s:
            statement = select(UserRow)
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(UserRow.username.ilike(pattern), UserRow.email.ilike(pattern))
                )
            return list(
                (
                    await s.scalars(
                        statement.order_by(UserRow.id).offset(offset).limit(limit)
                    )
                ).all()
            )

    async def add_exception(
        self, uid: UUID, actor: str, source: str, session: AsyncSession
    ) -> None:
        if await self.exception(uid, session) is None:
            session.add(
                PlatformAccessUserRow(
                    user_id=uid,
                    source=source,
                    granted_by=actor,
                    granted_at=datetime.now(timezone.utc),
                )
            )

    async def observe(self, user: KeycloakUser, path: str) -> UserRow:
        uid = UUID(user.uid)
        row = await self.user(uid)
        if (
            row is not None
            and row.admission_claim_path == path
            and row.admission_issued_at is not None
        ):
            if (
                user.admission_issued_at is None
                or user.admission_issued_at < row.admission_issued_at
            ):
                return row
            if (
                user.admission_issued_at == row.admission_issued_at
                and row.admission_attribute == user.admission_attribute
                and row.admission_expires_at == user.admission_expires_at
            ):
                return row
        async with self.mutation(f"observation:{uid}") as s:
            row = await self.user(uid, s)
            if row is None:
                row = UserRow(
                    id=uid,
                    username=user.username,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    last_seen_at=datetime.now(timezone.utc),
                )
                s.add(row)
            issued = user.admission_issued_at
            if issued is not None:
                same_path = row.admission_claim_path == path
                if (
                    not same_path
                    or row.admission_issued_at is None
                    or issued > row.admission_issued_at
                ):
                    row.username, row.email = user.username, user.email
                    row.first_name, row.last_name = user.first_name, user.last_name
                    row.last_seen_at = datetime.now(timezone.utc)
                    row.admission_attribute = user.admission_attribute
                    row.admission_claim_path = path
                    row.admission_issued_at = issued
                    row.admission_expires_at = user.admission_expires_at
                    row.admission_conflicted = False
                elif issued == row.admission_issued_at and (
                    row.admission_attribute != user.admission_attribute
                    or row.admission_expires_at != user.admission_expires_at
                ):
                    row.admission_conflicted = True
            await s.flush()
            return row

    async def user_count(self, query: str = "") -> int:
        async with use_session(self.sessions) as session:
            statement = select(func.count()).select_from(UserRow)
            if query:
                statement = statement.where(
                    or_(
                        UserRow.username.ilike(f"%{query}%"),
                        UserRow.email.ilike(f"%{query}%"),
                    )
                )
            return int((await session.scalar(statement)) or 0)

    async def team(self, team_id: str, session: AsyncSession) -> TeamMetadataRow | None:
        return await session.get(TeamMetadataRow, team_id)

    async def link_team(
        self, token_hash: str, session: AsyncSession
    ) -> TeamMetadataRow | None:
        return await session.scalar(
            select(TeamMetadataRow).where(
                TeamMetadataRow.enrollment_token_hash == token_hash,
                TeamMetadataRow.platform_access_free.is_(True),
                ~TeamMetadataRow.id.startswith("personal-"),
            )
        )
