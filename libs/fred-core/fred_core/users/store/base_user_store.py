# Copyright Thales 2026
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
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..user_models import GcuVersionsType, UserRow


class AmbiguousUsernameError(ValueError):
    """Distinct local identities share a username needed for resolution."""

    def __init__(self, usernames: list[str]) -> None:
        self.usernames = tuple(sorted(set(usernames)))
        super().__init__(
            "Local usernames resolve to multiple identities (ambiguous_username): "
            + ", ".join(self.usernames)
        )


class BaseUserStore(ABC):
    @abstractmethod
    async def update_gcu_version(
        self,
        user_id: UUID,
        gcu_version: str | GcuVersionsType,
        session: AsyncSession | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def find_user_by_id(
        self, user_id: UUID, session: AsyncSession | None = None
    ) -> Optional[UserRow]:
        pass

    @abstractmethod
    async def increment_current_storage_size(
        self,
        user_id: UUID,
        delta: int,
        session: AsyncSession | None = None,
    ) -> None:
        """Adjust a user's recorded personal storage usage by `delta` bytes.

        `delta` is negative when storage is released (a document was permanently
        deleted). Implementations MUST NOT persist a negative usage: clamp at 0
        and log, because usage is a byte count and `check_quota` reads this value
        as the sole enforcement input — a negative usage silently grants free
        quota (#2149).
        """

    @abstractmethod
    async def upsert_identity(
        self,
        user_id: UUID,
        username: str,
        email: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """Record a person's current identity without changing their local state."""

    @abstractmethod
    async def search_identities(
        self, query: str, limit: int
    ) -> list[dict[str, str | None]]:
        """Search signed-in people by name or email."""

    @abstractmethod
    async def list_identities(
        self, offset: int, limit: int
    ) -> list[dict[str, str | None]]:
        """Return one page of signed-in people."""

    @abstractmethod
    async def get_identities(self, ids: list[UUID]) -> list[dict[str, str | None]]:
        """Return signed-in people with these IDs."""

    @abstractmethod
    async def count_identities(self) -> int:
        """Count signed-in people."""

    @abstractmethod
    async def find_ids_by_usernames(
        self, usernames: list[str] | None = None
    ) -> dict[str, str]:
        """Resolve usernames; raise AmbiguousUsernameError for distinct matching IDs."""

    @abstractmethod
    async def identity_exists(self, user_id: UUID) -> bool:
        """Whether a signed-in identity exists."""
