# Copyright Thales 2025
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

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.session.session_schema import SessionSchema
from fred_core.session.stores.base_session_store import BaseSessionStore
from fred_core.session.stores.session_models import SessionRow
from fred_core.sql.async_session import make_session_factory, use_session


class PostgresSessionStore(BaseSessionStore):
    """ORM-backed Postgres session store.

    Uses SQLAlchemy ``AsyncSession`` and the ``session`` table managed by Alembic.
    The full ``SessionSchema`` is serialised into the ``session_data`` JSONB column;
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def save(
        self, session: SessionSchema, db_session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, db_session) as s:
            existing_row = await s.get(SessionRow, session.id)

            if existing_row:
                existing_row.session_data = session.model_dump(mode="json")
                existing_row.updated_at = session.updated_at
            else:
                new_row = SessionRow(
                    session_id=session.id,
                    user_id=session.user_id,
                    team_id=session.team_id,
                    agent_id=session.agent_id,
                    session_data=session.model_dump(mode="json"),
                    updated_at=session.updated_at,
                )
                s.add(new_row)

    async def get(
        self, session_id: str, db_session: AsyncSession | None = None
    ) -> SessionSchema | None:
        async with use_session(self._sessions, db_session) as s:
            row = await s.get(SessionRow, session_id)
        if row is None:
            return None
        return SessionSchema.model_validate(row.session_data)

    async def delete(
        self, session_id: str, db_session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, db_session) as s:
            row = await s.get(SessionRow, session_id)
            if row is not None:
                await s.delete(row)

    async def get_for_user(
        self,
        user_id: str,
        team_id: Optional[str],
        db_session: AsyncSession | None = None,
    ) -> list[SessionSchema]:
        async with use_session(self._sessions, db_session) as s:
            stmt = select(SessionRow).where(SessionRow.user_id == user_id)
            if team_id is not None:
                stmt = stmt.where(SessionRow.team_id == team_id)
            result = await s.execute(stmt.order_by(SessionRow.updated_at.desc()))
            rows = result.scalars().all()
        return [SessionSchema.model_validate(row.session_data) for row in rows]

    async def count_for_user(
        self, user_id: str, db_session: AsyncSession | None = None
    ) -> int:
        from sqlalchemy import func
        from sqlalchemy import select as sa_select

        async with use_session(self._sessions, db_session) as s:
            result = await s.execute(
                sa_select(func.count())
                .select_from(SessionRow)
                .where(SessionRow.user_id == user_id)
            )
            return int(result.scalar_one())
