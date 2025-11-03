from typing import Optional

from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore


class NoOpSessionStore(BaseSessionStore):
    """A session store that does nothing. Useful for testing or ephemeral sessions."""

    def save(self, session: SessionSchema) -> None:
        """No-op save method."""
        pass

    def get(self, session_id: str) -> Optional[SessionSchema]:
        """No-op get method that always returns None."""
        return None

    def delete(self, session_id: str) -> None:
        """No-op delete method."""
        pass

    def get_for_user(self, user_id: str) -> list[SessionSchema]:
        """No-op get_for_user method that always returns an empty list."""
        return []
