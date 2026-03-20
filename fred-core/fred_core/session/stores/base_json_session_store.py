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

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncConnection


class BaseJsonSessionStore(ABC):
    """Abstract contract for JSON session persistence backends."""

    @abstractmethod
    async def save(
        self,
        *,
        session_id: str,
        user_id: str,
        updated_at: datetime,
        payload: Mapping[str, Any],
        team_id: str | None = None,
        agent_id: str = "",
    ) -> None:
        """Persist a session payload."""

    @abstractmethod
    async def save_with_conn(
        self,
        conn: AsyncConnection,
        *,
        session_id: str,
        user_id: str,
        updated_at: datetime,
        payload: Mapping[str, Any],
        team_id: str | None = None,
        agent_id: str = "",
    ) -> None:
        """Persist a session payload using an existing transaction connection."""

    @abstractmethod
    async def get_payload(self, session_id: str) -> dict[str, Any] | None:
        """Return one session payload by id."""

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete one session payload by id."""

    @abstractmethod
    async def get_payloads_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all payloads for a user, ordered by recency."""

    @abstractmethod
    async def count_for_user(self, user_id: str) -> int:
        """Return session count for a user."""
