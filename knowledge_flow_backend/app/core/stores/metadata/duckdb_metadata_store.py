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

from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import ValidationError

from app.common.document_structures import DocumentMetadata
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)


class DuckdbMetadataStore(BaseMetadataStore):
    """
    DuckDB metadata store with native arrays:
      - 'doc' keeps the full DocumentMetadata JSON blob
      - 'tag_ids' is a VARCHAR[] for fast filtering
    """

    def __init__(self, db_path: Path):
        self.table_name = "metadata_v2"
        self.store = DuckDBTableStore(db_path, prefix="metadata_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # --- schema ---

    def _ensure_schema(self) -> None:
        """
        Ensure table exists and add columns if the schema drifted.
        """
        full_table = self._table()
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    document_uid TEXT PRIMARY KEY,
                    source_tag   TEXT,
                    date_added_to_kb TIMESTAMP,
                    tag_ids      VARCHAR[],   -- native array
                    doc          JSON         -- full DocumentMetadata JSON blob
                )
            """)
            # Add missing column if upgrading from an older layout
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info('{full_table}')").fetchall()}
            if "tag_ids" not in cols:
                conn.execute(f"ALTER TABLE {full_table} ADD COLUMN tag_ids VARCHAR[]")

    # --- serialization helpers ---

    @staticmethod
    def _to_json(md: DocumentMetadata) -> str:
        # Store in JSON mode for portability (enums as values etc.)
        return md.model_dump_json()

    @staticmethod
    def _from_json(s: str) -> DocumentMetadata:
        try:
            return DocumentMetadata.model_validate_json(s)
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata JSON: {e}") from e

    # --- reads ---

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
        Filter by a specific tag using DuckDB's native list_contains function.
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT doc FROM {self._table()} WHERE list_contains(tag_ids, ?)",
                [tag_id],
            ).fetchall()
        return [self._from_json(r[0]) for r in rows]

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Load all documents then filter in Python for nested keys.
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

        source_tag = metadata.source.source_tag
        date_added = metadata.source.date_added_to_kb
        tag_ids = list(metadata.tags.tag_ids or [])
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

    # --- helper: nested filter ---

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
