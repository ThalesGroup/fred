# app/core/stores/metadata/opensearch_metadata_store.py

import logging
from typing import Any, Dict, List, Optional

from fred_core.store.opensearch_mapping_validator import validate_index_mapping
from opensearchpy import OpenSearch, OpenSearchException, RequestsHttpConnection
from pydantic import ValidationError

from app.common.document_structures import (
    AccessInfo,
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)

# ==============================================================================
# METADATA_INDEX_MAPPING (flat fields for DocumentMetadata v2)
# ==============================================================================
METADATA_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            # identity
            "document_uid": {"type": "keyword"},
            "document_name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
            "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
            "author": {"type": "keyword"},
            "created": {"type": "date"},
            "modified": {"type": "date"},
            "last_modified_by": {"type": "keyword"},
            # source
            "source_type": {"type": "keyword"},
            "source_tag": {"type": "keyword"},
            "pull_location": {"type": "keyword"},
            "retrievable": {"type": "boolean"},
            "date_added_to_kb": {"type": "date"},
            # file
            "file_type": {"type": "keyword"},
            "mime_type": {"type": "keyword"},
            "file_size_bytes": {"type": "long"},
            "page_count": {"type": "integer"},
            "row_count": {"type": "integer"},
            "sha256": {"type": "keyword"},
            "language": {"type": "keyword"},
            # tags / folders
            "tag_ids": {"type": "keyword"},
            # access
            "license": {"type": "keyword"},
            "confidential": {"type": "boolean"},
            "acl": {"type": "keyword"},
            # processing (ops)
            "processing_stages": {"type": "object", "dynamic": True},
            "processing_errors": {"type": "object", "dynamic": True},
            # processor specific fields
            "extensions": {"type": "object", "enabled": False},
        }
    }
}


