from __future__ import annotations

from datetime import datetime, timezone

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.session_metadata_models import SessionMetadataRow


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class SessionMetadataAlreadyExistsError(Exception):
    """Raised when one session metadata row already exists for the session id."""


class SessionMetadataRecord:
    """In-memory projection of one DB session_metadata row."""

    def __init__(
        self,
        *,
        session_id: str,
        team_id: TeamId,
        agent_instance_id: str | None,
        user_id: str | None,
        title: str | None,
        context_prompt_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.session_id = session_id
        self.team_id = team_id
        self.agent_instance_id = agent_instance_id
        self.user_id = user_id
        self.title = title
        self.context_prompt_id = context_prompt_id
        self.created_at = created_at
        self.updated_at = updated_at


def _row_to_record(row: SessionMetadataRow) -> SessionMetadataRecord:
    return SessionMetadataRecord(
        session_id=row.session_id,
        team_id=TeamId(row.team_id),
        agent_instance_id=row.agent_instance_id,
        user_id=row.user_id,
        title=row.title,
        context_prompt_id=row.context_prompt_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SessionMetadataStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def create(
        self,
        record: SessionMetadataRecord,
        session: AsyncSession | None = None,
    ) -> SessionMetadataRecord:
        """
        Persist one new control-plane session metadata record.

        Why this function exists:
        - control-plane owns the lightweight sidebar/session metadata surface
          independently from runtime message history
        - duplicate `session_id` creation should fail explicitly instead of
          leaking raw SQL errors to higher layers

        How to use it:
        - pass a fully prepared `SessionMetadataRecord`
        - catch `SessionMetadataAlreadyExistsError` when callers want to map a
          duplicate create to a domain conflict

        Example:
        - `created = await store.create(record)`
        """

        now = _utcnow()
        row = SessionMetadataRow(
            session_id=record.session_id,
            team_id=str(record.team_id),
            agent_instance_id=record.agent_instance_id,
            user_id=record.user_id,
            title=record.title,
            created_at=record.created_at or now,
            updated_at=record.updated_at or now,
        )
        try:
            async with use_session(self._sessions, session) as s:
                s.add(row)
        except IntegrityError as exc:
            raise SessionMetadataAlreadyExistsError(record.session_id) from exc
        result = await self.get(record.session_id)
        assert result is not None
        return result

    async def get(
        self,
        session_id: str,
        session: AsyncSession | None = None,
    ) -> SessionMetadataRecord | None:
        async with use_session(self._sessions, session) as s:
            row = await s.get(SessionMetadataRow, session_id)
        if row is None:
            return None
        return _row_to_record(row)

    async def list_by_team(
        self,
        team_id: TeamId,
        user_id: str | None = None,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> list[SessionMetadataRecord]:
        async with use_session(self._sessions, session) as s:
            q = (
                select(SessionMetadataRow)
                .where(SessionMetadataRow.team_id == str(team_id))
            )
            if user_id is not None:
                q = q.where(SessionMetadataRow.user_id == user_id)
            rows = (
                (
                    await s.execute(
                        q.order_by(SessionMetadataRow.updated_at.desc()).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [_row_to_record(row) for row in rows]

    async def update_last_activity(
        self,
        session_id: str,
        team_id: TeamId,
        updated_at: datetime,
        session: AsyncSession | None = None,
    ) -> SessionMetadataRecord | None:
        """
        Refresh the sidebar ordering timestamp for one team-scoped session.

        Why this exists:
        - Runtime owns message history, while control-plane owns lightweight
          session metadata used by the sidebar.

        How to use it:
        - call after a managed turn completes with the frontend-observed
          activity timestamp.

        Example:
        - `await store.update_last_activity(session_id, team_id, updated_at)`
        """
        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(SessionMetadataRow)
                .where(
                    SessionMetadataRow.session_id == session_id,
                    SessionMetadataRow.team_id == str(team_id),
                )
                .values(updated_at=updated_at)
            )
            if result.rowcount == 0:
                return None
            row = (
                (
                    await s.execute(
                        select(SessionMetadataRow).where(
                            SessionMetadataRow.session_id == session_id,
                            SessionMetadataRow.team_id == str(team_id),
                        )
                    )
                )
                .scalars()
                .one()
            )
            return _row_to_record(row)

    async def update_metadata(
        self,
        session_id: str,
        team_id: TeamId,
        *,
        title: str | None = None,
        updated_at: datetime | None = None,
        context_prompt_id: str | None = None,
        clear_context_prompt: bool = False,
        session: AsyncSession | None = None,
    ) -> SessionMetadataRecord | None:
        """
        Update one or more control-plane metadata fields for a team-scoped session.

        Why this function exists:
        - ``update_last_activity`` only handles the ``updated_at`` freshness field;
          title edits need a single-roundtrip path that sets whichever fields are
          provided without touching the others.

        How to use it:
        - pass only the fields that should change; ``None`` means "leave as-is".
        - returns ``None`` when the session does not belong to ``team_id``.

        Example:
        - ``await store.update_metadata(session_id, team_id, title="My chat")``
        """
        values: dict[str, object] = {}
        if title is not None:
            values["title"] = title
        if updated_at is not None:
            values["updated_at"] = updated_at
        if context_prompt_id is not None:
            values["context_prompt_id"] = context_prompt_id
        elif clear_context_prompt:
            values["context_prompt_id"] = None
        if not values:
            return await self.get(session_id, session)
        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                update(SessionMetadataRow)
                .where(
                    SessionMetadataRow.session_id == session_id,
                    SessionMetadataRow.team_id == str(team_id),
                )
                .values(**values)
            )
            if result.rowcount == 0:
                return None
            row = (
                (
                    await s.execute(
                        select(SessionMetadataRow).where(
                            SessionMetadataRow.session_id == session_id,
                            SessionMetadataRow.team_id == str(team_id),
                        )
                    )
                )
                .scalars()
                .one()
            )
            return _row_to_record(row)

    async def delete(
        self,
        session_id: str,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> bool:
        """Delete one session scoped to team_id. Returns True if a row was removed."""
        async with use_session(self._sessions, session) as s:
            result: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(SessionMetadataRow).where(
                    SessionMetadataRow.session_id == session_id,
                    SessionMetadataRow.team_id == str(team_id),
                )
            )
        return result.rowcount > 0
