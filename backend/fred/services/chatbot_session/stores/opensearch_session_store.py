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
from typing import Dict, List, Optional, Any

from fred.services.chatbot_session.abstract_session_backend import AbstractSessionStorage
from fred.services.chatbot_session.abstract_user_authentication_backend import AbstractSecuredResourceAccess
from fred.services.chatbot_session.session_manager import SessionSchema
from fred.services.chatbot_session.structure.chat_schema import ChatMessagePayload
from opensearchpy import OpenSearch, RequestsHttpConnection, OpenSearchException
from fred.common.utils import auth_required

logger = logging.getLogger(__name__)

class OpensearchSessionStorage(AbstractSessionStorage, AbstractSecuredResourceAccess):
    def __init__(self, 
                 host: str, 
                 sessions_index: str, 
                 username: str = None,
                 password: str = None,
                 secure: bool = False,
                 verify_certs: bool = False):

        self.sessions: Dict[str, SessionSchema] = {}
        self.history: Dict[str, List[ChatMessagePayload]] = {}
        
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        
        self.sessions_index = sessions_index

        if not self.client.indices.exists(index=sessions_index):
            self.client.indices.create(index=sessions_index)
            logger.info(f"Opensearch index '{sessions_index}' created.")
        else:
            logger.warning(f"Opensearch index '{sessions_index}' already exists.")
        
    def get_authorized_user_id(self, session_id: str) -> Optional[str]:
        session = self.sessions.get(session_id)
        if session:
            return session.user_id
        return None


    def write_session(self, session_id: str, session: dict) -> Any:
        """
        Write session dict to OpenSearch using the session_id as its uid.
        """
        try:
            response = self.client.index(
                index=self.sessions_index,
                id=session_id,
                body=session
            )
            logger.info(f"Session written to index '{self.sessions.index}' for session_id '{session_id}'.")
            return response
        except OpenSearchException as e:
            logger.error(f"❌ Failed to write session with id {session_id}: {e}")
            raise ValueError(f"Failed to write session to Opensearch: {e}")
        
    def save_session(self, session: SessionSchema) -> None:
        """Save session in Opensearch

        Args:
            session (dict): A dictionary containing a session
        """
        try:
            self.write_session(session_id=session.get("session_id"), session=session)
        except Exception as e:
            logger.error(f"❌ Failed to write session with session_id {session.get("session_id")}: {e}")
            raise ValueError(e)
    
    # @TODO adapt
    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        logger.debug(f"Retrieving sessions for user: {user_id}")
        user_sessions = (session for session in self.sessions.values() if session.user_id == user_id)
        session_ids = []
        for session in user_sessions:
            session_ids.append(session.id)
        logger.debug(f"Retrieved {len(session_ids)} session{"s" if len(session_ids) > 1 else ""} for {user_id}")
        return [s for s in self.sessions.values() if s.user_id == user_id]
   
    # @TODO adapt
    @auth_required
    def get_session(self, session_id: str, user_id: str) -> SessionSchema:
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id]
    
    # @TODO adapt
    @auth_required
    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete session from OpenSearch using the session_id."""
        try:
            self.client.delete(index=self.sessions_index, id=session_id)
            logger.info(f"Session with session_id '{session_id}' deleted from index '{self.sessions_index}'.")

        except Exception as e:
            logger.error(f"Error while deleting session for session_id '{session_id}': {e}")
            raise e


    # @TODO adapt
    @auth_required
    def save_messages(self, session_id: str, messages: List[ChatMessagePayload], user_id: str) -> None:
        if session_id not in self.history:
            self.history[session_id] = []
        self.history[session_id].extend(messages)
        logger.info(f"Saved {len(messages)} messages to session {session_id}")

    # @TODO adapt
    @auth_required
    def get_message_history(self, session_id: str, user_id: str) -> List[ChatMessagePayload]:
        history = self.history.get(session_id, [])
        return sorted(history, key=lambda m: m.rank if m.rank is not None else 0)