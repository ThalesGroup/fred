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

import logging
from datetime import datetime, timezone
from typing import Optional, cast
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.sql import make_session_factory, use_session
from fred_core.users.user_models import GcuVersionsType, UserRow

from .base_user_store import AmbiguousUsernameError, BaseUserStore

logger = logging.getLogger(__name__)

_user_store: BaseUserStore | None = None


class StoreNotInitializedError(RuntimeError):
    def __init__(self):
        super().__init__(
            "UserStore is not initialized. "
            "Make sure init_user_store() is called during application startup."
        )


def init_user_store(async_engine: AsyncEngine) -> None:
    global _user_store
    _user_store = PostgresUserStore(engine=async_engine)


def get_user_store() -> BaseUserStore:
    if _user_store is None:
        raise StoreNotInitializedError()
    return _user_store


class PostgresUserStore(BaseUserStore):
    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)

    async def save(self, user: UserRow) -> None:
        pass

    @staticmethod
    def _identity_dict(user: UserRow) -> dict[str, str | None]:
        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "firstName": user.first_name,
            "lastName": user.last_name,
        }

    async def upsert_identity(
        self,
        user_id: UUID,
        username: str,
        email: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        values = {
            "username": username,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "last_seen_at": datetime.now(timezone.utc),
        }
        async with use_session(self._sessions) as session:
            result = await session.execute(
                update(UserRow).where(UserRow.id == user_id).values(**values)
            )
            if cast(CursorResult, result).rowcount:
                return
            try:
                async with session.begin_nested():
                    session.add(UserRow(id=user_id, **values))
                    await session.flush()
            except IntegrityError:
                await session.execute(
                    update(UserRow).where(UserRow.id == user_id).values(**values)
                )

    async def search_identities(
        self, query: str, limit: int
    ) -> list[dict[str, str | None]]:
        pattern = f"%{query}%"
        fields = (
            UserRow.username,
            UserRow.email,
            UserRow.first_name,
            UserRow.last_name,
        )
        async with use_session(self._sessions) as session:
            rows = (
                await session.scalars(
                    select(UserRow)
                    .where(UserRow.username.is_not(None))
                    .where(or_(*(field.ilike(pattern) for field in fields)))
                    .order_by(UserRow.username, UserRow.id)
                    .limit(limit)
                )
            ).all()
        return [self._identity_dict(row) for row in rows]

    async def list_identities(
        self, offset: int, limit: int
    ) -> list[dict[str, str | None]]:
        async with use_session(self._sessions) as session:
            rows = (
                await session.scalars(
                    select(UserRow)
                    .where(UserRow.username.is_not(None))
                    .order_by(UserRow.username, UserRow.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        return [self._identity_dict(row) for row in rows]

    async def get_identities(self, ids: list[UUID]) -> list[dict[str, str | None]]:
        if not ids:
            return []
        async with use_session(self._sessions) as session:
            rows = (
                await session.scalars(
                    select(UserRow).where(
                        UserRow.id.in_(ids), UserRow.username.is_not(None)
                    )
                )
            ).all()
        by_id = {row.id: self._identity_dict(row) for row in rows}
        return [by_id[user_id] for user_id in ids if user_id in by_id]

    async def count_identities(self) -> int:
        async with use_session(self._sessions) as session:
            count = await session.scalar(
                select(func.count())
                .select_from(UserRow)
                .where(UserRow.username.is_not(None))
            )
        return count or 0

    async def find_ids_by_usernames(
        self, usernames: list[str] | None = None
    ) -> dict[str, str]:
        stmt = select(UserRow).where(UserRow.username.is_not(None))
        if usernames is not None:
            if not usernames:
                return {}
            stmt = stmt.where(
                func.lower(UserRow.username).in_([name.lower() for name in usernames])
            )
        async with use_session(self._sessions) as session:
            rows = (await session.scalars(stmt)).all()
        resolved: dict[str, str] = {}
        ambiguous: set[str] = set()
        for row in rows:
            if row.username is None:
                continue
            user_id = str(row.id)
            if row.username in resolved and resolved[row.username] != user_id:
                ambiguous.add(row.username)
            resolved[row.username] = user_id
        if ambiguous:
            # SQL matches case-insensitively; consumers resolve exact names.
            requested = (
                ambiguous if usernames is None else ambiguous.intersection(usernames)
            )
            if requested:
                raise AmbiguousUsernameError(list(requested))
            for username in ambiguous:
                resolved.pop(username, None)
        return resolved

    async def identity_exists(self, user_id: UUID) -> bool:
        async with use_session(self._sessions) as session:
            value = await session.scalar(
                select(UserRow.id).where(
                    UserRow.id == user_id, UserRow.username.is_not(None)
                )
            )
        return value is not None

    async def find_user_by_id(
        self, user_id: UUID, session: AsyncSession | None = None
    ) -> Optional[UserRow]:
        async with use_session(self._sessions, session) as s:
            result = await s.execute(select(UserRow).where(UserRow.id == user_id))
        return result.scalar_one_or_none()

    async def update_gcu_version(
        self,
        user_id: UUID,
        gcu_version: GcuVersionsType,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            user = await s.get(UserRow, user_id)

            if user is None:
                user = UserRow(
                    id=user_id,
                    gcuVersionAccepted=gcu_version,
                    gcuAcceptedAt=datetime.now(),
                )
                s.add(user)
            else:
                user.gcuVersionAccepted = gcu_version
                user.gcuAcceptedAt = datetime.now()

    async def increment_current_storage_size(
        self,
        user_id: UUID,
        delta: int,
        session: AsyncSession | None = None,
    ) -> None:
        """Increment current storage size of a user by a delta (can be negative).

        The result is clamped at 0: personal usage is a byte count, so a negative
        value is always accounting drift rather than a real state, and letting it
        go negative would hand the user free quota. The clamp logs a warning so the
        drift stays visible instead of being silently absorbed (#2149).

        The update is a single atomic `UPDATE ... SET col = col + :delta`, not a
        read-modify-write: personal-space releases fan out concurrently the same
        way team releases do, and loading the row then writing back an absolute
        value lost decrements under concurrency (#2149 review finding).
        """
        async with use_session(self._sessions, session) as s:
            # CASE, not GREATEST/MAX — see the note in TeamMetadataStore; the same
            # portability constraint applies here.
            new_value = func.coalesce(UserRow.current_resources_storage_size, 0) + delta
            result = await s.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(
                    current_resources_storage_size=case(
                        (new_value < 0, 0), else_=new_value
                    )
                )
                .returning(UserRow.current_resources_storage_size)
            )
            updated = result.scalar_one_or_none()
            if updated is not None:
                if delta < 0 and updated == 0:
                    logger.warning(
                        "Storage accounting for user '%s' reached 0 (delta=%d); if this was a clamp, usage had drifted",
                        user_id,
                        delta,
                    )
                return

            # No row yet. Insert one, but treat a concurrent insert as the normal
            # case rather than an error: two releases for the same unseen user race
            # here, and the loser must fold its delta into the winner's row instead
            # of failing the delete that triggered it.
            if delta < 0:
                logger.warning(
                    "Storage release for unknown user '%s' (delta=%d); recording 0 rather than a negative usage",
                    user_id,
                    delta,
                )
            try:
                async with s.begin_nested():
                    s.add(
                        UserRow(
                            id=user_id,
                            gcuVersionAccepted=None,
                            gcuAcceptedAt=None,
                            current_resources_storage_size=max(0, delta),
                        )
                    )
            except IntegrityError:
                await s.execute(
                    update(UserRow)
                    .where(UserRow.id == user_id)
                    .values(
                        current_resources_storage_size=case(
                            (new_value < 0, 0), else_=new_value
                        )
                    )
                )
