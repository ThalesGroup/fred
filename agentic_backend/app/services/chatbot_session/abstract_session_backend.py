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

from typing import List
from abc import ABC, abstractmethod

from app.services.chatbot_session.structure.chat_schema import ChatMessagePayload, SessionSchema

class AbstractSessionStorage(ABC):

    @abstractmethod
    def save_session(self, session: SessionSchema) -> None:
        """
        Save a session to the storage.
        """
        pass

    @abstractmethod
    def get_session(self, session_id: str, user_id: str) -> SessionSchema:
        """
        Retrieve a session by its ID.
        """
        pass

    @abstractmethod
    def delete_session(self, session_id: str, user_id: str) -> bool:
        """
        Delete a session by its ID.
        """
        pass

    @abstractmethod
    def get_sessions_for_user(self, user_id: str) -> List[SessionSchema]:
        """
        Retrieve all sessions for a specific user.
        """
        pass

    @abstractmethod
    def save_messages(self, session_id: str, messages: List[ChatMessagePayload], user_id: str) -> None:
        """Save a batch of messages to the session history."""
        pass

    @abstractmethod
    def get_message_history(self, session_id: str, user_id: str) -> List[ChatMessagePayload]:
        """Retrieve messages for a given session."""
        pass
