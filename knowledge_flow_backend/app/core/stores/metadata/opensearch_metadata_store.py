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

import logging
from typing import List, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException
from pydantic import ValidationError

from app.common.document_structures import DocumentMetadata
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)

# ==============================================================================
# METADATA_INDEX_MAPPING
# ==============================================================================
# This mapping defines the OpenSearch schema used for storing DocumentMetadata.
#
# ⚠️ WARNING: This mapping is embedded directly in code and applied when the
# OpenSearchMetadataStore is initialized, if the index does not already exist.
#
# ✅ This approach works well for local development and lightweight deployments.
# ❗ In production environments, it is recommended to pre-create indices using
# provisioning tools (Terraform, Ansible, OpenSearch Dashboards, etc.) so you
# can control:
#   - number_of_shards / number_of_replicas
#   - refresh interval
#   - ILM policies
#   - index templates and mappings evolution
#
# 🛠️ If needed, you can extend this dictionary to include full "settings":
# {
#     "settings": {
#         "number_of_shards": 1,
#         "number_of_replicas": 0,
#         "refresh_interval": "1s"
#     },
#     "mappings": { ... }
# }
#
# Note: Fields like 'document_name' are stored both as full text (for search)
# and as 'keyword' (for exact match filters). The 'processing_stages' object
# is partially structured, but allows new stage keys thanks to `dynamic: true`.
# ==============================================================================

METADATA_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "document_uid": {"type": "keyword"},
            "document_name": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
            "date_added_to_kb": {"type": "date"},
            "source_tag": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "retrievable": {"type": "boolean"},
            "processing_stages": {
                "type": "object",
                "properties": {
                    "VECTORIZED": {"type": "keyword"},
                    "OCR_DONE": {"type": "keyword"},
                    "INGESTED": {"type": "keyword"},
                },
                "dynamic": True,
            },
        }
    }
}


class OpenSearchMetadataStore(BaseMetadataStore):
    """
    OpenSearch-based implementation of the metadata store.

    Required OpenSearch mapping for 'metadata-index':

    {
      "mappings": {
        "properties": {
          "document_uid":     { "type": "keyword" },
          "document_name":    { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },
          "date_added_to_kb": { "type": "date" },
          "source_tag":       { "type": "keyword" },
          "tags":             { "type": "keyword" },
          "retrievable":      { "type": "boolean" },
          "processing_stages": {
            "type": "object",
            "properties": {
              "VECTORIZED": { "type": "keyword" },
              "OCR_DONE":   { "type": "keyword" },
              "INGESTED":   { "type": "keyword" }
            },
            "dynamic": true
          }
        }
      }
    }
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
            logger.info(f"Opensearch index '{index}' created.")
        else:
            logger.warning(f"Opensearch index '{index}' already exists.")

    def get_metadata_by_uid(self, document_uid: str) -> Optional[DocumentMetadata]:
        """
        Retrieve metadata for a document by its unique identifier (UID).
        Returns None if the document does not exist.
        """
        if not document_uid:
            raise ValueError("Document UID must be provided.")
        try:
            response = self.client.get(index=self.metadata_index_name, id=document_uid)
            if not response.get("found"):
                return None
            source = response["_source"]
        except Exception as e:
            logger.error(f"OpenSearch request failed for UID '{document_uid}': {e}")
            raise

        try:
            return DocumentMetadata(**source)
        except Exception as e:
            logger.error(f"Deserialization failed for UID '{document_uid}': {e}")
            raise MetadataDeserializationError from e

    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        """
        Retrieve all metadata documents that match the given filters.
        Filters should be a dictionary where keys are field names and values are the filter values.
        Example: {"source_tag": "local-docs", "category": "reports"}
        """
        try:
            must_clauses = self._build_must_clauses(filters)
            query = {"match_all": {}} if not must_clauses else {"bool": {"must": must_clauses}}

            response = self.client.search(
                params={"size": 10000},
                index=self.metadata_index_name,
                body={"query": query},
            )
            hits = response["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch search failed with filters {filters}: {e}")
            raise

        results = []
        for h in hits:
            try:
                results.append(DocumentMetadata(**h["_source"]))
            except Exception as e:
                logger.warning(f"Deserialization failed for doc {h.get('_id')}: {e}")
        return results

    def _build_must_clauses(self, filters_dict: dict) -> List[dict]:
        must = []

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

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        """
        List all metadata documents that match a specific source tag.
        """
        try:
            query = {"query": {"term": {"source_tag": {"value": source_tag}}}}

            response = self.client.search(index=self.metadata_index_name, body=query, params={"size": 10000})
            hits = response["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch query failed for source_tag='{source_tag}': {e}")
            raise

        results = []
        errors = 0
        for h in hits:
            try:
                results.append(DocumentMetadata(**h["_source"]))
            except ValidationError as e:
                errors += 1
                doc_id = h.get("_id", "<unknown>")
                logger.warning(f"[Deserialization error] Skipping document '{doc_id}': {e}")

        if errors > 0:
            logger.warning(f"{errors} documents failed to deserialize in list_by_source_tag('{source_tag}').")

        return results

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        """
        Index the metadata into OpenSearch by document UID.
        Overwrites any existing document with the same UID.
        """
        if not metadata.document_uid:
            raise ValueError("Missing 'document_uid' in metadata.")

        try:
            self.client.index(
                index=self.metadata_index_name,
                id=metadata.document_uid,
                body=metadata.model_dump(),
            )
            logger.info(f"[METADATA] Indexed document with UID '{metadata.document_uid}' into '{self.metadata_index_name}'.")
        except OpenSearchException as e:
            logger.error(f"❌ Failed to index metadata for UID '{metadata.document_uid}': {e}")
            raise RuntimeError(f"Failed to index metadata: {e}") from e

    def delete_metadata(self, document_uid: str) -> None:
        """
        Delete the metadata document identified by its UID.
        Returns True if deletion succeeded, False otherwise.
        """
        try:
            self.client.delete(index=self.metadata_index_name, id=document_uid)
            logger.info(f"✅ Deleted metadata UID '{document_uid}' from index '{self.metadata_index_name}'.")
        except Exception as e:
            logger.error(f"❌ Failed to delete metadata UID '{document_uid}': {e}")
            raise

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Return all metadata entries where 'tags' contains the specified tag_id.
        """
        if not tag_id:
            raise ValueError("Tag ID must be provided.")

        try:
            query = {"query": {"term": {"tags": tag_id}}}
            response = self.client.search(index=self.metadata_index_name, body=query, params={"size": 10000})
            hits = response["hits"]["hits"]
        except Exception as e:
            logger.error(f"OpenSearch query failed for tag '{tag_id}': {e}")
            raise

        try:
            return [DocumentMetadata(**hit["_source"]) for hit in hits]
        except Exception as e:
            logger.error(f"Deserialization failed for results tagged '{tag_id}': {e}")
            raise MetadataDeserializationError from e

    def clear(self) -> None:
        try:
            self.client.delete_by_query(index=self.metadata_index_name, body={"query": {"match_all": {}}})
            logger.info(f"Cleared all documents from '{self.metadata_index_name}'")
        except Exception as e:
            logger.error(f"❌ Failed to clear metadata store: {e}")
            raise
