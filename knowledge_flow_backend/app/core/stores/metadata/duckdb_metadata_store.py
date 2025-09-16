# app/core/stores/metadata/duckdb_metadata_store.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import ValidationError

from app.common.document_structures import DocumentMetadata
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)


class DuckdbMetadataStore(BaseMetadataStore):
    """
    Minimal, robust DuckDB store:
      - One JSON blob column 'doc' with the full DocumentMetadata (authoritative)
      - A few 'hot' columns for fast filters: document_uid (PK), source_tag, tag_ids (JSON array), date_added_to_kb
    Query strategy:
      - get_metadata_by_uid: direct hit on PK
      - list_by_source_tag: simple WHERE on source_tag
      - get_metadata_in_tag: json_each(tag_ids)
      - get_all_metadata: dev-friendly load-all + in-memory filter (as before)
    """

    def __init__(self, db_path: Path):
        self.table_name = "metadata_v2"
        self.store = DuckDBTableStore(db_path, prefix="metadata_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # ---------- schema ----------

    def _ensure_schema(self) -> None:
        """
        Schema: compact + future-proof.
        """
        full_table = self._table()
        sql = f"""
            CREATE TABLE IF NOT EXISTS {full_table} (
                document_uid TEXT PRIMARY KEY,
                source_tag   TEXT,
                date_added_to_kb TIMESTAMP,
                tag_ids      JSON,      -- JSON ARRAY of strings
                doc          JSON       -- full DocumentMetadata JSON blob
            );
        """
        with self.store._connect() as conn:
            conn.execute(sql)
            # Normalize legacy bad tag_ids (string -> array) if present
            conn.execute(
                f"""
                UPDATE {full_table}
                SET tag_ids = json_array(tag_ids)
                WHERE tag_ids IS NOT NULL
                  AND json_valid(tag_ids)
                  AND json_type(tag_ids) = 'STRING'
                """
            )

    # ---------- helpers ----------

    @staticmethod
    def _to_json(md: DocumentMetadata) -> str:
        # Store in “json” mode for portability (enums as values etc.)
        return json.dumps(md.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def _from_json(s: str) -> DocumentMetadata:
        try:
            return DocumentMetadata.model_validate_json(s)
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata JSON: {e}") from e

    # ---------- reads ----------

    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT doc FROM {self._table()} WHERE document_uid = ?",
                [document_uid],
            ).fetchone()
        return self._from_json(row[0]) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT doc FROM {self._table()} WHERE source_tag = ?",
                [source_tag],
            ).fetchall()
        return [self._from_json(r[0]) for r in rows]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Robust to legacy rows: if tag_ids was a string, we normalized it to an array in _ensure_schema.
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT m.doc
                FROM {self._table()} AS m,
                     json_each(CASE
                         WHEN json_valid(m.tag_ids) AND json_type(m.tag_ids)='ARRAY' THEN m.tag_ids
                         ELSE json('[]')
                     END) AS je
                WHERE je.value::VARCHAR = ?
                """,
                [tag_id],
            ).fetchall()
        return [self._from_json(r[0]) for r in rows]

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Keep it simple: load all + filter in memory using the JSON dict.
        (Same behavior you had; easy to evolve later.)
        """
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT doc FROM {self._table()}").fetchall()
        docs = [self._from_json(r[0]) for r in rows]
        return [md for md in docs if self._match_nested(md.model_dump(mode="json"), filters)]

    # ---------- writes ----------

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = metadata.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")

        # pull “hot” columns from the object
        source_tag = metadata.source.source_tag
        date_added = metadata.source.date_added_to_kb
        tag_ids = json.dumps(list(metadata.tags.tag_ids or []), ensure_ascii=False)
        doc_json = self._to_json(metadata)

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self._table()}
                (document_uid, source_tag, date_added_to_kb, tag_ids, doc)
                VALUES (?, ?, ?, ?, ?)
                """,
                [uid, source_tag, date_added, tag_ids, doc_json],
            )

    def delete_metadata(self, document_uid: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(
                f"DELETE FROM {self._table()} WHERE document_uid = ?",
                [document_uid],
            )
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    def clear(self) -> None:
        with self.store._connect() as conn:
            conn.execute(f"DELETE FROM {self._table()}")

    # ---------- helper: nested filter ----------

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        """
        Recursively match a filter dict against a nested dict (string-compare for robustness).
        - If filter value is a list, any exact string match passes.
        """
        for key, value in filter_dict.items():
            if isinstance(value, dict):
                sub = item.get(key, {})
                if not isinstance(sub, dict) or not self._match_nested(sub, value):
                    return False
            else:
                cur = item.get(key)
                if isinstance(value, list):
                    if str(cur) not in map(str, value):
                        return False
                else:
                    if str(cur) != str(value):
                        return False
        return True
