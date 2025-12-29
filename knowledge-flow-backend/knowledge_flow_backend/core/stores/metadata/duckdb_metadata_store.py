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
from pathlib import Path
from typing import List, Optional

from fred_core.store.duckdb_store import DuckDBTableStore
from pydantic import ValidationError

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)


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
                CREATE TABLE IF NOT EXISTS "{full_table}" (
                    document_uid TEXT PRIMARY KEY,
                    source_tag   TEXT,
                    date_added_to_kb TIMESTAMP,
                    tag_ids      VARCHAR[],   -- native array
                    doc          JSON         -- full DocumentMetadata JSON blob
                )
            """)
            # Add missing column if upgrading from an older layout
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{full_table}")').fetchall()}
            if "tag_ids" not in cols:
                conn.execute(f'ALTER TABLE "{full_table}" ADD COLUMN tag_ids VARCHAR[]')

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
                f'SELECT doc FROM "{self._table()}" WHERE document_uid = ?',
                [document_uid],
            ).fetchone()
        return self._from_json(row[0]) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT doc FROM "{self._table()}" WHERE source_tag = ?',
                [source_tag],
            ).fetchall()
        return [self._from_json(r[0]) for r in rows]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Filter by a specific tag using DuckDB's native list_contains function.
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                f'SELECT doc FROM "{self._table()}" WHERE list_contains(tag_ids, ?)',
                [tag_id],
            ).fetchall()
        return [self._from_json(r[0]) for r in rows]

    def browse_metadata_in_tag(self, tag_id: str, offset: int = 0, limit: int = 50) -> tuple[list[DocumentMetadata], int]:
        logger.debug(
            "[PAGINATION] (DuckDB) browse_metadata_in_tag(tag_id=%s, offset=%s, limit=%s)",
            tag_id,
            offset,
            limit,
        )
        with self.store._connect() as conn:
            total_row = conn.execute(
                f'SELECT COUNT(*) FROM "{self._table()}" WHERE list_contains(tag_ids, ?)',
                [tag_id],
            ).fetchone()
            total = total_row[0] if total_row else 0
            rows = conn.execute(
                f'SELECT doc FROM "{self._table()}" WHERE list_contains(tag_ids, ?) LIMIT ? OFFSET ?',
                [tag_id, limit, offset],
            ).fetchall()
        docs = [self._from_json(r[0]) for r in rows]
        logger.debug(
            "[PAGINATION] (DuckDB) browse_metadata_in_tag result: returned=%s total=%s",
            len(docs),
            total,
        )
        return docs, total

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Load all documents then filter in Python for nested keys.
        """
        with self.store._connect() as conn:
            rows = conn.execute(f'SELECT doc FROM "{self._table()}"').fetchall()
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
                INSERT OR REPLACE INTO "{self._table()}"
                (document_uid, source_tag, date_added_to_kb, tag_ids, doc)
                VALUES (?, ?, ?, ?, ?)
                """,
                [uid, source_tag, date_added, tag_ids, doc_json],
            )

    def delete_metadata(self, document_uid: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(
                f'DELETE FROM "{self._table()}" WHERE document_uid = ?',
                [document_uid],
            )
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    def clear(self) -> None:
        with self.store._connect() as conn:
            conn.execute(f'DELETE FROM "{self._table()}"')

    # --- helper: nested filter ---

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        """
        Recursively match a filter dict against a nested dict (string-compare for robustness).

        This implementation is aligned with the flattened field semantics used by the
        OpenSearch metadata store so that callers can use the same filter keys regardless
        of the underlying metadata backend.

        Notable behaviours:
        - Supports both nested keys (e.g. {"source": {"source_tag": "fred"}})
          and flattened aliases (e.g. {"source_tag": "fred"}).
        - For list-valued filters, a match occurs when *any* element matches
          (mirrors OpenSearch "terms" semantics on multi-valued fields).
        - Special handling for processing stage filters using the
          "processing_stages" flattened key.
        """
        for key, value in filter_dict.items():
            # Special case: processing stage filters use a flattened key
            # "processing_stages": {"raw": "done", "preview": "done", ...}
            if key == "processing_stages" and isinstance(value, dict):
                stages = item.get("processing", {}).get("stages", {})
                if not isinstance(stages, dict):
                    return False

                for stage_key, expected in value.items():
                    current = stages.get(stage_key)
                    if isinstance(expected, list):
                        # Any-of semantics on stage status
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
                # Follow nested structure as-is (e.g. {"source": {"source_tag": "fred"}})
                sub = item.get(key, {})
                if not isinstance(sub, dict) or not self._match_nested(sub, value):
                    return False
            else:
                # Flattened aliases for common fields so callers can use the
                # same keys as the OpenSearch-backed path.
                cur = item.get(key, None)
                if cur is None:
                    if key in {"document_name", "document_uid"}:
                        cur = item.get("identity", {}).get(key)
                    elif key in {"source_tag", "retrievable"}:
                        cur = item.get("source", {}).get(key)
                    elif key == "tag_ids":
                        cur = item.get("tags", {}).get("tag_ids")

                if isinstance(value, list):
                    # When the filter is a list:
                    # - if the current value is also a list, check that they intersect
                    # - otherwise, require the scalar value to be in the filter list
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
