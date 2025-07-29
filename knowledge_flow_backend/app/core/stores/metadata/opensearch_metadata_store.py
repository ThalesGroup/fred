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
from typing import List
from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException

from app.common.document_structures import DocumentMetadata
from app.core.stores.metadata.base_metadata_store import (
    BaseMetadataStore,
    MetadataDeserializationError,
)

logger = logging.getLogger(__name__)


class OpenSearchMetadataStore(BaseMetadataStore):
    def __init__(
        self,
        host: str,
        metadata_index_name: str,
        vector_index_name: str,
        username: str = None,
        password: str = None,
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
        self.metadata_index_name = metadata_index_name
        self.vector_index_name = vector_index_name

        if not self.client.indices.exists(index=metadata_index_name):
            self.client.indices.create(index=metadata_index_name)
            logger.info(f"Opensearch index '{metadata_index_name}' created.")
        else:
            logger.warning(f"Opensearch index '{metadata_index_name}' already exists.")

    def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata:
        try:
            response = self.client.get(index=self.metadata_index_name, id=document_uid)
            if not response.get("found"):
                raise ValueError(f"Metadata with UID '{document_uid}' not found.")
            source = response["_source"]
            front_metadata = source.pop("front_metadata", {})
            combined = {**source, **front_metadata}
            return DocumentMetadata(**combined)
        except Exception as e:
            logger.error(f"Failed to get metadata by UID '{document_uid}': {e}")
            raise MetadataDeserializationError from e

    def get_all_metadata(self, filters_dict: dict) -> List[DocumentMetadata]:
        try:
            must_clauses = [
                {"term": {f"front_metadata.{k}.keyword": v}}
                for k, v in filters_dict.items()
            ]
            query = (
                {"match_all": {}}
                if not must_clauses
                else {"bool": {"must": must_clauses}}
            )
            response = self.client.search(
                index=self.metadata_index_name,
                body={"query": query},
                size=1000,
                _source=[
                    "document_name",
                    "document_uid",
                    "date_added_to_kb",
                    "retrievable",
                    "front_metadata",
                ],
            )
            hits = response["hits"]["hits"]
            return [
                DocumentMetadata(**{**h["_source"], **h["_source"].get("front_metadata", {})})
                for h in hits
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve metadata with filters {filters_dict}: {e}")
            raise MetadataDeserializationError from e

    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        try:
            query = {
                "query": {"term": {"front_metadata.source.keyword": source_tag}}
            }
            response = self.client.search(
                index=self.metadata_index_name, body=query, size=1000
            )
            return [
                DocumentMetadata(**{**h["_source"], **h["_source"].get("front_metadata", {})})
                for h in response["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"Error in list_by_source_tag('{source_tag}'): {e}")
            raise MetadataDeserializationError from e

    def update_metadata_field(self, document_uid: str, field: str, value: any):
        try:
            response_meta = self.client.update(
                index=self.metadata_index_name,
                id=document_uid,
                body={"doc": {field: value}},
            )
            logger.info(f"[METADATA] Updated '{field}' for UID '{document_uid}' => {value}")

            script = f"ctx._source.metadata.{field} = params.value"
            query = {
                "script": {"source": script, "lang": "painless", "params": {"value": value}},
                "query": {"term": {"metadata.document_uid": document_uid}},
            }
            response_vector = self.client.update_by_query(
                index=self.vector_index_name, body=query
            )
            logger.info(f"[VECTOR] Updated 'metadata.{field}' for UID '{document_uid}'")

            return {
                "metadata_index_response": response_meta,
                "vector_index_response": response_vector,
            }
        except Exception as e:
            logger.error(f"Failed to update field '{field}' for UID '{document_uid}': {e}")
            raise

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        if not metadata.document_uid:
            raise ValueError("Missing 'document_uid' in metadata.")
        try:
            self.write_metadata(metadata.document_uid, metadata.dict())
        except Exception as e:
            logger.error(f"Failed to save metadata for UID '{metadata.document_uid}': {e}")
            raise

    def write_metadata(self, document_uid: str, metadata: dict):
        try:
            self.client.index(index=self.metadata_index_name, id=document_uid, body=metadata)
            logger.info(f"Metadata written to index '{self.metadata_index_name}' for UID '{document_uid}'.")
        except OpenSearchException as e:
            logger.error(f"❌ Failed to write metadata with UID {document_uid}: {e}")
            raise ValueError(f"Failed to write metadata to Opensearch: {e}")

    def delete_metadata(self, metadata: DocumentMetadata) -> None:
        document_uid = metadata.document_uid
        if not document_uid:
            raise ValueError("Missing 'document_uid' in metadata.")
        try:
            self.client.delete(index=self.metadata_index_name, id=document_uid)
            logger.info(f"Deleted metadata UID '{document_uid}' from index '{self.metadata_index_name}'.")

            delete_query = {"query": {"match": {"metadata.document_uid": document_uid}}}
            self.client.delete_by_query(index=self.vector_index_name, body=delete_query)
            logger.info(f"Deleted all vector chunks for UID '{document_uid}'.")
        except Exception as e:
            logger.error(f"Failed to delete metadata for UID '{document_uid}': {e}")
            raise

    def get_metadata_in_tag(self, tag_id: str) -> List[DocumentMetadata]:
        """
        Return all metadata entries where 'tags' contains the specified tag_id.
        """
        try:
            query = {
                "query": {
                    "term": {
                        "front_metadata.tags.keyword": tag_id
                    }
                }
            }
            response = self.client.search(
                index=self.metadata_index_name,
                body=query,
                size=1000
            )
            hits = response["hits"]["hits"]
            return [
                DocumentMetadata(**{**hit["_source"], **hit["_source"].get("front_metadata", {})})
                for hit in hits
            ]
        except Exception as e:
            logger.error(f"Error in get_metadata_in_tag('{tag_id}'): {e}")
            raise MetadataDeserializationError from e

    def clear(self) -> None:
        try:
            self.client.delete_by_query(index=self.metadata_index_name, body={"query": {"match_all": {}}})
            self.client.delete_by_query(index=self.vector_index_name, body={"query": {"match_all": {}}})
            logger.info(f"Cleared all documents from '{self.metadata_index_name}' and '{self.vector_index_name}'.")
        except Exception as e:
            logger.error(f"❌ Failed to clear metadata store: {e}")
            raise
