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
from typing import Any


class BaseSessionStore(ABC):
    """Application-level session store contract."""

    @abstractmethod
    async def save(self, session: Any) -> None:
        """Save one session."""

    @abstractmethod
    async def get(self, session_id: str) -> Any | None:
        """Retrieve one session by ID."""

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete one session by ID."""

    @abstractmethod
    async def get_for_user(self, user_id: str) -> list[Any]:
        """Retrieve all sessions for a user."""

    @abstractmethod
    async def count_for_user(self, user_id: str) -> int:
        """Count sessions for a user."""

    @abstractmethod
    async def save_with_conn(self, conn: Any, session: Any) -> None:
        """Save one session using an existing transaction connection."""
