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
from typing import Any, List, Optional, cast

from fred_core.sql import AsyncBaseSqlStore, PydanticJsonMixin, json_for_engine
from pydantic import ValidationError
from sqlalchemy import ARRAY, Column, DateTime, Index, MetaData, String, Table, delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)


class PostgresMetadataStore(BaseMetadataStore, PydanticJsonMixin):
    """
    PostgreSQL-backed metadata store using JSONB + array columns.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        table_name: str,
        prefix: str,
    ):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._is_postgres = self.store.engine.dialect.name == "postgresql"

        json_type = json_for_engine(self.store.engine)
        tag_ids_type = ARRAY(String) if self._is_postgres else json_type

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("document_uid", String, primary_key=True),
            Column("source_tag", String, index=True),
            Column("date_added_to_kb", DateTime(timezone=True)),
            Column("tag_ids", tag_ids_type),
            Column("doc", json_type),
            keep_existing=True,
        )

        # Helpful indexes for filters (GIN for array lookups on Postgres)
        if self._is_postgres:
            Index(
                f"idx_{self.table_name}_tag_ids_gin",
                self.table.c.tag_ids,
                postgresql_using="gin",
            )

        async def _create():
            async with self.store.engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(metadata.create_all)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[METADATA][PG][ASYNC] Table ready: %s", self.table_name)

    # ---------- helpers ----------

    @staticmethod
    def _to_dict(md: DocumentMetadata) -> dict[str, Any]:
        return md.model_dump(mode="json")

    @staticmethod
    def _from_dict(data: Any) -> DocumentMetadata:
        try:
            return DocumentMetadata.model_validate(data or {})
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata JSON: {e}") from e

    @staticmethod
    def _require_uid(md: DocumentMetadata) -> str:
        uid = md.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")
        return uid

    # ---------- reads ----------

    async def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc).where(self.table.c.document_uid == document_uid))
            row = result.fetchone()
        return self._from_dict(row[0]) if row else None

    async def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc).where(self.table.c.source_tag == source_tag))
            rows = result.fetchall()
        return [self._from_dict(r[0]) for r in rows]

    async def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(ColumnElement[bool], self.store.array_contains(self.table.c.tag_ids, tag_id))
            async with self.store.begin() as conn:
                result = await conn.execute(select(self.table.c.doc).where(cond))
                rows = result.fetchall()
            return [self._from_dict(r[0]) for r in rows]

        # SQLite / other: load all and filter in Python
        docs = await self.get_all_metadata(filters={})
        return [md for md in docs if tag_id in (md.tags.tag_ids or [])]

    async def browse_metadata_in_tag(self, tag_id: str, offset: int = 0, limit: int = 50) -> tuple[list[DocumentMetadata], int]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(ColumnElement[bool], self.store.array_contains(self.table.c.tag_ids, tag_id))
            async with self.store.begin() as conn:
                total_result = await conn.execute(select(func.count()).select_from(self.table).where(cond))
                total = total_result.scalar_one()
                rows_result = await conn.execute(select(self.table.c.doc).where(cond).limit(limit).offset(offset))
                rows = rows_result.fetchall()
            docs = [self._from_dict(r[0]) for r in rows]
            return docs, int(total)

        # SQLite / other: filter in Python
        docs = await self.get_all_metadata(filters={})
        filtered = [md for md in docs if tag_id in (md.tags.tag_ids or [])]
        total = len(filtered)
        return filtered[offset : offset + limit], total

    async def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Load all documents then filter in Python for nested keys (parity with DuckDB store).
        """
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table.c.doc))
            rows = result.fetchall()
        docs = [self._from_dict(r[0]) for r in rows]
        return [md for md in docs if self._match_nested(md.model_dump(mode="json"), filters)]

    # ---------- writes ----------

    async def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = self._require_uid(metadata)
        values = {
            "document_uid": uid,
            "source_tag": metadata.source.source_tag,
            "date_added_to_kb": metadata.source.date_added_to_kb,
            "tag_ids": list(metadata.tags.tag_ids or []),
            "doc": self._to_dict(metadata),
        }
        async with self.store.begin() as conn:
            await self.store.upsert(conn, self.table, values, pk_cols=["document_uid"])

    async def delete_metadata(self, document_uid: str) -> None:
        async with self.store.begin() as conn:
            result = await conn.execute(delete(self.table).where(self.table.c.document_uid == document_uid))
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    async def clear(self) -> None:
        async with self.store.begin() as conn:
            await conn.execute(delete(self.table))

    # --- helper: nested filter (copied from DuckDB store for parity) ---

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        """
        Recursively match a filter dict against a nested dict (string-compare for robustness).
        Mirrors the DuckDB/OpenSearch semantics to keep callers consistent.
        """
        for key, value in filter_dict.items():
            if key == "processing_stages" and isinstance(value, dict):
                stages = item.get("processing", {}).get("stages", {})
                if not isinstance(stages, dict):
                    return False

                for stage_key, expected in value.items():
                    current = stages.get(stage_key)
                    if isinstance(expected, list):
                        if isinstance(current, list):
                            if not any(str(c) in map(str, expected) for c in current):
                                return False
                        else:
                            if str(current) not in map(str, expected):
                                return False
                    else:
                        if str(current) != str(expected):
                            return False
                continue

            if isinstance(value, dict):
                sub = item.get(key, {})
                if not isinstance(sub, dict) or not self._match_nested(sub, value):
                    return False
            else:
                cur = item.get(key, None)
                if cur is None:
                    if key in {"document_name", "document_uid"}:
                        cur = item.get("identity", {}).get(key)
                    elif key in {"source_tag", "retrievable"}:
                        cur = item.get("source", {}).get(key)
                    elif key == "tag_ids":
                        cur = item.get("tags", {}).get("tag_ids")

                if isinstance(value, list):
                    if isinstance(cur, list):
                        if not any(str(c) in map(str, value) for c in cur):
                            return False
                    else:
                        if str(cur) not in map(str, value):
                            return False
                else:
                    if str(cur) != str(value):
                        return False

        return True
