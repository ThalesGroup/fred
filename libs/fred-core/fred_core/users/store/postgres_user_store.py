from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.sql import make_session_factory, use_session
from fred_core.users.user_models import GcuVersionsType, UserRow

from .base_user_store import BaseUserStore

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
