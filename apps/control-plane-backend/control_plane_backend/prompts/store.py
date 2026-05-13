from __future__ import annotations

from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, literal, select, union_all, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.prompt_models import PromptRow


def _utcnow() -> datetime:
    """Return a stable UTC timestamp for local DB writes.

    Why this helper exists:
    - prompt-library writes should use the same timezone-aware timestamp policy
      as the other control-plane metadata stores

    How to use it:
    - call when creating or updating DB-backed prompt rows

    Example:
    - `created_at = _utcnow()`
    """

    return datetime.now(timezone.utc).replace(microsecond=0)


class PromptAlreadyExistsError(Exception):
    """Raised when one prompt name is already used inside the same team."""


class PromptRecord:
    """In-memory projection of one DB prompt row."""

    def __init__(
        self,
        *,
        prompt_id: str,
        team_id: TeamId,
        name: str,
        description: str | None,
        text: str,
        created_by: str | None,
        version: int = 1,
        import_count: int = 0,
        session_count: int = 0,
        score: float | None = None,
        avg_input_tokens: int | None = None,
        avg_output_tokens: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.prompt_id = prompt_id
        self.team_id = team_id
        self.name = name
        self.description = description
        self.text = text
        self.created_by = created_by
        self.version = version
        self.import_count = import_count
        self.session_count = session_count
        self.score = score
        self.avg_input_tokens = avg_input_tokens
        self.avg_output_tokens = avg_output_tokens
        self.created_at = created_at
        self.updated_at = updated_at


class ContextPromptRecord:
    """Projection for the context-picker union query (personal + team prompts)."""

    def __init__(
        self,
        *,
        prompt_id: str,
        name: str,
        description: str | None,
        scope: str,
        version: int,
        session_count: int,
        score: float | None,
    ) -> None:
        self.prompt_id = prompt_id
        self.name = name
        self.description = description
        self.scope = scope
        self.version = version
        self.session_count = session_count
        self.score = score


def _row_to_record(row: PromptRow) -> PromptRecord:
    return PromptRecord(
        prompt_id=row.prompt_id,
        team_id=TeamId(row.team_id),
        name=row.name,
        description=row.description,
        text=row.text,
        created_by=row.created_by,
        version=row.version,
        import_count=row.import_count,
        session_count=row.session_count,
        score=row.score,
        avg_input_tokens=row.avg_input_tokens,
        avg_output_tokens=row.avg_output_tokens,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PromptStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        record: PromptRecord,
        session: AsyncSession | None = None,
    ) -> PromptRecord:
        """
        Persist one new team-scoped prompt-library record.

        Why this function exists:
        - prompt management must stay a first-class control-plane storage
          surface independent of managed-agent instances
        - duplicate prompt names should fail explicitly at the store boundary

        How to use it:
        - pass a fully prepared `PromptRecord`
        - catch `PromptAlreadyExistsError` to map name conflicts at the API
          layer

        Example:
        - `created = await store.create(record)`
        """

        now = _utcnow()
        row = PromptRow(
            prompt_id=record.prompt_id,
            team_id=str(record.team_id),
            name=record.name,
            description=record.description,
            text=record.text,
            created_by=record.created_by,
            version=record.version,
            import_count=record.import_count,
            session_count=record.session_count,
            score=record.score,
            avg_input_tokens=record.avg_input_tokens,
            avg_output_tokens=record.avg_output_tokens,
            created_at=record.created_at or now,
            updated_at=record.updated_at or now,
        )
        try:
            async with use_session(self._sessions, session) as s:
                s.add(row)
        except IntegrityError as exc:
            raise PromptAlreadyExistsError(record.name) from exc
        result = await self.get(record.prompt_id)
        assert result is not None
        return result

    async def get(
        self,
        prompt_id: str,
        session: AsyncSession | None = None,
    ) -> PromptRecord | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(PromptRow, prompt_id)
        if row is None:
            return None
        return _row_to_record(row)

    async def get_for_team(
        self,
        prompt_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> PromptRecord | None:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PromptRow).where(
                            PromptRow.prompt_id == prompt_id,
                            PromptRow.team_id == str(team_id),
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
        *,
        limit: int = 100,
        session: AsyncSession | None = None,
    ) -> list[PromptRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PromptRow)
                        .where(PromptRow.team_id == str(team_id))
                        .order_by(PromptRow.updated_at.desc(), PromptRow.name.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [_row_to_record(row) for row in rows]

    async def update(
        self,
        prompt_id: str,
        team_id: TeamId,
        *,
        name: str,
        description: str | None,
        text: str,
        session: AsyncSession | None = None,
    ) -> PromptRecord | None:
        """
        Replace one team-scoped prompt-library record.

        Why this function exists:
        - the prompt library starts with one intentionally simple mutable-record
          model instead of per-field patch semantics or version graphs

        How to use it:
        - pass the full replacement values for the prompt
        - returns `None` when the prompt does not belong to `team_id`
        - catches duplicate `(team_id, name)` conflicts as
          `PromptAlreadyExistsError`

        Example:
        - `updated = await store.update(prompt_id, team_id, name="Ops", description=None, text="...")`
        """

        try:
            async with use_session(self._sessions, session) as s:
                result: CursorResult = await s.execute(  # type: ignore[assignment]
                    update(PromptRow)
                    .where(
                        PromptRow.prompt_id == prompt_id,
                        PromptRow.team_id == str(team_id),
                    )
                    .values(
                        name=name,
                        description=description,
                        text=text,
                        version=PromptRow.version + 1,
                        updated_at=_utcnow(),
                    )
                )
                if result.rowcount == 0:
                    return None
        except IntegrityError as exc:
            raise PromptAlreadyExistsError(name) from exc
        return await self.get(prompt_id, session)

    async def delete(
        self,
        prompt_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> bool:
        """Delete one prompt scoped to team_id. Returns True if a row was removed."""

        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(PromptRow).where(
                    PromptRow.prompt_id == prompt_id,
                    PromptRow.team_id == str(team_id),
                )
            )
        return result.rowcount > 0

    async def increment_import_count(
        self,
        prompt_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> None:
        """Atomically increment import_count when this prompt is imported into an agent."""

        async with use_session(self._sessions, session) as s:
            await s.execute(
                update(PromptRow)
                .where(
                    PromptRow.prompt_id == prompt_id,
                    PromptRow.team_id == str(team_id),
                )
                .values(import_count=PromptRow.import_count + 1)
            )

    async def increment_session_count(
        self,
        prompt_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> None:
        """Atomically increment session_count when this prompt is selected as chat context."""

        async with use_session(self._sessions, session) as s:
            await s.execute(
                update(PromptRow)
                .where(
                    PromptRow.prompt_id == prompt_id,
                    PromptRow.team_id == str(team_id),
                )
                .values(session_count=PromptRow.session_count + 1)
            )

    async def update_score(
        self,
        prompt_id: str,
        team_id: TeamId,
        score: float,
        session: AsyncSession | None = None,
    ) -> PromptRecord | None:
        """Set the explicit quality score (0.0–5.0) for one team-scoped prompt."""

        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(PromptRow)
                .where(
                    PromptRow.prompt_id == prompt_id,
                    PromptRow.team_id == str(team_id),
                )
                .values(score=score)
            )
            if result.rowcount == 0:
                return None
        return await self.get(prompt_id, session)

    async def list_context_prompts(
        self,
        personal_team_id: TeamId,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> list[ContextPromptRecord]:
        """Return the union of personal + team prompts ordered by session_count DESC for the context picker."""

        personal_str = str(personal_team_id)
        team_str = str(team_id)

        personal_q = select(
            PromptRow.prompt_id,
            PromptRow.name,
            PromptRow.description,
            literal("personal").label("scope"),
            PromptRow.version,
            PromptRow.session_count,
            PromptRow.score,
        ).where(PromptRow.team_id == personal_str)

        team_q = select(
            PromptRow.prompt_id,
            PromptRow.name,
            PromptRow.description,
            literal("team").label("scope"),
            PromptRow.version,
            PromptRow.session_count,
            PromptRow.score,
        ).where(PromptRow.team_id == team_str)

        if personal_str == team_str:
            combined = personal_q
        else:
            combined = union_all(personal_q, team_q)

        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(combined)).all()

        results = [
            ContextPromptRecord(
                prompt_id=row[0],
                name=row[1],
                description=row[2],
                scope=row[3],
                version=row[4],
                session_count=row[5],
                score=row[6],
            )
            for row in rows
        ]
        results.sort(key=lambda r: (-r.session_count, r.name))
        return results
