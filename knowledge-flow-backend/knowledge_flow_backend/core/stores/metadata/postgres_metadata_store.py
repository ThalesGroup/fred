from __future__ import annotations

import logging
from typing import Any, List, Optional

from pydantic import ValidationError
from sqlalchemy import ARRAY, Column, DateTime, Index, MetaData, String, Table, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from fred_core.sql import BaseSqlStore
from fred_core.sql import PydanticJsonMixin
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
        engine: Engine,
        table_name: str = "metadata_v2",
        prefix: str = "metadata_",
    ):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("document_uid", String, primary_key=True),
            Column("source_tag", String, index=True),
            Column("date_added_to_kb", DateTime(timezone=True)),
            Column("tag_ids", ARRAY(String)),
            Column("doc", JSONB),
            keep_existing=True,
        )

        # Helpful indexes for filters (GIN for array lookups)
        Index(f"idx_{self.table_name}_tag_ids_gin", self.table.c.tag_ids, postgresql_using="gin")

        metadata.create_all(self.store.engine)
        logger.info("[METADATA][PG] Table ready: %s", self.table_name)

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

    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table.c.doc).where(self.table.c.document_uid == document_uid)
            ).fetchone()
        return self._from_dict(row[0]) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store.begin() as conn:
            rows = conn.execute(
                select(self.table.c.doc).where(self.table.c.source_tag == source_tag)
            ).fetchall()
        return [self._from_dict(r[0]) for r in rows]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        cond = self.store.array_contains(self.table.c.tag_ids, tag_id)
        with self.store.begin() as conn:
            rows = conn.execute(select(self.table.c.doc).where(cond)).fetchall()
        return [self._from_dict(r[0]) for r in rows]

    def browse_metadata_in_tag(
        self, tag_id: str, offset: int = 0, limit: int = 50
    ) -> tuple[list[DocumentMetadata], int]:
        cond = self.store.array_contains(self.table.c.tag_ids, tag_id)
        with self.store.begin() as conn:
            total = conn.execute(
                select(func.count()).select_from(self.table).where(cond)
            ).scalar_one()
            rows = conn.execute(
                select(self.table.c.doc).where(cond).limit(limit).offset(offset)
            ).fetchall()
        docs = [self._from_dict(r[0]) for r in rows]
        return docs, int(total)

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Load all documents then filter in Python for nested keys (parity with DuckDB store).
        """
        with self.store.begin() as conn:
            rows = conn.execute(select(self.table.c.doc)).fetchall()
        docs = [self._from_dict(r[0]) for r in rows]
        return [md for md in docs if self._match_nested(md.model_dump(mode="json"), filters)]

    # ---------- writes ----------

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = self._require_uid(metadata)
        values = {
            "document_uid": uid,
            "source_tag": metadata.source.source_tag,
            "date_added_to_kb": metadata.source.date_added_to_kb,
            "tag_ids": list(metadata.tags.tag_ids or []),
            "doc": self._to_dict(metadata),
        }
        with self.store.begin() as conn:
            self.store.upsert(conn, self.table, values, pk_cols=["document_uid"])

    def delete_metadata(self, document_uid: str) -> None:
        with self.store.begin() as conn:
            result = conn.execute(
                delete(self.table).where(self.table.c.document_uid == document_uid)
            )
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    def clear(self) -> None:
        with self.store.begin() as conn:
            conn.execute(delete(self.table))

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
