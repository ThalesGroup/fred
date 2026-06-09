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


class BaseUserStore(ABC):
    @abstractmethod
    async def update_gcu_version(
        self,
        user_id: UUID,
        gcu_version: GcuVersionsType,
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
        pass
