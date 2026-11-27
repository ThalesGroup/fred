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

"""The last workbook `create_spreadsheet` delivered, per conversation and agent:
the base a `changes` call applies to (design.md D11).

In the capability's own table, so any replica and any later turn reads it, after
history trimming too. Services never bind at import time: the store resolves
through an overridable provider, and the engine is built on first use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SpreadsheetBase(DeclarativeBase):
    """The capability's own metadata: never shared with core or another capability."""


class WorkbookRow(SpreadsheetBase):
    """One row per conversation and agent instance; no foreign keys."""

    __tablename__ = "cap_spreadsheet_workbook"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workbook_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(128), nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


@dataclass(frozen=True)
class StoredWorkbook:
    workbook_id: str
    version: int
    file_name: str
    # The request as delivered (sheets, columns, values, formulas), as JSON.
    spec_json: str


class WorkbookSpecStore(ABC):
    @abstractmethod
    async def get(self, session_id: str, instance_id: str) -> StoredWorkbook | None:
        """The last delivered workbook, or None."""

    @abstractmethod
    async def put(
        self, session_id: str, instance_id: str, workbook: StoredWorkbook
    ) -> None: ...

    @abstractmethod
    async def clear(self, session_id: str, instance_id: str) -> None: ...


class SqlWorkbookSpecStore(WorkbookSpecStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @staticmethod
    def _key(session_id: str, instance_id: str):
        return (
            WorkbookRow.session_id == session_id,
            WorkbookRow.agent_instance_id == instance_id,
        )

    async def get(self, session_id: str, instance_id: str) -> StoredWorkbook | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(WorkbookRow).where(*self._key(session_id, instance_id))
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return StoredWorkbook(
            row.workbook_id, row.version, row.file_name, row.spec_json
        )

    async def put(
        self, session_id: str, instance_id: str, workbook: StoredWorkbook
    ) -> None:
        values = {
            "workbook_id": workbook.workbook_id,
            "version": workbook.version,
            "file_name": workbook.file_name,
            "spec_json": workbook.spec_json,
            "updated_at": datetime.now(timezone.utc),
        }
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    update(WorkbookRow)
                    .where(*self._key(session_id, instance_id))
                    .values(**values)
                )
                if getattr(result, "rowcount", 0):
                    return
        try:
            async with self._sessionmaker() as session:
                async with session.begin():
                    session.add(
                        WorkbookRow(
                            session_id=session_id,
                            agent_instance_id=instance_id,
                            **values,
                        )
                    )
        except IntegrityError:  # a concurrent delivery inserted it first
            await self.put(session_id, instance_id, workbook)

    async def clear(self, session_id: str, instance_id: str) -> None:
        async with self._sessionmaker() as session:
            async with session.begin():
                await session.execute(
                    delete(WorkbookRow).where(*self._key(session_id, instance_id))
                )


class MemoryWorkbookSpecStore(WorkbookSpecStore):
    """For tests and evaluations: one process, no database."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], StoredWorkbook] = {}

    async def get(self, session_id: str, instance_id: str) -> StoredWorkbook | None:
        return self.rows.get((session_id, instance_id))

    async def put(
        self, session_id: str, instance_id: str, workbook: StoredWorkbook
    ) -> None:
        self.rows[(session_id, instance_id)] = workbook

    async def clear(self, session_id: str, instance_id: str) -> None:
        self.rows.pop((session_id, instance_id), None)


_provider: Callable[[], WorkbookSpecStore] | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """One engine per pod, from the pod's own `storage.postgres` configuration."""

    global _sessionmaker
    if _sessionmaker is None:
        from fred_core.common import load_postgres_config
        from fred_core.sql import create_async_engine_from_config

        engine = create_async_engine_from_config(load_postgres_config())
        _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return _sessionmaker


def get_workbook_spec_store() -> WorkbookSpecStore:
    if _provider is not None:
        return _provider()
    return SqlWorkbookSpecStore(_default_sessionmaker())


def set_workbook_spec_store_provider(provider: Callable[[], WorkbookSpecStore]) -> None:
    global _provider
    _provider = provider


def clear_workbook_spec_store_provider() -> None:
    global _provider
    _provider = None
