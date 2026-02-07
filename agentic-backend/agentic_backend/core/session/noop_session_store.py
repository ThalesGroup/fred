from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore


class NoOpSessionStore(BaseSessionStore):
    """A session store that does nothing. Useful for testing or ephemeral sessions."""

    async def save(self, session: SessionSchema) -> None:
        """No-op save method."""
        pass

    async def get(self, session_id: str) -> SessionSchema | None:
        """No-op get method that always returns None."""
        return None

    async def delete(self, session_id: str) -> None:
        """No-op delete method."""
        pass

    async def get_for_user(self, user_id: str) -> list[SessionSchema]:
        """No-op get_for_user method that always returns an empty list."""
        return []

    async def save_with_conn(self, conn, session: SessionSchema) -> None:
        """Reuse no-op save for transactional path."""
        await self.save(session)
