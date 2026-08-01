from __future__ import annotations

from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.prompt_models import PromptCategoryRow


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PromptCategoryAlreadyExistsError(Exception):
    """Raised when one category name is already used inside the same team."""


class PromptCategoryRecord:
    """In-memory projection of one DB prompt_category row."""

    def __init__(
        self,
        *,
        category_id: str,
        team_id: TeamId,
        name: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.category_id = category_id
        self.team_id = team_id
        self.name = name
        self.created_at = created_at
        self.updated_at = updated_at


def _row_to_record(row: PromptCategoryRow) -> PromptCategoryRecord:
    return PromptCategoryRecord(
        category_id=row.category_id,
        team_id=TeamId(row.team_id),
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PromptCategoryStore:
    """Team-owned prompt categories — same CRUD shape as `PromptStore`.

    Why this store exists (PROMPT-09):
    - categories moved from a fixed, platform-wide enum to per-team content
      that any `team_editor` can create, rename, and delete
    - deletion enforcement (a category still referenced by a prompt cannot be
      removed) lives in the service layer, which composes this store with
      `PromptStore.count_by_category`
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        record: PromptCategoryRecord,
        session: AsyncSession | None = None,
    ) -> PromptCategoryRecord:
        now = _utcnow()
        row = PromptCategoryRow(
            category_id=record.category_id,
            team_id=str(record.team_id),
            name=record.name,
            created_at=record.created_at or now,
            updated_at=record.updated_at or now,
        )
        try:
            async with use_session(self._sessions, session) as s:
                s.add(row)
        except IntegrityError as exc:
            raise PromptCategoryAlreadyExistsError(record.name) from exc
        result = await self.get_for_team(record.category_id, record.team_id)
        assert result is not None
        return result

    async def get_for_team(
        self,
        category_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> PromptCategoryRecord | None:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PromptCategoryRow).where(
                            PromptCategoryRow.category_id == category_id,
                            PromptCategoryRow.team_id == str(team_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            return None
        return _row_to_record(rows[0])

    async def list_by_team(
        self,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> list[PromptCategoryRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PromptCategoryRow)
                        .where(PromptCategoryRow.team_id == str(team_id))
                        .order_by(PromptCategoryRow.name.asc())
                    )
                )
                .scalars()
                .all()
            )
        return [_row_to_record(row) for row in rows]

    async def update(
        self,
        category_id: str,
        team_id: TeamId,
        *,
        name: str,
        session: AsyncSession | None = None,
    ) -> PromptCategoryRecord | None:
        """Rename one team-scoped category. Returns `None` if not found in `team_id`."""

        try:
            async with use_session(self._sessions, session) as s:
                result: CursorResult = await s.execute(  # type: ignore[assignment]
                    update(PromptCategoryRow)
                    .where(
                        PromptCategoryRow.category_id == category_id,
                        PromptCategoryRow.team_id == str(team_id),
                    )
                    .values(name=name, updated_at=_utcnow())
                )
                if result.rowcount == 0:
                    return None
        except IntegrityError as exc:
            raise PromptCategoryAlreadyExistsError(name) from exc
        return await self.get_for_team(category_id, team_id, session)

    async def delete(
        self,
        category_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> bool:
        """Delete one category scoped to team_id. Returns True if a row was removed.

        Callers must check `PromptStore.count_by_category` first — this store
        has no visibility into the `prompt` table and does not enforce the
        "still in use" invariant itself.
        """

        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(PromptCategoryRow).where(
                    PromptCategoryRow.category_id == category_id,
                    PromptCategoryRow.team_id == str(team_id),
                )
            )
        return result.rowcount > 0
