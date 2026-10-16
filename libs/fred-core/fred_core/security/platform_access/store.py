# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from fred_pod.security.platform_access import PlatformAccessPolicy
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import ColumnElement, delete, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.security.platform_access.models import (
    PlatformAccessLinkJoinerRow,
    PlatformAccessLinkRow,
    PlatformAccessSettingsRow,
    PlatformAccessUserRow,
)
from fred_core.security.platform_access.rules import Fact, path_key
from fred_core.sql import make_session_factory, use_session
from fred_core.sql.accent_folding import fold_accents, search_spellings
from fred_core.sql.base_sql import advisory_lock_key
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow

logger = logging.getLogger(__name__)
_WARNING_INTERVAL = 60.0
_last_warning: dict[str, float] = {}


def warn_unavailable(kind: str, error: BaseException) -> None:
    """Log why platform access answered 503, at most once a minute per kind.

    The limit is per kind: another cause of the same kind inside the window is
    not logged. Only the exception type and SQLSTATE: messages and statement
    parameters can carry link tokens."""
    now = time.monotonic()
    if now - _last_warning.get(kind, -_WARNING_INTERVAL) < _WARNING_INTERVAL:
        return
    _last_warning[kind] = now
    code = getattr(getattr(error, "orig", None), "pgcode", None)
    logger.warning(
        "Platform access %s unavailable: %s%s",
        kind,
        type(error).__name__,
        f" (SQLSTATE {code})" if code else "",
    )


