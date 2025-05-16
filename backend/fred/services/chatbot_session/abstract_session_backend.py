from typing import List
from abc import ABC, abstractmethod

from services.chatbot_session.structure.chat_schema import ChatMessagePayload, SessionSchema

class AbstractSessionStorage(ABC):

    @abstractmethod
    def save_session(self, session: SessionSchema) -> None:
        """
        Save a session to the storage.
        """
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> SessionSchema:
        """
        Retrieve a session by its ID.
        """
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
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
    def save_messages(self, session_id: str, messages: List[ChatMessagePayload]) -> None:
        """Save a batch of messages to the session history."""
        pass

    @abstractmethod
    def get_message_history(self, session_id: str) -> List[ChatMessagePayload]:
        """Retrieve messages for a given session."""
        pass
