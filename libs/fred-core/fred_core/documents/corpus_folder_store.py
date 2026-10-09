# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.documents.corpus_folder_models import CorpusFolder, CorpusFolderRow
from fred_core.sql.async_session import make_session_factory, use_session


class CorpusFolderStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(
        self, folder_id: str, session: AsyncSession | None = None
    ) -> CorpusFolder | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(CorpusFolderRow, folder_id)
            return CorpusFolder.model_validate(row) if row is not None else None

    async def create(
        self,
        folder_id: str,
        space_id: str,
        name: str,
        *,
        parent_id: str | None = None,
        description: str | None = None,
        synchronized_by: str | None = None,
        session: AsyncSession | None = None,
    ) -> CorpusFolder:
        async with use_session(self._sessions, session) as s:
            row = CorpusFolderRow(
                id=folder_id,
                space_id=space_id,
                parent_id=parent_id,
                name=name.strip(),
                description=description,
                synchronized_by=synchronized_by,
            )
            s.add(row)
            await s.flush()
            return CorpusFolder.model_validate(row)

    async def update(
        self,
        folder_id: str,
        name: str,
        description: str | None,
        session: AsyncSession | None = None,
    ) -> CorpusFolder | None:
        """Rename/edit descriptive metadata; ownership and parent are immutable."""
        async with use_session(self._sessions, session) as s:
            row = await s.scalar(
                update(CorpusFolderRow)
                .where(CorpusFolderRow.id == folder_id)
                .values(
                    name=name.strip(), description=description, updated_at=func.now()
                )
                .returning(CorpusFolderRow)
            )
            return CorpusFolder.model_validate(row) if row is not None else None

    async def list_children(
        self,
        space_ids: tuple[str, ...],
        parent_id: str | None,
        *,
        limit: int,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[CorpusFolder]:
        async with use_session(self._sessions, session) as s:
            rows = await s.scalars(
                select(CorpusFolderRow)
                .where(
                    CorpusFolderRow.space_id.in_(space_ids),
                    CorpusFolderRow.parent_id == parent_id,
                )
                .order_by(CorpusFolderRow.name, CorpusFolderRow.id)
                .offset(offset)
                .limit(limit)
            )
            return [CorpusFolder.model_validate(row) for row in rows]
