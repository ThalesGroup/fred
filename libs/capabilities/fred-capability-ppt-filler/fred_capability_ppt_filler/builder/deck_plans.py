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

"""The last deck plan ``build_presentation`` evaluated, per conversation and
agent: the base a ``changes`` call applies to. In the capability's own table,
so any replica and any later turn reads it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import DateTime, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from fred_capability_ppt_filler.builder.analysis_job import (
    PptBuilderBase,
    default_sessionmaker,
)


class DeckPlanRow(PptBuilderBase):
    """One row per conversation and agent instance; no foreign keys."""

    __tablename__ = "cap_ppt_builder_deck_plan"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DeckPlanStore(ABC):
    @abstractmethod
    async def get(self, session_id: str, instance_id: str) -> Optional[str]:
        """The stored plan JSON, or None."""

    @abstractmethod
    async def put(self, session_id: str, instance_id: str, plan_json: str) -> None: ...


class SqlDeckPlanStore(DeckPlanStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    def _key(self, session_id: str, instance_id: str):
        return (
            DeckPlanRow.session_id == session_id,
            DeckPlanRow.agent_instance_id == instance_id,
        )

    async def get(self, session_id: str, instance_id: str) -> Optional[str]:
        async with self._sessionmaker() as session:
            return (
                await session.execute(
                    select(DeckPlanRow.plan_json).where(
                        *self._key(session_id, instance_id)
                    )
                )
            ).scalar_one_or_none()

    async def put(self, session_id: str, instance_id: str, plan_json: str) -> None:
        values = {"plan_json": plan_json, "updated_at": datetime.now(timezone.utc)}
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    update(DeckPlanRow)
                    .where(*self._key(session_id, instance_id))
                    .values(**values)
                )
                if getattr(result, "rowcount", 0):
                    return
        try:
            async with self._sessionmaker() as session:
                async with session.begin():
                    session.add(
                        DeckPlanRow(
                            session_id=session_id,
                            agent_instance_id=instance_id,
                            **values,
                        )
                    )
        except IntegrityError:  # a concurrent call inserted it first
            await self.put(session_id, instance_id, plan_json)


class MemoryDeckPlanStore(DeckPlanStore):
    """For the evaluation harness and tests: one process, no database."""

    def __init__(self) -> None:
        self.plans: Dict[Tuple[str, str], str] = {}

    async def get(self, session_id: str, instance_id: str) -> Optional[str]:
        return self.plans.get((session_id, instance_id))

    async def put(self, session_id: str, instance_id: str, plan_json: str) -> None:
        self.plans[(session_id, instance_id)] = plan_json


_provider: Callable[[], DeckPlanStore] | None = None


def get_deck_plan_store() -> DeckPlanStore:
    if _provider is not None:
        return _provider()
    return SqlDeckPlanStore(default_sessionmaker())


def set_deck_plan_store_provider(provider: Callable[[], DeckPlanStore]) -> None:
    global _provider
    _provider = provider


def clear_deck_plan_store_provider() -> None:
    global _provider
    _provider = None
