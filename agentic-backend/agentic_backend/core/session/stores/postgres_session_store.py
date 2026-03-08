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

from typing import Any, List, Optional

from fred_core import BaseSessionStore
from fred_core.session.stores import BaseJsonSessionStore, PostgresJsonSessionStore
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.core.chatbot.chat_schema import SessionSchema


class PostgresSessionStore(BaseSessionStore):
    """Agentic wrapper around the shared Postgres JSON session store."""

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "sessions_"):
        self._store: BaseJsonSessionStore = PostgresJsonSessionStore(
            engine=engine,
            table_name=table_name,
            prefix=prefix,
        )

    async def save(self, session: SessionSchema) -> None:
        payload = session.model_dump(mode="json")
        await self._store.save(
            session_id=session.id,
            user_id=session.user_id,
            updated_at=session.updated_at,
            payload=payload,
            team_id=payload.get("team_id"),
            agent_id=payload.get("agent_id", ""),
        )

    async def save_with_conn(self, conn: Any, session: SessionSchema) -> None:
        payload = session.model_dump(mode="json")
        await self._store.save_with_conn(
            conn,
            session_id=session.id,
            user_id=session.user_id,
            updated_at=session.updated_at,
            payload=payload,
            team_id=payload.get("team_id"),
            agent_id=payload.get("agent_id", ""),
        )

    async def get(self, session_id: str) -> Optional[SessionSchema]:
        payload = await self._store.get_payload(session_id)
        if payload is None:
            return None
        return SessionSchema.model_validate(payload)

    async def delete(self, session_id: str) -> None:
        await self._store.delete(session_id)

    async def get_for_user(self, user_id: str) -> List[SessionSchema]:
        payloads = await self._store.get_payloads_for_user(user_id)
        return [SessionSchema.model_validate(payload) for payload in payloads]

    async def count_for_user(self, user_id: str) -> int:
        return await self._store.count_for_user(user_id)
