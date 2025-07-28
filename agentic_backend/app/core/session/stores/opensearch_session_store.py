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
from opensearchpy import OpenSearch, RequestsHttpConnection
from app.core.session.stores.abstract_session_backend import AbstractSessionStorage
from app.core.session.stores.abstract_user_authentication_backend import AbstractSecuredResourceAccess
from app.core.session.session_manager import SessionSchema
from app.core.chatbot.chat_schema import ChatMessagePayload
from app.common.utils import authorization_required
from app.common.error import AuthorizationSentinel, SESSION_NOT_INITIALIZED

logger = logging.getLogger(__name__)

class OpensearchSessionStorage(AbstractSessionStorage, AbstractSecuredResourceAccess):
    def __init__(self, 
                 host: str,
                 sessions_index: str,
                 history_index: str,
                 username: str = None,
                 password: str = None,
                 secure: bool = False,
                 verify_certs: bool = False):
        
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        
        self.sessions_index = sessions_index
        self.history_index = history_index

        for index in [sessions_index, history_index]:
            if not self.client.indices.exists(index=index):
                self.client.indices.create(index=index)
                logger.info(f"Opensearch index '{index}' created.")
            else:
                logger.debug(f"Opensearch index '{index}' already exists.")

    def get_authorized_user_id(self, session_id: str) -> str | None | AuthorizationSentinel:
        try:
            session = self.client.get(index=self.sessions_index, id=session_id)
            return session["_source"].get("user_id")
        except Exception as e:
            logger.warning(f"Could not get user_id for session {session_id}: {e}")
            return SESSION_NOT_INITIALIZED
    
    def save_session(self, session: SessionSchema) -> None:
        try:
            session_dict = session.model_dump()
            self.client.index(index=self.sessions_index, id=session.id, body=session_dict)
            logger.debug(f"Session {session.id} saved for user {session.user_id}")
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise

    @authorization_required
    def get_session(self, session_id: str, user_id: str) -> Optional[SessionSchema]:
        try:
            response = self.client.get(index=self.sessions_index, id=session_id)
            session_data = response["_source"]
            return SessionSchema(**session_data)
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    @authorization_required
    def delete_session(self, session_id: str, user_id: str) -> bool:
        try:
            self.client.delete(index=self.sessions_index, id=session_id)
            query = {
                "query": {
                    "term": {
                        "session_id.keyword": {
                            "value": session_id
                            }
                        }
                    }
                }
            self.client.delete_by_query(
                index=self.history_index,
                body = query
            )
            logger.info(f"Deleted session {session_id} and its messages")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    
    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        try:
            query = {
                "query": {
                    "term": {
                        "user_id.keyword": {
                            "value": user_id
                        }
                    }
                }
            }
            response = self.client.search(index=self.sessions_index, body=query, size=1000)
            sessions = [SessionSchema(**hit["_source"]) for hit in response["hits"]["hits"]]
            logger.debug(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions
        except Exception as e:
            logger.error(f"Failed to fetch sessions for user {user_id}: {e}")
            return []

    @authorization_required
    def save_messages(self, session_id: str, messages: List[ChatMessagePayload], user_id: str) -> None:
        try:
            actions = [
                {
                    "index": {
                        "_index": self.history_index,
                        "_id": f"{session_id}-{message.rank or i}"
                    }
                }
                for i, message in enumerate(messages)
            ]
            bodies = [msg.model_dump() for msg in messages]
            bulk_body = [entry for pair in zip(actions, bodies) for entry in pair]

            # OpenSearch Bulk API
            self.client.bulk(body=bulk_body)
            self.client.indices.refresh(index=self.history_index) # Necessary due to indexing delay for whoever wants to access the newly stored data (from save_messages).
            logger.info(f"Saved {len(messages)} messages for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to save messages for session {session_id}: {e}")
            raise

    @authorization_required
    def get_message_history(self, session_id: str, user_id: str) -> List[ChatMessagePayload]:
        try:
            query = {
                "query": {
                    "term": {
                        "session_id.keyword": {
                            "value": session_id
                        }
                    }
                },
                "sort": [
                    {
                        "rank": {
                            "order": "asc",
                            "unmapped_type" : "integer"
                        }
                    }
                    
                ],
                "size": 1000
            }
            response = self.client.search(index=self.history_index, body=query)
            return [ChatMessagePayload(**hit["_source"]) for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Failed to retrieve messages for session {session_id}: {e}")
            return []
