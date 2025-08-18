# app/core/stores/metadata/duckdb_metadata_store.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from pydantic import ValidationError

from fred_core.store.duckdb_store import DuckDBTableStore
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)
from app.common.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    FileInfo,
    Tagging,
    AccessInfo,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceType,
    FileType,
)

logger = logging.getLogger(__name__)


class DuckdbMetadataStore(BaseMetadataStore):
    """
    DuckDB-backed store for DocumentMetadata.

    Table layout is kept flat for simplicity; nested fields are serialized as JSON.
    """

    def __init__(self, db_path: Path):
        self.table_name = "metadata"
        self.store = DuckDBTableStore(db_path, prefix="metadata_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # ---------- schema ----------

    def _ensure_schema(self) -> None:
        """Create the table if it does not exist (idempotent)."""
        full_table = self._table()
        # NOTE: Avoid braces in f-string comments (they confuse the formatter).
        # Keep examples minimal and brace-free.
        sql = f"""
            CREATE TABLE IF NOT EXISTS {full_table} (
                -- identity
                document_uid TEXT PRIMARY KEY,
                document_name TEXT,
                title TEXT,
                author TEXT,
                created TIMESTAMP,
                modified TIMESTAMP,
                last_modified_by TEXT,

                -- source
                source_type TEXT,
                source_tag TEXT,
                pull_location TEXT,
                retrievable BOOLEAN,
                date_added_to_kb TIMESTAMP,

                -- file
                file_type TEXT,
                mime_type TEXT,
                file_size_bytes BIGINT,
                page_count INTEGER,
                row_count INTEGER,
                sha256 TEXT,
                md5 TEXT,
                language TEXT,

                -- tags / folders
                tag_ids JSON,
                tag_names JSON,

                -- access
                license TEXT,
                confidential BOOLEAN,
                acl JSON,

                -- processing (dev/ops convenience)
                processing_stages JSON,   -- map of stage -> status
                processing_errors JSON,   -- map of stage -> error message

                -- UX links
                preview_url TEXT,
                viewer_url TEXT,

                -- extensions
                extensions JSON
            )
        """
        with self.store._connect() as conn:
            conn.execute(sql)

    # ---------- (de)serialization ----------

    @staticmethod
    def _serialize(md: DocumentMetadata) -> Tuple:
        """Flatten DocumentMetadata into a tuple matching the column order."""
        # stages/errors as string enums for portability
        stages = {k.value: v.value for k, v in md.processing.stages.items()}
        errors = {k.value: v for k, v in md.processing.errors.items()}

        # JSON helpers
        tag_ids_json = json.dumps(md.tags.tag_ids or [])
        tag_names_json = json.dumps(md.tags.tag_names or [])
        acl_json = json.dumps(md.access.acl or [])
        stages_json = json.dumps(stages)
        errors_json = json.dumps(errors)
        extensions_json = json.dumps(md.extensions) if md.extensions else None

        return (
            # identity
            md.identity.document_uid,
            md.identity.document_name,
            md.identity.title,
            md.identity.author,
            md.identity.created,
            md.identity.modified,
            md.identity.last_modified_by,

            # source
            md.source.source_type.value,
            md.source.source_tag,
            md.source.pull_location,
            bool(md.source.retrievable),
            md.source.date_added_to_kb,

            # file
            (md.file.file_type.value if md.file.file_type else FileType.OTHER.value),
            md.file.mime_type,
            md.file.file_size_bytes,
            md.file.page_count,
            md.file.row_count,
            md.file.sha256,
            md.file.md5,
            md.file.language,

            # tags
            tag_ids_json,
            tag_names_json,

            # access
            md.access.license,
            bool(md.access.confidential),
            acl_json,

            # processing
            stages_json,
            errors_json,

            # UX links
            str(md.preview_url) if md.preview_url else None,
            str(md.viewer_url) if md.viewer_url else None,

            # extensions
            extensions_json,
        )

    @staticmethod
    def _deserialize(row: tuple) -> DocumentMetadata:
        """
        Rebuild DocumentMetadata from a row tuple.

        Column indices (0-based):
            0-6    identity
            7-11   source
            12-19  file
            20-21  tags
            22-24  access
            25-26  processing maps
            27-28  UX links
            29     extensions
        """
        try:
            # identity
            identity = Identity(
                document_uid=row[0],
                document_name=row[1],
                title=row[2],
                author=row[3],
                created=row[4],
                modified=row[5],
                last_modified_by=row[6],
            )

            # source
            source = SourceInfo(
                source_type=SourceType(row[7]),
                source_tag=row[8],
                pull_location=row[9],
                retrievable=bool(row[10]) if row[10] is not None else False,
                date_added_to_kb=row[11],
            )

            # file
            file = FileInfo(
                file_type=FileType(row[12]) if row[12] else FileType.OTHER,
                mime_type=row[13],
                file_size_bytes=row[14],
                page_count=row[15],
                row_count=row[16],
                sha256=row[17],
                md5=row[18],
                language=row[19],
            )

            # tags
            tag_ids = json.loads(row[20]) if row[20] else []
            tag_names = json.loads(row[21]) if row[21] else []
            tags = Tagging(tag_ids=tag_ids, tag_names=tag_names)

            # access
            access = AccessInfo(
                license=row[22],
                confidential=bool(row[23]) if row[23] is not None else False,
                acl=json.loads(row[24]) if row[24] else [],
            )

            # processing
            stages_raw: Dict[str, str] = json.loads(row[25]) if row[25] else {}
            errors_raw: Dict[str, str] = json.loads(row[26]) if row[26] else {}

            stages: Dict[ProcessingStage, ProcessingStatus] = {}
            for k, v in stages_raw.items():
                try:
                    stages[ProcessingStage(k)] = ProcessingStatus(v)
                except Exception:
                    logger.warning(f"Unknown processing mapping ignored: {k} -> {v}")
                    continue

            proc_errors: Dict[ProcessingStage, str] = {}
            for k, msg in errors_raw.items():
                try:
                    stage = ProcessingStage(k)
                    if msg is not None:
                        proc_errors[stage] = msg
                except Exception:
                    logger.warning(f"Unknown processing error ignored: {k} -> {msg}")
                    continue

            proc = Processing(stages=stages, errors=proc_errors)

            # UX links
            preview_url = row[27]
            viewer_url = row[28]

            # extensions (FIX: correct index)
            extensions = json.loads(row[29]) if row[29] else None

            return DocumentMetadata(
                identity=identity,
                source=source,
                file=file,
                tags=tags,
                access=access,
                processing=proc,
                preview_url=preview_url,
                viewer_url=viewer_url,
                extensions=extensions,
            )
        except ValidationError as e:
            raise MetadataDeserializationError(
                f"Invalid metadata structure for document {row[0]}: {e}"
            )

    # ---------- queries ----------

    def _query_all(self) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()}").fetchall()
        return [self._deserialize(r) for r in rows]

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Simple dev-mode filter: load all, then filter in memory against the JSON form.
        """
        all_docs = self._query_all()
        return [md for md in all_docs if self._match_nested(md.model_dump(mode="json"), filters)]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Search by tag id in JSON array column tag_ids (DuckDB: use json_each to scan arrays).
        """
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT m.*
                FROM {self._table()} AS m,
                     json_each(m.tag_ids) AS je
                WHERE je.value = ?
                """,
                [tag_id],
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        with self.store._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {self._table()} WHERE document_uid = ?",
                [document_uid],
            ).fetchone()
        return self._deserialize(row) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self._table()} WHERE source_tag = ?",
                [source_tag],
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    # ---------- mutations ----------

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = metadata.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")

        columns_sql = """
            document_uid, document_name, title, author, created, modified, last_modified_by,
            source_type, source_tag, pull_location, retrievable, date_added_to_kb,
            file_type, mime_type, file_size_bytes, page_count, row_count, sha256, md5, language,
            tag_ids, tag_names,
            license, confidential, acl,
            processing_stages, processing_errors,
            preview_url, viewer_url,
            extensions
        """
        placeholders = ", ".join(["?"] * 31)

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self._table()} (
                    {columns_sql}
                ) VALUES ({placeholders})
                """,
                self._serialize(metadata),
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
                sub_item = item.get(key, {})
                if not isinstance(sub_item, dict) or not self._match_nested(sub_item, value):
                    return False
            else:
                item_value = item.get(key)
                if isinstance(value, list):
                    if str(item_value) not in map(str, value):
                        return False
                else:
                    if str(item_value) != str(value):
                        return False
        return True
