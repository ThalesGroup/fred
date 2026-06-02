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
from typing import Any, List, Optional, cast

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)
from knowledge_flow_backend.core.stores.metadata.metadata_models import MetadataRow

logger = logging.getLogger(__name__)


class PostgresMetadataStore(BaseMetadataStore):
    """PostgreSQL-backed metadata store using declarative ORM."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)
        self._is_postgres = engine.dialect.name == "postgresql"

    # ---------- helpers ----------

    @staticmethod
    def _to_dict(md: DocumentMetadata) -> dict[str, Any]:
        return md.model_dump(mode="json")

    @staticmethod
    def _from_row(row: MetadataRow) -> DocumentMetadata:
        try:
            return DocumentMetadata.model_validate(row.doc or {})
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata JSON: {e}") from e

    @staticmethod
    def _require_uid(md: DocumentMetadata) -> str:
        uid = md.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")
        return uid

    # ---------- reads ----------

    async def get_metadata_by_uid(self, document_uid: str, session: AsyncSession | None = None) -> Optional[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            row = await s.get(MetadataRow, document_uid)
        return self._from_row(row) if row else None

    async def get_metadata_by_uids(self, document_uids: list[str], session: AsyncSession | None = None) -> list[DocumentMetadata]:
        """
        Return metadata documents for one targeted uid list with one SQL query.

        Why this exists:
        - High-cardinality authorization paths should fetch only the documents
          already authorized by ReBAC instead of scanning the full metadata
          table and filtering afterwards.

        How to use:
        - Pass the readable document uids for one request.
        - The returned list preserves the input uid order for the uids that
          exist in storage.

        Example:
        - `docs = await store.get_metadata_by_uids(["doc-1", "doc-2"])`
        """
        unique_uids = list(dict.fromkeys(document_uids))
        if not unique_uids:
            return []

        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(MetadataRow).where(MetadataRow.document_uid.in_(unique_uids)))).scalars().all()

        row_by_uid = {row.document_uid: row for row in rows}
        return [self._from_row(row_by_uid[document_uid]) for document_uid in unique_uids if document_uid in row_by_uid]

    async def list_by_source_tag(self, source_tag: str, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(MetadataRow).where(MetadataRow.source_tag == source_tag))).scalars().all()
        return [self._from_row(row) for row in rows]

    async def get_metadata_in_tag(self, tag_id: str, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(ColumnElement[bool], MetadataRow.tag_ids.contains([tag_id]))
            async with use_session(self._sessions, session) as s:
                rows = (await s.execute(select(MetadataRow).where(cond))).scalars().all()
            return [self._from_row(row) for row in rows]

        # SQLite: load all and filter in Python
        docs = await self.get_all_metadata(filters={}, session=session)
        return [md for md in docs if tag_id in (md.tags.tag_ids or [])]

    async def browse_metadata_in_tag(self, tag_id: str, offset: int = 0, limit: int = 50, session: AsyncSession | None = None) -> tuple[list[DocumentMetadata], int]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(ColumnElement[bool], MetadataRow.tag_ids.contains([tag_id]))
            async with use_session(self._sessions, session) as s:
                total_result = await s.execute(select(func.count()).select_from(MetadataRow).where(cond))
                total = total_result.scalar_one()
                rows = (await s.execute(select(MetadataRow).where(cond).limit(limit).offset(offset))).scalars().all()
            return [self._from_row(row) for row in rows], int(total)

        # SQLite: filter in Python
        docs = await self.get_all_metadata(filters={}, session=session)
        filtered = [md for md in docs if tag_id in (md.tags.tag_ids or [])]
        return filtered[offset : offset + limit], len(filtered)

    async def get_all_metadata(self, filters: dict, session: AsyncSession | None = None) -> List[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(MetadataRow))).scalars().all()
        docs = [self._from_row(row) for row in rows]
        return [md for md in docs if self._match_nested(md.model_dump(mode="json"), filters)]

    # ---------- writes ----------

    async def save_metadata(self, metadata: DocumentMetadata, session: AsyncSession | None = None) -> None:
        uid = self._require_uid(metadata)
        async with use_session(self._sessions, session) as s:
            row = await s.get(MetadataRow, uid)
            if row is None:
                row = MetadataRow(document_uid=uid)
                s.add(row)
            row.source_tag = metadata.source.source_tag
            row.date_added_to_kb = metadata.source.date_added_to_kb
            row.tag_ids = list(metadata.tags.tag_ids or [])
            row.doc = self._to_dict(metadata)

    async def delete_metadata(self, document_uid: str, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(MetadataRow, document_uid)
            if row is None:
                raise ValueError(f"No document found with UID {document_uid}")
            await s.delete(row)

    async def clear(self, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(delete(MetadataRow))

    # --- helper: nested filter ---

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
