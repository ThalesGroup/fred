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

import asyncio
import logging
from typing import Any

from fred_core.sql import AsyncBaseSqlStore, advisory_lock_key, run_ddl_with_advisory_lock
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.core.stores.tabular_dataset_registry.base_tabular_dataset_registry_store import (
    BaseTabularDatasetRegistryStore,
)
from knowledge_flow_backend.core.stores.tabular_dataset_registry.structures import (
    TabularDatasetRecord,
)

logger = logging.getLogger(__name__)


class PostgresTabularDatasetRegistryStore(BaseTabularDatasetRegistryStore):
    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("document_uid", String, primary_key=True),
            Column("db_name", String, nullable=False, index=True),
            Column("physical_table_name", String, nullable=False, unique=True, index=True),
            Column("query_alias", String, nullable=False, unique=True, index=True),
            Column("display_name", String, nullable=False),
            Column("row_count", Integer, nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            keep_existing=True,
        )

        async def _create():
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=metadata.create_all,
                logger=logger,
            )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[TABULAR_DATASET_REGISTRY][PG][ASYNC] Table ready: %s", self.table_name)

    @staticmethod
    def _from_row(row: Any) -> TabularDatasetRecord:
        values = row._mapping
        return TabularDatasetRecord(
            document_uid=values["document_uid"],
            db_name=values["db_name"],
            physical_table_name=values["physical_table_name"],
            query_alias=values["query_alias"],
            display_name=values["display_name"],
            row_count=values["row_count"],
            created_at=values["created_at"],
            updated_at=values["updated_at"],
        )

    async def get_by_document_uid(self, document_uid: str) -> TabularDatasetRecord | None:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table).where(self.table.c.document_uid == document_uid))
            row = result.fetchone()
        return self._from_row(row) if row else None

    async def get_by_query_alias(self, query_alias: str) -> TabularDatasetRecord | None:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table).where(self.table.c.query_alias == query_alias))
            row = result.fetchone()
        return self._from_row(row) if row else None

    async def list_by_document_uids(self, document_uids: list[str]) -> list[TabularDatasetRecord]:
        if not document_uids:
            return []
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table).where(self.table.c.document_uid.in_(document_uids)))
            rows = result.fetchall()
        return [self._from_row(row) for row in rows]

    async def list_all(self) -> list[TabularDatasetRecord]:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table))
            rows = result.fetchall()
        return [self._from_row(row) for row in rows]

    async def upsert(self, dataset: TabularDatasetRecord) -> TabularDatasetRecord:
        values = dataset.model_dump()
        async with self.store.begin() as conn:
            await self.store.upsert(conn, self.table, values, pk_cols=["document_uid"])
        return dataset

    async def delete_by_document_uid(self, document_uid: str) -> None:
        async with self.store.begin() as conn:
            await conn.execute(self.table.delete().where(self.table.c.document_uid == document_uid))
