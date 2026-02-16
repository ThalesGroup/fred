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
from datetime import datetime, timezone
from typing import List

from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)

logger = logging.getLogger(__name__)


class PostgresSessionAttachmentStore(BaseSessionAttachmentStore):
    """
    PostgreSQL-backed storage for session attachments summaries.
    """

    def __init__(
        self, engine: AsyncEngine, table_name: str, prefix: str = "sessions_"
    ) -> None:
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("attachment_id", String, primary_key=True),
            Column("name", String, nullable=False),
            Column("mime", String, nullable=True),
            Column("size_bytes", Integer, nullable=True),
            Column("summary_md", Text, nullable=False),
            Column("document_uid", String, nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            keep_existing=True,
        )

        def _ensure_schema(sync_conn):
            metadata.create_all(sync_conn)
            insp = inspect(sync_conn)
            cols = {c["name"] for c in insp.get_columns(self.table_name)}
            if "document_uid" not in cols:
                sync_conn.execute(
                    text(
                        f'ALTER TABLE "{self.table_name}" '
                        "ADD COLUMN IF NOT EXISTS document_uid VARCHAR"
                    )
                )
                logger.info(
                    "[SESSION][PG] Added missing document_uid column to %s",
                    self.table_name,
                )

        import asyncio

        async def _create_async():
            try:
                await run_ddl_with_advisory_lock(
                    engine=self.store.engine,
                    lock_key=self._ddl_lock_id,
                    ddl_sync_fn=_ensure_schema,
                    logger=logger,
                )
                logger.info(
                    "[SESSION][PG] Attachments table ready: %s", self.table_name
                )
            except Exception:
                logger.exception(
                    "[SESSION][PG] Failed to ensure document_uid column on %s",
                    self.table_name,
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create_async())
        except RuntimeError:
            asyncio.run(_create_async())

    async def save(self, record: SessionAttachmentRecord) -> None:
        now = datetime.now(timezone.utc)
        created = record.created_at or now
        values = {
            "session_id": record.session_id,
            "attachment_id": record.attachment_id,
            "name": record.name,
            "mime": record.mime,
            "size_bytes": record.size_bytes,
            "summary_md": record.summary_md,
            "document_uid": record.document_uid,
            "created_at": created,
            "updated_at": record.updated_at or now,
        }
        async with self.store.begin() as conn:
            await self.store.upsert(
                conn,
                self.table,
                values=values,
                pk_cols=["session_id", "attachment_id"],
            )

    async def list_for_session(self, session_id: str) -> List[SessionAttachmentRecord]:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table)
                .where(self.table.c.session_id == session_id)
                .order_by(self.table.c.created_at.asc())
            )
            rows = result.fetchall()
        records: List[SessionAttachmentRecord] = []
        for row in rows:
            records.append(
                SessionAttachmentRecord(
                    session_id=row.session_id,
                    attachment_id=row.attachment_id,
                    name=row.name,
                    mime=row.mime,
                    size_bytes=row.size_bytes,
                    summary_md=row.summary_md,
                    document_uid=row.document_uid,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return records

    async def delete(self, session_id: str, attachment_id: str) -> None:
        async with self.store.begin() as conn:
            await conn.execute(
                self.table.delete().where(
                    self.table.c.session_id == session_id,
                    self.table.c.attachment_id == attachment_id,
                )
            )

    async def delete_for_session(self, session_id: str) -> None:
        async with self.store.begin() as conn:
            await conn.execute(
                self.table.delete().where(self.table.c.session_id == session_id)
            )

    async def count_for_sessions(self, session_ids: List[str]) -> int:
        if not session_ids:
            return 0
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(func.count())
                .select_from(self.table)
                .where(self.table.c.session_id.in_(session_ids))
            )
            return result.scalar() or 0