class PlatformAccessStore:
    @staticmethod
    def projection(user: KeycloakUser, selected: set[str]) -> dict[str, Fact | None]:
        return {
            key: user.admission_claims.get(key)
            for key in sorted(selected)
            if path_key([]) not in user.admission_invalid_claims
            or key in user.admission_claims
            or key in user.admission_invalid_claims
        }

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.sessions = make_session_factory(engine)

    @asynccontextmanager
    async def read(
        self, session: AsyncSession | None = None
    ) -> AsyncIterator[AsyncSession]:
        try:
            async with asyncio.timeout(5):
                async with use_session(self.sessions, session) as active:
                    yield active
        except HTTPException:
            raise
        except Exception as error:
            warn_unavailable("store", error)
            raise HTTPException(503, "platform_access_unavailable") from None

    @asynccontextmanager
    async def mutation(self, key: str = "policy") -> AsyncIterator[AsyncSession]:
        async with self.read() as session:
            if self.engine.dialect.name == "postgresql":
                await session.execute(text("SET LOCAL lock_timeout = '5s'"))
                await session.execute(text("SET LOCAL statement_timeout = '5s'"))
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(f"platform_access:{key}")},
                )
            yield session

    async def settings(
        self, session: AsyncSession | None = None
    ) -> PlatformAccessSettingsRow | None:
        async with self.read(session) as s:
            return await s.get(PlatformAccessSettingsRow, 1)

    async def user(
        self, uid: UUID, session: AsyncSession | None = None
    ) -> UserRow | None:
        async with self.read(session) as s:
            return await s.get(UserRow, uid)

    async def exception(
        self, uid: UUID, session: AsyncSession | None = None
    ) -> PlatformAccessUserRow | None:
        async with self.read(session) as s:
            return await s.get(PlatformAccessUserRow, uid)

    async def teams(
        self, session: AsyncSession | None = None, *, eligible_only: bool = False
    ) -> list[TeamMetadataRow]:
        async with self.read(session) as s:
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

    async def free_joined_teams(
        self, user_id: UUID | None = None, session: AsyncSession | None = None
    ) -> dict[UUID, set[str]]:
        """Teams each person joined through a Free link: the only Free admission evidence."""
        async with self.read(session) as s:
            query = (
                select(
                    PlatformAccessLinkJoinerRow.user_id, PlatformAccessLinkRow.team_id
                )
                .join(
                    PlatformAccessLinkRow,
                    PlatformAccessLinkRow.id == PlatformAccessLinkJoinerRow.link_id,
                )
                .where(
                    PlatformAccessLinkRow.kind == "free",
                    PlatformAccessLinkJoinerRow.deleted_at.is_(None),
                )
                .distinct()
            )
            if user_id is not None:
                query = query.where(PlatformAccessLinkJoinerRow.user_id == user_id)
            joined: dict[UUID, set[str]] = {}
            for uid, team_id in (await s.execute(query)).all():
                joined.setdefault(uid, set()).add(team_id)
            return joined

    async def has_free_links(self, team_id: str) -> bool:
        async with self.read() as s:
            return bool(
                await s.scalar(
                    select(
                        select(PlatformAccessLinkRow.id)
                        .where(
                            PlatformAccessLinkRow.team_id == team_id,
                            PlatformAccessLinkRow.kind == "free",
                        )
                        .exists()
                    )
                )
            )

    async def forget_free_joins(
        self, team_id: str, user_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """Leaving a team ends its Free source: only a new Free enrollment restores it."""
        async with self.read(session) as s:
            links = select(PlatformAccessLinkRow.id).where(
                PlatformAccessLinkRow.team_id == team_id,
                PlatformAccessLinkRow.kind == "free",
            )
            await s.execute(
                delete(PlatformAccessLinkJoinerRow).where(
                    PlatformAccessLinkJoinerRow.user_id == user_id,
                    PlatformAccessLinkJoinerRow.link_id.in_(links),
                )
            )

    @staticmethod
    def user_search(query: str) -> ColumnElement[bool]:
        # Accents and case are ignored on both sides: "helene" finds "Hélène" and back.
        # The typed text is bound and folded by the database, exactly like the columns.
        patterns = [
            fold_accents(literal(spelling)) for spelling in search_spellings(query)
        ]
        return or_(
            *(
                fold_accents(column).contains(pattern)
                for column in (
                    UserRow.username,
                    UserRow.email,
                    UserRow.first_name,
                    UserRow.last_name,
                )
                for pattern in patterns
            )
        )

    @staticmethod
    def user_filter(query: str) -> list[ColumnElement[bool]]:
        if not query:
            return []
        try:
            return [UserRow.id == UUID(query)]
        except ValueError:
            return [PlatformAccessStore.user_search(query)]

    async def users_with_exceptions(
        self,
        offset: int,
        limit: int | None,
        query: str = "",
        session: AsyncSession | None = None,
        *,
        exceptions_only: bool = False,
        identities_only: bool = False,
    ) -> list[tuple[UserRow, PlatformAccessUserRow | None]]:
        """One page of users, each with their individual exception when they hold one."""
        async with self.read(session) as s:
            # Explicit NULLS LAST: PostgreSQL and SQLite disagree on the default.
            alphabetical = (
                func.lower(UserRow.username).asc().nulls_last(),
                UserRow.id,
            )
            statement = (
                select(UserRow, PlatformAccessUserRow)
                .join(
                    PlatformAccessUserRow,
                    PlatformAccessUserRow.user_id == UserRow.id,
                    isouter=not exceptions_only,
                )
                .where(*self.user_filter(query))
            )
            if identities_only:
                statement = statement.where(UserRow.username.is_not(None))
            # The whitelist reads newest grant first; a batch shares one date and stays alphabetical.
            statement = (
                statement.order_by(
                    PlatformAccessUserRow.granted_at.desc(), *alphabetical
                )
                if exceptions_only
                else statement.order_by(*alphabetical)
            )
            result = await s.execute(statement.offset(offset).limit(limit))
            return [(user, exception) for user, exception in result.all()]

    async def users(
        self,
        offset: int,
        limit: int,
        query: str = "",
        session: AsyncSession | None = None,
        *,
        exceptions_only: bool = False,
    ) -> list[UserRow]:
        page = await self.users_with_exceptions(
            offset, limit, query, session, exceptions_only=exceptions_only
        )
        return [user for user, _ in page]

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

    async def observe(
        self, user: KeycloakUser, policy: PlatformAccessPolicy | None
    ) -> UserRow:
        uid = UUID(user.uid)
        selected = (
            {path_key(condition.claim) for condition in policy.conditions}
            if policy
            else set()
        )
        projection = self.projection(user, selected)
        row = await self.user(uid)
        issued = user.admission_issued_at
        if row is not None and row.admission_issued_at is not None:
            if issued is None or issued < row.admission_issued_at:
                return row
            if (
                issued == row.admission_issued_at
                and row.admission_attribute == projection
                and row.admission_expires_at == user.admission_expires_at
            ):
                return row
        # Write evidence under the policy lock so an old request cannot restore old paths.
        async with self.mutation() as session:
            state = await self.settings(session)
            if state is None:
                raise RuntimeError("Missing admission policy authority")
            current = (
                PlatformAccessPolicy.model_validate(state.policy)
                if state.policy is not None
                else None
            )
            selected = (
                {path_key(condition.claim) for condition in current.conditions}
                if current
                else set()
            )
            projection = self.projection(user, selected)
            row = await self.user(uid, session)
            if row is None:
                row = UserRow(
                    id=uid,
                    username=user.username,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    last_seen_at=datetime.now(timezone.utc),
                )
                session.add(row)
            if issued is not None:
                previous = row.admission_attribute or {}
                if row.admission_issued_at is None or issued > row.admission_issued_at:
                    row.username, row.email = user.username, user.email
                    row.first_name, row.last_name = user.first_name, user.last_name
                    row.last_seen_at = datetime.now(timezone.utc)
                    row.admission_conflicted = False
                    row.admission_attribute = projection
                    row.admission_issued_at = issued
                    row.admission_expires_at = user.admission_expires_at
                elif issued == row.admission_issued_at:
                    # Newly selected paths are observable with the same verified token.
                    if row.admission_expires_at != user.admission_expires_at or any(
                        previous[key] != projection[key]
                        for key in previous.keys() & projection.keys()
                    ):
                        row.admission_conflicted = True
                    row.admission_attribute = projection
            await session.flush()
            return row

    async def user_count(
        self,
        query: str = "",
        *,
        exceptions_only: bool = False,
        identities_only: bool = False,
    ) -> int:
        async with self.read() as session:
            statement = select(func.count()).select_from(UserRow)
            if exceptions_only:
                statement = statement.join(
                    PlatformAccessUserRow, PlatformAccessUserRow.user_id == UserRow.id
                )
            if identities_only:
                statement = statement.where(UserRow.username.is_not(None))
            return int(
                (await session.scalar(statement.where(*self.user_filter(query)))) or 0
            )

    async def team(self, team_id: str, session: AsyncSession) -> TeamMetadataRow | None:
        return await session.get(TeamMetadataRow, team_id)

    async def link(
        self, token_hash: str, session: AsyncSession
    ) -> tuple[PlatformAccessLinkRow, TeamMetadataRow] | None:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(PlatformAccessLinkRow, TeamMetadataRow)
            .join(TeamMetadataRow, TeamMetadataRow.id == PlatformAccessLinkRow.team_id)
            .where(
                PlatformAccessLinkRow.token_hash == token_hash,
                PlatformAccessLinkRow.revoked_at.is_(None),
                or_(
                    PlatformAccessLinkRow.expires_at.is_(None),
                    PlatformAccessLinkRow.expires_at > now,
                ),
                or_(
                    (PlatformAccessLinkRow.kind == "team")
                    & PlatformAccessLinkRow.paused.is_(False),
                    (PlatformAccessLinkRow.kind == "free")
                    & TeamMetadataRow.platform_access_free.is_(True),
                ),
                ~TeamMetadataRow.id.startswith("personal-"),
            )
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row is not None else None
