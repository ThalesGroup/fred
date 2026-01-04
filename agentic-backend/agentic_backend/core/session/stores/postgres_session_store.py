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

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fred_core.sql import BaseSqlStore
from sqlalchemy import Column, DateTime, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from agentic_backend.core.session.stores.base_session_store import BaseSessionStore
from agentic_backend.core.chatbot.chat_schema import SessionSchema

logger = logging.getLogger(__name__)


class PostgresSessionStore(BaseSessionStore):
    """
    PostgreSQL-backed session store using JSONB.
    """

    def __init__(self, engine: Engine, table_name: str, prefix: str = "sessions_"):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("user_id", String, index=True),
            Column("agent_name", String, index=True),
            Column("session_data", JSONB),
            Column("updated_at", DateTime(timezone=True), index=True),
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[SESSION][PG] Table ready: %s", self.table_name)

    def save(self, session: SessionSchema) -> None:
        payload: Dict[str, Any] = session.model_dump(mode="json")
        with self.store.begin() as conn:
            self.store.upsert(
                conn,
                self.table,
                values={
                    "session_id": session.id,
                    "user_id": session.user_id,
                    "agent_name": payload.get("agent_name", ""),
                    "session_data": payload,
                    "updated_at": session.updated_at,
                },
                pk_cols=["session_id"],
            )

    def get(self, session_id: str) -> Optional[SessionSchema]:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.session_data).where(self.table.c.session_id == session_id)
            ).fetchone()
        if not row:
            return None
        return SessionSchema.model_validate(row[0])

    def delete(self, session_id: str) -> None:
        with self.store.begin() as conn:
            conn.execute(self.table.delete().where(self.table.c.session_id == session_id))

    def get_for_user(self, user_id: str) -> List[SessionSchema]:
        with self.store.begin() as conn:
            rows = conn.execute(
                select(self.table.c.session_data)
                .where(self.table.c.user_id == user_id)
                .order_by(self.table.c.updated_at.desc())
            ).fetchall()
        return [SessionSchema.model_validate(r[0]) for r in rows]
