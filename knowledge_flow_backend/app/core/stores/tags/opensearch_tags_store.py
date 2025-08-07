# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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

from fred_core import KeycloakUser
from fred_core import ThreadSafeLRUCache

from opensearchpy import ConflictError, NotFoundError, OpenSearch, RequestsHttpConnection

from app.core.stores.tags.base_tag_store import BaseTagStore, TagAlreadyExistsError, TagNotFoundError
from app.features.tag.structure import Tag

logger = logging.getLogger(__name__)

# ==============================================================================
# TAGS_INDEX_MAPPING
# ==============================================================================
# This mapping defines the OpenSearch schema used for storing Tag objects.
# Fields:
#   - id: Unique identifier for the tag (type: keyword)
#   - name: Display name of the tag (type: text and keyword)
#   - color: Color code for display (type: keyword)
#   - owner_id: User UID who owns this tag (type: keyword)
# ==============================================================================

TAGS_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "owner_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "description": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "type": {"type": "keyword"},  # TagType enum (e.g., "library")
        }
    }
}


class OpenSearchTagStore(BaseTagStore):
    """
    OpenSearch implementation of BaseTagStore.
    Automatically creates the index if it doesn't exist.
    Tags are scoped per user via `owner_id`.
    """

    default_params: dict[str, str] = {
        # Important to wait for the changes to be effective before sending response
        # (if not, you can send a DELETE tag request, send a GET tags request to list
        # them and still get the one you just deleted because OpenSearch hasn't deleted it)
        "refresh": "wait_for",
    }

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
        self._cache = ThreadSafeLRUCache[str, Tag](max_size=1000)
        self.index_name = index

        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name, body=TAGS_INDEX_MAPPING)
            logger.info(f"[TAGS] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(f"[TAGS] OpenSearch index '{self.index_name}' already exists.")

    def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        try:
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"owner_id": user.uid}}
                            # {"term": {"type": tag_type.value}},
                        ]
                    }
                }
            }
            response = self.client.search(index=self.index_name, body=query, params={"size": 10000})
            return [Tag(**hit["_source"]) for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"[TAGS] Failed to list tags for user '{user.uid}': {e}")
            raise

    def get_tag_by_id(self, tag_id: str) -> Tag:
        if cached := self._cache.get(tag_id):
            logger.debug(f"[TAGS] Cache hit for tag '{tag_id}'")
            return cached
        try:
            response = self.client.get(index=self.index_name, id=tag_id)
            return Tag(**response["_source"])
        except NotFoundError:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        except Exception as e:
            logger.error(f"[TAGS] Failed to get tag '{tag_id}': {e}")
            raise

    def create_tag(self, tag: Tag) -> Tag:
        try:
            self.client.index(
                index=self.index_name,
                id=tag.id,
                body=tag.model_dump(mode="json"),
                params=self.default_params,
            )
            self._cache.set(tag.id, tag)
            logger.info(f"[TAGS] Created tag '{tag.id}' for user '{tag.owner_id}'")
            return tag
        except ConflictError:
            raise TagAlreadyExistsError(f"Tag with id '{tag.id}' already exists.")
        except Exception as e:
            logger.error(f"[TAGS] Failed to create tag '{tag.id}': {e}")
            raise

    def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        try:
            self.get_tag_by_id(tag_id)  # ensure it exists
            self.client.index(
                index=self.index_name,
                id=tag_id,
                body=tag.model_dump(mode="json"),
                params=self.default_params,
            )
            self._cache.set(tag_id, tag)
            logger.info(f"[TAGS] Updated tag '{tag_id}'")
            return tag
        except TagNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[TAGS] Failed to update tag '{tag_id}': {e}")
            raise

    def delete_tag_by_id(self, tag_id: str) -> None:
        self._cache.delete(tag_id)
        try:
            self.client.delete(
                index=self.index_name,
                id=tag_id,
                params=self.default_params,
            )
            logger.info(f"[TAGS] Deleted tag '{tag_id}'")
        except NotFoundError:
            raise TagNotFoundError(f"Tag with id '{tag_id}' not found.")
        except Exception as e:
            logger.error(f"[TAGS] Failed to delete tag '{tag_id}': {e}")
            raise
