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
from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException

from app.core.stores.metadata.base_metadata_store import BaseMetadataStore


logger = logging.getLogger(__name__)


class OpenSearchMetadataStore(BaseMetadataStore):
    def __init__(self, host: str, metadata_index_name: str, vector_index_name: str, username: str = None, password: str = None, secure: bool = False, verify_certs: bool = False):
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

    def get_metadata_by_uid(self, document_uid: str) -> dict:
        """Fetch metadata of a specific document by UID."""
        try:
            response = self.client.get(index=self.metadata_index_name, id=document_uid)
            if response["found"]:
                source = response["_source"]
                # Extract and merge main metadata with front_metadata
                front_metadata = source.pop("front_metadata", {})
                combined_metadata = {**source, **front_metadata}
                return combined_metadata
            else:
                return {}
        except Exception as e:
            logger.error(f"Error while retrieving metadata for UID '{document_uid}': {e}")
            return {}

    def uid_exists(self, document_uid: str) -> bool:
        try:
            return self.client.exists(index=self.metadata_index_name, id=document_uid)
        except Exception as e:
            logger.error(f"Error while checking existence of UID '{document_uid}' in OpenSearch: {e}")
            return False

    def write_metadata(self, document_uid: str, metadata: dict):
        """Write metadata to OpenSearch using the UID as document ID."""
        try:
            response = self.client.index(index=self.metadata_index_name, id=document_uid, body=metadata)
            logger.info(f"Metadata written to index '{self.metadata_index_name}' for UID '{document_uid}'.")
            return response
        except OpenSearchException as e:
            logger.error(f"❌ Failed to write metadata with UID {document_uid}: {e}")
            raise ValueError(f"Failed to write metadata to Opensearch: {e}")

    def update_metadata_field(self, document_uid: str, field: str, value: any):
        try:
            # 1) Partial update of the document in the metadata index
            response_meta = self.client.update(index=self.metadata_index_name, id=document_uid, body={"doc": {field: value}})
            logger.info(f"[METADATA INDEX] Field '{field}' updated for UID '{document_uid}' => {value}")
            # 2) Update (in bulk) chunks in the "vector store" index
            #    - The Painless script will set `ctx._source.metadata.<field>`
            #      to the new value.
            #    - This is done to ensure that the vector index is in sync with the metadata index.
            #    - The field name is prefixed with "metadata." to match the structure in the vector index.
            #    - The script is executed in the context of each document being updated.
            #    - The `params.value` is passed to the script as a parameter.
            #    - The `document_uid` is used to filter the documents to be updated.
            #    - The `term` query is used to match the documents with the specified UID.
            #    - The `update_by_query` API is used to update all matching documents in the vector index.
            script_source = f"ctx._source.metadata.{field} = params.value"
            query_body = {"script": {"source": script_source, "lang": "painless", "params": {"value": value}}, "query": {"term": {"metadata.document_uid": document_uid}}}

            response_vector = self.client.update_by_query(index=self.vector_index_name, body=query_body)
            logger.info(f"[VECTOR INDEX] Field 'metadata.{field}' updated for all chunks with UID='{document_uid}' => {value}")

            return {"metadata_index_response": response_meta, "vector_index_response": response_vector}
        except Exception as e:
            logger.error(f"Error while updating field '{field}' for UID '{document_uid}': {e}")
            raise e

    def get_all_metadata(self, filters_dict: dict):
        """
        Retrieve all document metadata from the index,
        optionally filtered by provided parameters.
        filters_dict is a dict like {"GBU": "TAS", "BU": "X", ...}
        """
        try:
            must_clauses = []
            # For each parameter, build a term query
            # Ex.: field_name="GBU", field_value="TAS"
            for field_name, field_value in filters_dict.items():
                clause = {"term": {f"front_metadata.{field_name}.keyword": field_value}}
                must_clauses.append(clause)

            if not must_clauses:
                # If no parameters were passed, do a match_all
                # This will return all documents in the index
                query = {"match_all": {}}
            else:
                # Combine all filters into a bool must
                # This will return documents that match all the filters
                query = {"bool": {"must": must_clauses}}

            response = self.client.search(
                index=self.metadata_index_name, body={"query": query}, _source=["document_name", "document_uid", "date_added_to_kb", "retrievable", "front_metadata"], size=1000
            )

            hits = response["hits"]["hits"]
            # Merge _source and front_metadata if we want a single object per doc
            # This will create a list of documents with merged metadata
            documents = []
            for h in hits:
                src = h["_source"].copy()
                front_metadata = src.pop("front_metadata", {})
                merged = {**src, **front_metadata}
                documents.append(merged)

            return documents

        except Exception as e:
            logger.error(f"Error while retrieving metadata: {e}")
            return []

    def delete_metadata(self, metadata: dict):
        """Delete metadata from OpenSearch using the UID."""
        try:
            document_uid = metadata.get("document_uid")
            if not document_uid:
                raise ValueError("Missing 'document_uid' in metadata.")

            # Delete from the metadata index
            self.client.delete(index=self.metadata_index_name, id=document_uid)
            logger.info(f"Metadata with UID '{document_uid}' deleted from index '{self.metadata_index_name}'.")

            # Delete from the vector index
            query_delete_document_vector_index = {"query": {"match": {"metadata.document_uid": document_uid}}}
            self.client.delete_by_query(index=self.vector_index_name, body=query_delete_document_vector_index)
            logger.info(f"Metadata with UID '{document_uid}' deleted from index '{self.vector_index_name}'.")

        except Exception as e:
            logger.error(f"Error while deleting metadata for UID '{metadata.get('document_uid', 'N/A')}': {e}")
            raise e

    def save_metadata(self, metadata: dict):
        """Save metadata in Opensearch

        Args:
            metadata (dict): A dictionary containing metadatas
        """
        try:
            self.write_metadata(document_uid=metadata.get("document_uid"), metadata=metadata)
        except Exception as e:
            logger.error(f"❌ Failed to write metadata with UID {metadata.get('document_uid')}: {e}")
            raise ValueError(e)
