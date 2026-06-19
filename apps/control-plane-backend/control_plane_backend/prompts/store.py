from __future__ import annotations

from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, literal, select, union_all, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.prompt_models import DefaultPromptUsageRow, PromptRow


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
        category: str | None = None,
        emoji: str | None = None,
        tags: list[str] | None = None,
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
        self.category = category
        self.emoji = emoji
        self.tags = tags or []
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
        category: str | None,
        version: int,
        session_count: int,
        score: float | None,
    ) -> None:
        self.prompt_id = prompt_id
        self.name = name
        self.description = description
        self.scope = scope
        self.category = category
        self.version = version
        self.session_count = session_count
        self.score = score


def _row_to_record(row: PromptRow) -> PromptRecord:
    return PromptRecord(
        prompt_id=row.prompt_id,
        team_id=TeamId(row.team_id),
        name=row.name,
        description=row.description,
        category=row.category,
        emoji=row.emoji,
        tags=row.tags or [],
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
            category=record.category,
            emoji=record.emoji,
            tags=record.tags,
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
        category: str | None,
        emoji: str | None,
        tags: list[str],
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
                        category=category,
                        emoji=emoji,
                        tags=tags,
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

    async def increment_default_usage(
        self,
        category: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> None:
        """Increment the session_count for one platform-default prompt category.

        Default prompts are never stored in PromptRow, so their usage is tracked
        in the separate default_prompt_usage table keyed by (team_id, category).
        The row is created on first use and incremented on each subsequent call.
        """

        async with use_session(self._sessions, session) as s:
            stmt = (
                sqlite_insert(DefaultPromptUsageRow)
                .values(team_id=str(team_id), category=category, session_count=1)
                .on_conflict_do_update(
                    index_elements=["team_id", "category"],
                    set_={
                        "session_count": DefaultPromptUsageRow.__table__.c.session_count
                        + 1
                    },
                )
            )
            await s.execute(stmt)

    async def get_default_usage(
        self,
        team_id: TeamId,
        categories: list[str],
        session: AsyncSession | None = None,
    ) -> dict[str, int]:
        """Return {category: session_count} for the given team and category list.

        Missing rows (never used) are absent from the result; callers should
        default to 0 for any category not present in the returned dict.
        """

        if not categories:
            return {}
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(
                        DefaultPromptUsageRow.category,
                        DefaultPromptUsageRow.session_count,
                    ).where(
                        DefaultPromptUsageRow.team_id == str(team_id),
                        DefaultPromptUsageRow.category.in_(categories),
                    )
                )
            ).all()
        return {row[0]: row[1] for row in rows}

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
            PromptRow.category,
        ).where(PromptRow.team_id == personal_str)

        team_q = select(
            PromptRow.prompt_id,
            PromptRow.name,
            PromptRow.description,
            literal("team").label("scope"),
            PromptRow.version,
            PromptRow.session_count,
            PromptRow.score,
            PromptRow.category,
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
                category=row[7],
            )
            for row in rows
        ]
        results.sort(key=lambda r: (-r.session_count, r.name))
        return results
