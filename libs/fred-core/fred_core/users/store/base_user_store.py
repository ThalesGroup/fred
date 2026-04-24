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