class OpenSearchMetadataStore(BaseMetadataStore):
    """
    OpenSearch-based implementation of the metadata store (flat fields persisted).
    Auto-creates the index with METADATA_INDEX_MAPPING when missing.
    """

    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        self.metadata_index_name = index

        if not self.client.indices.exists(index=self.metadata_index_name):
            self.client.indices.create(index=self.metadata_index_name, body=METADATA_INDEX_MAPPING)
            logger.info(f"OpenSearch index '{index}' created.")
        else:
            logger.info(f"OpenSearch index '{index}' already exists.")
            # Validate existing mapping matches expected mapping
            validate_index_mapping(self.client, self.metadata_index_name, METADATA_INDEX_MAPPING)

    # ---------- (de)serialization ----------

    @staticmethod
    def _serialize(md: DocumentMetadata) -> Dict[str, Any]:
        missing: list[tuple[str, str]] = []
        if not md.identity.document_uid:
            missing.append(("identity.document_uid", "document UID"))
        if not md.identity.document_name:
            missing.append(("identity.document_name", "document name"))
        if not md.source.date_added_to_kb:
            missing.append(("source.date_added_to_kb", "date added to KB"))
        if not md.source.source_type:
            missing.append(("source.source_type", "source type"))
        if missing:
            labels = ", ".join(lbl for _, lbl in missing)
            raise MetadataDeserializationError(f"Cannot serialize metadata: missing {labels}")

        """Flatten DocumentMetadata v2 into top-level dict that matches index mapping."""
        stages = {k.value: v.value for k, v in md.processing.stages.items()}
        errors = {k.value: v for k, v in md.processing.errors.items()}

        return {
            # identity
            "document_uid": md.identity.document_uid,
            "document_name": md.identity.document_name,
            "title": md.identity.title,
            "author": md.identity.author,
            "created": md.identity.created,
            "modified": md.identity.modified,
            "last_modified_by": md.identity.last_modified_by,
            # source
            "source_type": md.source.source_type.value,
            "source_tag": md.source.source_tag,
            "pull_location": md.source.pull_location,
            "retrievable": md.source.retrievable,
            "date_added_to_kb": md.source.date_added_to_kb,
            # file
            "file_type": (md.file.file_type.value if md.file.file_type else FileType.OTHER.value),
            "mime_type": md.file.mime_type,
            "file_size_bytes": md.file.file_size_bytes,
            "page_count": md.file.page_count,
            "row_count": md.file.row_count,
            "sha256": md.file.sha256,
            "language": md.file.language,
            # tags / folders
            "tag_ids": md.tags.tag_ids,
            # access
            "license": md.access.license,
            "confidential": md.access.confidential,
            "acl": md.access.acl,
            # processing (ops)
            "processing_stages": stages,
            "processing_errors": errors,
            # extensions
            "extensions": md.extensions or {},
        }

    @staticmethod
    def _deserialize(src: Dict[str, Any]) -> DocumentMetadata:
        """Rebuild nested DocumentMetadata v2 from flat dict."""
        try:
            if not src.get("document_uid"):
                raise MetadataDeserializationError("Missing 'document_uid' in OpenSearch source")
            if not src.get("document_name"):
                raise MetadataDeserializationError("Missing 'document_name' in OpenSearch source")
            if not src.get("date_added_to_kb"):
                raise MetadataDeserializationError("Missing 'date_added_to_kb' in OpenSearch source")

            identity = Identity(
                document_uid=src["document_uid"],
                document_name=src["document_name"],
                title=src.get("title"),
                author=src.get("author"),
                created=src.get("created"),
                modified=src.get("modified"),
                last_modified_by=src.get("last_modified_by"),
            )
            source = SourceInfo(
                source_type=SourceType(src.get("source_type")) if src.get("source_type") else SourceType.PUSH,
                source_tag=src.get("source_tag"),
                pull_location=src.get("pull_location"),
                retrievable=bool(src.get("retrievable")) if src.get("retrievable") is not None else False,
                date_added_to_kb=src["date_added_to_kb"],
            )
            file = FileInfo(
                file_type=FileType(src.get("file_type")) if src.get("file_type") else FileType.OTHER,
                mime_type=src.get("mime_type"),
                file_size_bytes=src.get("file_size_bytes"),
                page_count=src.get("page_count"),
                row_count=src.get("row_count"),
                sha256=src.get("sha256"),
                language=src.get("language"),
            )
            tags = Tagging(
                tag_ids=list(src.get("tag_ids") or []),
            )
            access = AccessInfo(
                license=src.get("license"),
                confidential=bool(src.get("confidential")) if src.get("confidential") is not None else False,
                acl=list(src.get("acl") or []),
            )

            stages_raw: Dict[str, str] = src.get("processing_stages") or {}
            errors_raw: Dict[str, str] = src.get("processing_errors") or {}

            stages: Dict[ProcessingStage, ProcessingStatus] = {}
            for k, v in stages_raw.items():
                try:
                    stages[ProcessingStage(k)] = ProcessingStatus(v)
                except Exception:
                    # tolerate unknowns
                    logger.warning(f"Failed to process stage {k}: {v}")
                    continue

            processing = Processing(
                stages=stages,
                errors={ProcessingStage(k): v for k, v in errors_raw.items() if k in stages_raw and v is not None},
            )

            return DocumentMetadata(
                identity=identity,
                source=source,
                file=file,
                tags=tags,
                access=access,
                processing=processing,
                extensions=src.get("extensions") or None,
            )
        except ValidationError as e:
            raise MetadataDeserializationError(f"Invalid metadata structure: {e}") from e

    # ---------- reads ----------

    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        if not document_uid:
            raise ValueError("Document UID must be provided.")
        try:
            resp = self.client.get(index=self.metadata_index_name, id=document_uid)
            if not resp.get("found"):
                return None
            source = resp["_source"]
        except Exception as e:
            logger.error(f"OpenSearch request failed for UID '{document_uid}': {e}")
            raise
        try:
            return self._deserialize(source)
        except Exception as e:
            logger.error(f"Deserialization failed for UID '{document_uid}': {e}")
            raise MetadataDeserializationError from e

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        try:
            must = self._build_must_clauses(filters)
            query = {"match_all": {}} if not must else {"bool": {"must": must}}
            resp = self.client.search(index=self.metadata_index_name, body={"query": query}, params={"size": 10000})
            hits = resp["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch search failed with filters {filters}: {e}")
            raise

        out: List[DocumentMetadata] = []
        for h in hits:
            try:
                out.append(self._deserialize(h["_source"]))
            except Exception as e:
                logger.warning(f"Deserialization failed for doc {h.get('_id')}: {e}")
        return out

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        try:
            query = {"query": {"term": {"source_tag": {"value": source_tag}}}}
            resp = self.client.search(index=self.metadata_index_name, body=query, params={"size": 10000})
            hits = resp["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch query failed for source_tag='{source_tag}': {e}")
            raise

        results: List[DocumentMetadata] = []
        errors = 0
        for h in hits:
            try:
                results.append(self._deserialize(h["_source"]))
            except ValidationError as e:
                errors += 1
                doc_id = h.get("_id", "<unknown>")
                logger.warning(f"[Deserialization error] Skipping document '{doc_id}': {e}")
        if errors > 0:
            logger.warning(f"{errors} documents failed to deserialize in list_by_source_tag('{source_tag}').")
        return results

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        if not tag_id:
            raise ValueError("Tag ID must be provided.")
        try:
            query = {"query": {"term": {"tag_ids": tag_id}}}
            resp = self.client.search(index=self.metadata_index_name, body=query, params={"size": 10000})
            hits = resp["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch query failed for tag '{tag_id}': {e}")
            raise
        try:
            return [self._deserialize(hit["_source"]) for hit in hits]
        except Exception as e:
            logger.error(f"Deserialization failed for results tagged '{tag_id}': {e}")
            raise MetadataDeserializationError from e

    # ---------- writes ----------

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        uid = metadata.identity.document_uid
        if not uid:
            raise ValueError("Missing 'document_uid' in metadata.")
        body = self._serialize(metadata)
        try:
            self.client.index(index=self.metadata_index_name, id=uid, body=body)
            logger.info(f"[METADATA] Indexed document with UID '{uid}' into '{self.metadata_index_name}'.")
        except OpenSearchException as e:
            logger.error(f"Failed to index metadata for UID '{uid}': {e}")
            raise RuntimeError(f"Failed to index metadata: {e}") from e

    def delete_metadata(self, document_uid: str) -> None:
        try:
            self.client.delete(index=self.metadata_index_name, id=document_uid)
            logger.info(f"Deleted metadata UID '{document_uid}' from index '{self.metadata_index_name}'.")
        except Exception as e:
            logger.error(f"Failed to delete metadata UID '{document_uid}': {e}")
            raise

    def clear(self) -> None:
        try:
            self.client.delete_by_query(index=self.metadata_index_name, body={"query": {"match_all": {}}})
            logger.info(f"Cleared all documents from '{self.metadata_index_name}'.")
        except Exception as e:
            logger.error(f"Failed to clear metadata store: {e}")
            raise

    # ---------- helpers ----------

    def _build_must_clauses(self, filters_dict: dict) -> List[dict]:
        must: List[dict] = []

        def flatten(prefix: str, val):
            if isinstance(val, dict):
                for k, v in val.items():
                    yield from flatten(f"{prefix}.{k}", v)
            else:
                yield (prefix, val)

        for field, value in filters_dict.items():
            if isinstance(value, dict):
                for flat_field, flat_value in flatten(field, value):
                    must.append({"term": {flat_field: flat_value}})
            elif isinstance(value, list):
                must.append({"terms": {field: value}})
            else:
                must.append({"term": {field: value}})
        return must
