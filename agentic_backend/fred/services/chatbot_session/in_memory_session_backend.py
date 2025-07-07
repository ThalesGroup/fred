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
from typing import Dict, List

from fred.services.chatbot_session.abstract_session_backend import AbstractSessionStorage
from fred.services.chatbot_session.session_manager import SessionSchema
from fred.services.chatbot_session.structure.chat_schema import ChatMessagePayload

logger = logging.getLogger(__name__)
class InMemorySessionStorage(AbstractSessionStorage):
    def __init__(self):
        self.sessions: Dict[str, SessionSchema] = {}
        self.history: Dict[str, List[ChatMessagePayload]] = {}

    def save_session(self, session: SessionSchema) -> None:
        self.sessions[session.id] = session

    def get_session(self, session_id: str) -> SessionSchema:
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id]

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.history.pop(session_id, None)
            return True
        return False

    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        #debug
        logger.debug(f"Retrieving sessions for user: {user_id}")
        for session in self.sessions.values():
            logger.debug(f"Session ID: {session.id}, User ID: {session.user_id}")
        return [s for s in self.sessions.values() if s.user_id == user_id]

    def save_messages(self, session_id: str, messages: List[ChatMessagePayload]) -> None:
        if session_id not in self.history:
            self.history[session_id] = []
        self.history[session_id].extend(messages)
        logger.info(f"Saved {len(messages)} messages to session {session_id}")

    def get_message_history(self, session_id: str) -> List[ChatMessagePayload]:
        history = self.history.get(session_id, [])
        return sorted(history, key=lambda m: m.rank if m.rank is not None else 0)
