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

    async def count_for_user(self, user_id: str) -> int:
        """No-op count_for_user method that always returns 0."""
        return 0
