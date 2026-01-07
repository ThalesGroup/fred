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

from fred_core import ThreadSafeLRUCache, validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection

from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "updated_at": {"type": "date"},
            "file_names": {
                "type": "keyword"
            },  # Stores file names as exact-matchable strings
        }
    },
}


class OpensearchSessionStore(BaseSessionStore):
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
        self._cache = ThreadSafeLRUCache[str, SessionSchema](max_size=1000)
        self._user_cache = ThreadSafeLRUCache[str, List[SessionSchema]](max_size=1000)
        self.index = index
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, body=MAPPING)
            logger.info(f"OpenSearch index '{index}' created with mapping.")
        else:
            logger.info(f"OpenSearch index '{index}' already exists.")
            # Validate existing mapping matches expected mapping
            validate_index_mapping(self.client, index, MAPPING)

    def save(self, session: SessionSchema) -> None:
        try:
            session_dict = session.model_dump()
            self.client.index(index=self.index, id=session.id, body=session_dict)
            self._cache_session(session)
            logger.debug(f"Session {session.id} saved for user {session.user_id}")
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise

    def get(self, session_id: str) -> SessionSchema | None:
        try:
            if cached := self._cache.get(session_id):
                logger.debug(f"[cache hit] session_id={session_id}")
                return cached
            response = self.client.get(index=self.index, id=session_id)
            session_data = response["_source"]
            return SessionSchema(**session_data)
        except NotFoundError:
            # a missing doc is not an error; be quiet or use debug
            logger.debug(f"[not found] session_id={session_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    def delete(self, session_id: str) -> None:
        try:
            session = self._cache.delete(session_id)
            if session:
                self._remove_from_user_cache(session.user_id, session_id)
            self.client.delete(index=self.index, id=session_id)
            # query = {"query": {"term": {"session_id.keyword": {"value": session_id}}}}
            # self.client.delete_by_query(index=self.history_index, body=query)
            # logger.info(f"Deleted session {session_id} and its messages")
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")

    def get_for_user(self, user_id: str) -> List[SessionSchema]:
        cached = self._user_cache.get(user_id)
        if cached is not None:
            logger.debug("[SESSION][OS] user cache hit for user_id=%s", user_id)
            return cached

        try:
            query = {"query": {"term": {"user_id": {"value": user_id}}}}
            response = self.client.search(
                params={"size": 10000},
                index=self.index,
                body=query,
            )
            sessions = [
                SessionSchema(**hit["_source"]) for hit in response["hits"]["hits"]
            ]
            for s in sessions:
                self._cache_session(s)
            logger.debug(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions
        except Exception as e:
            logger.error(f"Failed to fetch sessions for user {user_id}: {e}")
            return []

    # ---------- cache helpers ----------

    def _cache_session(self, session: SessionSchema) -> None:
        self._cache.set(session.id, session)
        existing = self._user_cache.get(session.user_id) or []
        # deduplicate and keep newest first
        remaining = [s for s in existing if s.id != session.id]
        remaining.append(session)
        remaining.sort(key=lambda s: s.updated_at, reverse=True)
        self._user_cache.set(session.user_id, remaining)

    def _remove_from_user_cache(self, user_id: str, session_id: str) -> None:
        existing = self._user_cache.get(user_id)
        if existing is None:
            return
        filtered = [s for s in existing if s.id != session_id]
        self._user_cache.set(user_id, filtered)
