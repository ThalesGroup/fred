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

import json
from pathlib import Path
from typing import List, Any
from pydantic import ValidationError

from fred_core.store.duckdb_store import DuckDBTableStore
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore, MetadataDeserializationError
from app.common.document_structures import DocumentMetadata, ProcessingStage


class DuckdbMetadataStore(BaseMetadataStore):
    def __init__(self, db_path: Path):
        self.table_name = "metadata"
        self.store = DuckDBTableStore(db_path, prefix="")
        self._ensure_schema()

    def _ensure_schema(self):
        full_table = self.store._prefixed(self.table_name)
        with self.store._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    document_uid TEXT PRIMARY KEY,
                    document_name TEXT,
                    date_added_to_kb TIMESTAMP,
                    retrievable BOOLEAN,
                    source_tag TEXT,
                    pull_location TEXT,
                    source_type TEXT,
                    tags JSON,
                    title TEXT,
                    author TEXT,
                    created TIMESTAMP,
                    modified TIMESTAMP,
                    last_modified_by TEXT,
                    category TEXT,
                    subject TEXT,
                    keywords TEXT,
                    processing_stages JSON
                )
            """)

    def _serialize(self, metadata: DocumentMetadata) -> tuple:
        return (
            metadata.document_uid,
            metadata.document_name,
            metadata.date_added_to_kb,
            metadata.retrievable,
            metadata.source_tag,
            metadata.pull_location,
            metadata.source_type,
            json.dumps(metadata.tags) if metadata.tags else "[]",
            metadata.title,
            metadata.author,
            metadata.created,
            metadata.modified,
            metadata.last_modified_by,
            metadata.category,
            metadata.subject,
            metadata.keywords,
            json.dumps(metadata.processing_stages) if metadata.processing_stages else "{}",
        )

    def _deserialize(self, row: tuple) -> DocumentMetadata:
        try:
            return DocumentMetadata(
                document_uid=row[0],
                document_name=row[1],
                date_added_to_kb=row[2],
                retrievable=row[3],
                source_tag=row[4],
                pull_location=row[5],
                source_type=row[6],
                tags=json.loads(row[7]) if row[7] else None,
                title=row[8],
                author=row[9],
                created=row[10],
                modified=row[11],
                last_modified_by=row[12],
                category=row[13],
                subject=row[14],
                keywords=row[15],
                processing_stages=json.loads(row[16]) if row[16] else {},
            )
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata structure for document {row[0]}: {e}")

    def _table(self):
        return self.store._prefixed(self.table_name)

    def _query_all(self) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()}").fetchall()
        return [self._deserialize(row) for row in rows]

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        # In-memory filtering for now
        all_docs = self._query_all()
        return [md for md in all_docs if self._match_nested(md.model_dump(mode="json"), filters)]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self._table()}
                WHERE json_contains(tags, to_json(?))
                """,
                [tag_id],
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata | None:
        with self.store._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._table()} WHERE document_uid = ?", [document_uid]).fetchone()
        return self._deserialize(row) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self._table()}
                WHERE source_tag = ?
                """,
                [source_tag],
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        if not metadata.document_uid:
            raise ValueError("Metadata must contain a 'document_uid'")
        with self.store._connect() as conn:
            conn.execute(
                f"""
                    INSERT OR REPLACE INTO {self._table()} VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
            """,
                self._serialize(metadata),
            )

    def delete_metadata(self, document_uid: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(f"DELETE FROM {self._table()} WHERE document_uid = ?", [document_uid])
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    def _update_metadata_field(self, document_uid: str, field: str, value: Any) -> DocumentMetadata:
        existing = self.get_metadata_by_uid(document_uid)
        if not existing:
            raise ValueError(f"No document found with UID {document_uid}")
        setattr(existing, field, value)
        self.save_metadata(existing)
        return existing

    def clear(self) -> None:
        with self.store._connect() as conn:
            conn.execute(f"DELETE FROM {self._table()}")

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        for key, value in filter_dict.items():
            if isinstance(value, dict):
                sub_item = item.get(key, {})
                if not isinstance(sub_item, dict) or not self._match_nested(sub_item, value):
                    return False
            else:
                if str(item.get(key)) != str(value):
                    return False
        return True
