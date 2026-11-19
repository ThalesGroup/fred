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

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    TraceAdmissionRequest,
    TraceAvailability,
    TraceFinalization,
    TraceOutcome,
)
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import aliased, load_only

from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceCatalog,
    ConversationTraceDetail,
    ConversationTraceSummary,
    ConversationTraceTurn,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceSettingsRow,
    ConversationTraceTurnRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow

_SETTINGS_ID = 1


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _availability(row: ConversationTraceTurnRow) -> TraceAvailability:
    return (
        TraceAvailability.PARTIAL
        if row.completed_at is None or row.outcome == TraceOutcome.UNKNOWN
        else TraceAvailability.METADATA_ONLY
    )


class ConversationTraceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)
        self._insert = (
            pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
        )

    async def enabled(self) -> bool:
        async with use_session(self._sessions) as session:
            row = await session.get(ConversationTraceSettingsRow, _SETTINGS_ID)
            return row.enabled if row is not None else False

    async def set_enabled(self, enabled: bool) -> None:
        statement = self._insert(ConversationTraceSettingsRow).values(
            id=_SETTINGS_ID, enabled=enabled
        )
        async with use_session(self._sessions) as session:
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"], set_={"enabled": enabled}
                )
            )

    async def admit(
        self, runtime_id: str, request: TraceAdmissionRequest
    ) -> str | None:
        async with use_session(self._sessions) as session:
            settings = await session.get(ConversationTraceSettingsRow, _SETTINGS_ID)
            if settings is None or not settings.enabled:
                return None
            agent_name = await session.scalar(
                select(AgentInstanceRow.display_name)
                .select_from(SessionMetadataRow)
                .join(
                    AgentInstanceRow,
                    and_(
                        AgentInstanceRow.agent_instance_id
                        == SessionMetadataRow.agent_instance_id,
                        AgentInstanceRow.team_id == SessionMetadataRow.team_id,
                    ),
                )
                .where(
                    SessionMetadataRow.session_id == request.session_id,
                    SessionMetadataRow.user_id == request.user_id,
                    SessionMetadataRow.deleted_at.is_(None),
                    AgentInstanceRow.agent_instance_id == request.agent_instance_id,
                    AgentInstanceRow.source_runtime_id == runtime_id,
                )
                .with_for_update(of=SessionMetadataRow)
            )
            if agent_name is None:
                return None
            existing_id = await session.scalar(
                select(ConversationTraceTurnRow.capture_id).where(
                    ConversationTraceTurnRow.session_id == request.session_id,
                    ConversationTraceTurnRow.exchange_id == request.exchange_id,
                )
            )
            if existing_id is not None:
                return existing_id
            capture_id = str(uuid4())
            session.add(
                ConversationTraceTurnRow(
                    capture_id=capture_id,
                    session_id=request.session_id,
                    exchange_id=request.exchange_id,
                    runtime_id=runtime_id,
                    agent_display_name=agent_name,
                    history_rank=request.history_rank,
                )
            )
            return capture_id

    async def finalize(
        self, runtime_id: str, capture_id: str, result: TraceFinalization
    ) -> None:
        async with use_session(self._sessions) as session:
            row = await session.scalar(
                select(ConversationTraceTurnRow)
                .where(
                    ConversationTraceTurnRow.capture_id == capture_id,
                    ConversationTraceTurnRow.runtime_id == runtime_id,
                )
                .with_for_update()
            )
            if row is None or row.outcome in (
                TraceOutcome.COMPLETED,
                TraceOutcome.FAILED,
            ):
                return
            if result.discarded:
                if row.completed_at is None:
                    await session.delete(row)
                return
            row.completed_at = utcnow()
            row.outcome = result.outcome.value
            row.turn_number = row.turn_number or result.turn_number
            row.duration_ms = min(
                (row.duration_ms or 0) + result.duration_ms, 2**31 - 1
            )
            row.trace_id = row.trace_id or result.trace_id
            row.span_id = row.span_id or result.span_id
            row.call_ids = list(dict.fromkeys([*row.call_ids, *result.call_ids]))[
                :MAX_TRACE_CALL_IDS
            ]

    async def list_conversations(
        self,
        *,
        failed_only: bool,
        limit: int,
        before: tuple[datetime, str] | None,
    ) -> ConversationTraceCatalog:
        turn = ConversationTraceTurnRow
        newer = aliased(turn)
        superseded = select(newer.capture_id).where(
            newer.session_id == turn.session_id,
            or_(
                newer.history_rank > turn.history_rank,
                and_(
                    newer.history_rank == turn.history_rank,
                    newer.capture_id > turn.capture_id,
                ),
            ),
        )
        if failed_only:
            superseded = superseded.where(newer.outcome == TraceOutcome.FAILED.value)
        query = (
            select(turn, SessionMetadataRow.team_id)
            .join(SessionMetadataRow, SessionMetadataRow.session_id == turn.session_id)
            .options(
                load_only(
                    turn.session_id,
                    turn.agent_display_name,
                    turn.started_at,
                    turn.outcome,
                    turn.completed_at,
                )
            )
            .where(SessionMetadataRow.deleted_at.is_(None), ~superseded.exists())
            .order_by(turn.started_at.desc(), turn.capture_id.desc())
            .limit(limit + 1)
        )
        if failed_only:
            query = query.where(turn.outcome == TraceOutcome.FAILED.value)
        if before is not None:
            date, capture_id = before
            query = query.where(
                or_(
                    turn.started_at < date,
                    and_(turn.started_at == date, turn.capture_id < capture_id),
                )
            )
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
        last = rows[limit - 1][0] if len(rows) > limit else None
        return ConversationTraceCatalog(
            conversations=[
                ConversationTraceSummary(
                    session_id=row.session_id,
                    agent_display_name=row.agent_display_name,
                    team_id=team_id,
                    latest_started_at=_utc(row.started_at),
                    outcome=TraceOutcome(row.outcome),
                    availability=_availability(row),
                )
                for row, team_id in rows[:limit]
            ],
            next_cursor=f"{_utc(last.started_at).isoformat()}|{last.capture_id}"
            if last
            else None,
        )

    async def get_conversation(
        self,
        session_id: str,
        *,
        limit: int,
        after: tuple[int, str] | None,
    ) -> ConversationTraceDetail | None:
        turn = ConversationTraceTurnRow
        query = (
            select(turn, SessionMetadataRow.team_id)
            .join(SessionMetadataRow, SessionMetadataRow.session_id == turn.session_id)
            .where(
                turn.session_id == session_id, SessionMetadataRow.deleted_at.is_(None)
            )
            .order_by(turn.history_rank, turn.capture_id)
            .limit(limit + 1)
        )
        if after is not None:
            rank, capture_id = after
            query = query.where(
                or_(
                    turn.history_rank > rank,
                    and_(turn.history_rank == rank, turn.capture_id > capture_id),
                )
            )
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
        if not rows:
            return None
        first, team_id = rows[0]
        last = rows[limit - 1][0] if len(rows) > limit else None
        return ConversationTraceDetail(
            session_id=session_id,
            agent_display_name=first.agent_display_name,
            team_id=team_id,
            turns=[
                ConversationTraceTurn(
                    exchange_id=row.exchange_id,
                    turn_number=row.turn_number,
                    started_at=_utc(row.started_at),
                    duration_ms=row.duration_ms,
                    outcome=TraceOutcome(row.outcome),
                    availability=_availability(row),
                    call_ids=row.call_ids,
                    trace_id=row.trace_id,
                    span_id=row.span_id,
                )
                for row, _ in rows[:limit]
            ],
            next_cursor=f"{last.history_rank}|{last.capture_id}" if last else None,
        )
