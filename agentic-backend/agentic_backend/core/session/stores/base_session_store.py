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

from abc import ABC, abstractmethod
from typing import Any, List

from agentic_backend.core.chatbot.chat_schema import (
    SessionSchema,
)


class BaseSessionStore(ABC):
    @abstractmethod
    async def save(self, session: SessionSchema) -> None:
        """
        Save a session to the storage.
        """
        pass

    @abstractmethod
    async def get(self, session_id: str) -> SessionSchema | None:
        """
        Retrieve a session by its ID.
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """
        Delete a session by its ID.
        """
        pass

    @abstractmethod
    async def get_for_user(self, user_id: str) -> List[SessionSchema]:
        """
        Retrieve all sessions for a specific user.
        """
        pass

    @abstractmethod
    async def count_for_user(self, user_id: str) -> int:
        """
        Return how many sessions exist for the given user_id.
        Should be efficient (COUNT in the backend, not full fetch).
        """
        pass

    @abstractmethod
    async def save_with_conn(self, conn: Any, session: SessionSchema) -> None:
        """
        Reuse an existing DB connection/transaction.
        """
        pass
