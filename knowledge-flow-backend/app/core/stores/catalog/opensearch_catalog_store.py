# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import List

from fred_core import validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection

from app.core.stores.catalog.base_catalog_store import PullFileEntry

logger = logging.getLogger(__name__)

CATALOG_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "source_tag": {"type": "keyword"},
            "path": {"type": "keyword"},
            "size": {"type": "long"},
            "modified_time": {"type": "double"},
            "hash": {"type": "keyword"},
        }
    }
}


class OpenSearchCatalogStore:
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
        self.index_name = index

        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name, body=CATALOG_INDEX_MAPPING)
            logger.info(f"[CATALOG] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(f"[CATALOG] OpenSearch index '{self.index_name}' already exists.")
            # Validate existing mapping matches expected mapping
            validate_index_mapping(self.client, self.index_name, CATALOG_INDEX_MAPPING)

    def save_entries(self, source_tag: str, entries: List[PullFileEntry]):
        try:
            # First, delete all existing entries for the source_tag
            self.client.delete_by_query(
                index=self.index_name,
                body={"query": {"term": {"source_tag": source_tag}}},
            )

            # Bulk insert new entries
            actions = [
                {
                    "_index": self.index_name,
                    "_id": f"{source_tag}:{entry.path}",
                    "_source": {
                        "source_tag": source_tag,
                        "path": entry.path,
                        "size": entry.size,
                        "modified_time": entry.modified_time,
                        "hash": entry.hash,
                    },
                }
                for entry in entries
            ]

            if actions:
                from opensearchpy.helpers import bulk

                success, _ = bulk(self.client, actions, refresh=True)
                logger.info(f"[CATALOG] Indexed {success} entries for '{source_tag}'")
            else:
                logger.info(f"[CATALOG] No entries to index for '{source_tag}'")
        except Exception as e:
            logger.error(f"[CATALOG] Failed to save entries for '{source_tag}': {e}")
            raise

    def add_entries(self, source_tag: str, entries: List[PullFileEntry]):
        try:
            # Récupération des entrées existantes pour le source_tag
            existing_docs = self.client.search(
                index=self.index_name,
                body={"query": {"term": {"source_tag": source_tag}}, "_source": ["path", "hash"]},
                params={"size": 10000},
            )["hits"]["hits"]

            existing = {doc["_source"]["path"]: doc["_source"]["hash"] for doc in existing_docs}

            from opensearchpy.helpers import bulk

            actions = []

            for entry in entries:
                doc_id = f"{source_tag}:{entry.path}"
                if entry.path in existing:
                    if existing[entry.path] != entry.hash:
                        # Met à jour le document si le hash a changé
                        actions.append(
                            {
                                "_op_type": "update",
                                "_index": self.index_name,
                                "_id": doc_id,
                                "doc": {
                                    "size": entry.size,
                                    "modified_time": entry.modified_time,
                                    "hash": entry.hash,
                                },
                            }
                        )
                else:
                    # Nouveau document
                    actions.append(
                        {
                            "_op_type": "index",
                            "_index": self.index_name,
                            "_id": doc_id,
                            "_source": {
                                "source_tag": source_tag,
                                "path": entry.path,
                                "size": entry.size,
                                "modified_time": entry.modified_time,
                                "hash": entry.hash,
                            },
                        }
                    )

            if actions:
                success, _ = bulk(self.client, actions, refresh=True)
                logger.info(f"[CATALOG] add_entries: {success} entries added/updated for '{source_tag}'")
            else:
                logger.info(f"[CATALOG] add_entries: No changes for '{source_tag}'")
        except Exception as e:
            logger.error(f"[CATALOG] Failed to add entries for '{source_tag}': {e}")
            raise

    def delete_entries(self, source_tag: str, entries: List[PullFileEntry]):
        if not entries:
            return

        try:
            from opensearchpy.helpers import bulk

            actions = [
                {
                    "_op_type": "delete",
                    "_index": self.index_name,
                    "_id": f"{source_tag}:{entry.path}",
                }
                for entry in entries
            ]

            success, _ = bulk(self.client, actions, refresh=True)
            logger.info(f"[CATALOG] delete_entries: {success} entries deleted for '{source_tag}'")
        except Exception as e:
            logger.error(f"[CATALOG] Failed to delete entries for '{source_tag}': {e}")
            raise

    def list_entries(self, source_tag: str) -> List[PullFileEntry]:
        try:
            results = self.client.search(
                index=self.index_name,
                body={"query": {"term": {"source_tag": source_tag}}},
                params={"size": 10000},
            )
            hits = results["hits"]["hits"]
            return [
                PullFileEntry(
                    path=hit["_source"]["path"],
                    size=hit["_source"]["size"],
                    modified_time=hit["_source"]["modified_time"],
                    hash=hit["_source"]["hash"],
                )
                for hit in hits
            ]
        except NotFoundError:
            return []
        except Exception as e:
            logger.error(f"[CATALOG] Failed to list entries for '{source_tag}': {e}")
            raise
