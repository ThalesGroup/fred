import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from pydantic import ValidationError

from fred_core.store.duckdb_store import DuckDBTableStore
from app.core.stores.metadata.base_metadata_store import BaseMetadataStore, MetadataDeserializationError
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
    def __init__(self, db_path: Path):
        self.table_name = "metadata"
        self.store = DuckDBTableStore(db_path, prefix="metadata_")
        self._ensure_schema()

    def _table(self) -> str:
        return self.store._prefixed(self.table_name)

    # ---------- schema ----------

    def _ensure_schema(self) -> None:
        full_table = self._table()
        with self.store._connect() as conn:
            conn.execute(
                f"""
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
                    language TEXT,

                    -- tags / folders
                    tag_ids JSON,

                    -- access
                    license TEXT,
                    confidential BOOLEAN,
                    acl JSON,

                    -- processing (dev/ops convenience)
                    processing_stages JSON,   -- {"raw": "done", ... }
                    processing_errors JSON    -- {"raw": "err msg", ... }
                    extensions JSON
                )
                """
            )

    # ---------- (de)serialization ----------

    @staticmethod
    def _serialize(md: DocumentMetadata) -> Tuple:
        # stages/errors as string enums for portability
        stages = {k.value: v.value for k, v in md.processing.stages.items()}
        errors = {k.value: v for k, v in md.processing.errors.items()}

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
            md.source.retrievable,
            md.source.date_added_to_kb,
            # file
            (md.file.file_type.value if md.file.file_type else FileType.OTHER.value),
            md.file.mime_type,
            md.file.file_size_bytes,
            md.file.page_count,
            md.file.row_count,
            md.file.sha256,
            md.file.language,
            # tags / folders
            json.dumps(md.tags.tag_ids or []),
            # access
            md.access.license,
            md.access.confidential,
            json.dumps(md.access.acl or []),
            # processing
            json.dumps(stages),
            json.dumps(errors),
            json.dumps(md.extensions) if md.extensions else "{}",
        )

    @staticmethod
    def _deserialize(row: tuple) -> DocumentMetadata:
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
                language=row[18],
            )
            # tags
            tag_ids = json.loads(row[19]) if row[19] else []
            tags = Tagging(
                tag_ids=tag_ids,
            )
            # access
            access = AccessInfo(
                license=row[20],
                confidential=bool(row[21]) if row[21] is not None else False,
                acl=json.loads(row[22]) if row[22] else [],
            )
            # processing
            stages_raw: Dict[str, str] = json.loads(row[23]) if row[23] else {}
            errors_raw: Dict[str, str] = json.loads(row[24]) if row[24] else {}

            stages: Dict[ProcessingStage, ProcessingStatus] = {}
            for k, v in stages_raw.items():
                # tolerate unknowns in dev
                try:
                    stages[ProcessingStage(k)] = ProcessingStatus(v)
                except Exception:
                    logger.warning(f"Failed to process stage {k}: {v}")
                    continue

            proc_errors: Dict[ProcessingStage, str] = {}
            for k in stages_raw.keys():
                if k in errors_raw:
                    try:
                        stage = ProcessingStage(k)
                        error_val = errors_raw.get(k)
                        if error_val is not None:
                            proc_errors[stage] = error_val
                    except Exception:
                        logger.warning(f"Failed to process error for stage {k}: {errors_raw.get(k)}")
                        continue

            proc = Processing(stages=stages, errors=proc_errors)
            extensions = json.loads(row[18]) if row[25] else None
            return DocumentMetadata(identity=identity, source=source, file=file, tags=tags, access=access, processing=proc, extensions=extensions)
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata structure for document {row[0]}: {e}")

    # ---------- queries ----------

    def _query_all(self) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()}").fetchall()
        return [self._deserialize(r) for r in rows]

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        # Keep simple for dev: load all, then in‑memory filter against the JSON form
        all_docs = self._query_all()
        return [md for md in all_docs if self._match_nested(md.model_dump(mode="json"), filters)]

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        # Search by tag id in JSON array column tag_ids
        with self.store._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self._table()}
                WHERE json_contains(tag_ids, to_json(?))
                """,
                [tag_id],
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata | None:
        with self.store._connect() as conn:
            row = conn.execute(f"SELECT * FROM {self._table()} WHERE document_uid = ?", [document_uid]).fetchone()
        return self._deserialize(row) if row else None

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        with self.store._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {self._table()} WHERE source_tag = ?", [source_tag]).fetchall()
        return [self._deserialize(r) for r in rows]

    # ---------- mutations ----------

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = metadata.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")

        with self.store._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self._table()} VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
                """,
                self._serialize(metadata),
            )

    def delete_metadata(self, document_uid: str) -> None:
        with self.store._connect() as conn:
            result = conn.execute(f"DELETE FROM {self._table()} WHERE document_uid = ?", [document_uid])
        if result.rowcount == 0:
            raise ValueError(f"No document found with UID {document_uid}")

    def clear(self) -> None:
        with self.store._connect() as conn:
            conn.execute(f"DELETE FROM {self._table()}")

    # ---------- helper: nested filter ----------

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
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
