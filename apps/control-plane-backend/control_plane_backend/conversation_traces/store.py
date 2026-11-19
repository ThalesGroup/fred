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

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    TRACE_MAX_HTTP_ATTEMPTS,
    TRACE_MAX_MODEL_CALLS,
    TRACE_MAX_SSE_SEGMENTS,
    TraceAdmission,
    TraceAdmissionRequest,
    TraceAvailability,
    TraceFinalization,
    TraceHistoryBoundary,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceModelIndex,
    TraceModelOrigin,
    TraceOutcome,
    TraceSseAvailability,
    TraceSseSegment,
)
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import aliased, defer

from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceCatalog,
    ConversationTraceDetail,
    ConversationTraceSummary,
    ConversationTraceTurn,
    TraceConsentGrant,
    TraceContentAccess,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
    ConversationTraceSettingsRow,
    ConversationTraceTurnRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow

_SETTINGS_ID = 1


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _availability(
    completed_at: datetime | None, outcome: str, http: str | None = None
) -> TraceAvailability:
    if http is not None:
        return TraceAvailability(http)
    return (
        TraceAvailability.PARTIAL
        if completed_at is None or outcome == TraceOutcome.UNKNOWN
        else TraceAvailability.METADATA_ONLY
    )


def _consent(row: ConversationTraceConsentRow) -> TraceConsentGrant:
    return TraceConsentGrant(
        grant_id=row.grant_id,
        cutoff=TraceHistoryBoundary(
            exchange_id=row.exchange_id,
            first_rank=row.first_rank,
            last_rank=row.last_rank,
            turn_number=row.turn_number,
            started_at=_utc(row.started_at),
        ),
    )


def _consent_version(row: ConversationTraceConsentRow | None) -> str | None:
    if row is None:
        return None
    return f"{row.grant_id}:revoked" if row.revoked_at is not None else row.grant_id


def _sse_refs(segments: list[dict[str, object]]) -> set[str]:
    return {
        ref
        for item in segments
        if isinstance(lane := item.get("outgoing"), dict)
        and isinstance(ref := lane.get("ref"), str)
    }


@dataclass(frozen=True)
class TraceConversationReference:
    session_id: str
    team_id: str
    owner_id: str
    runtime_id: str | None
    agent_display_name: str
    has_capture: bool
    consent: TraceConsentGrant | None
    consent_version: str | None

    @property
    def visible(self) -> bool:
        return self.has_capture or self.consent is not None


class TraceSessionNotFound(Exception):
    pass


class TraceConsentDoesNotExtend(Exception):
    pass


class TraceConsentChanged(Exception):
    pass


class ConversationTraceStore:
    def __init__(self, engine: AsyncEngine, *, local_development: bool = False) -> None:
        self._sessions = make_session_factory(engine)
        self.local_development = local_development
        self._insert = (
            pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
        )

    async def enabled(self) -> bool:
        async with use_session(self._sessions) as session:
            row = await session.get(ConversationTraceSettingsRow, _SETTINGS_ID)
            return row.enabled if row is not None else self.local_development

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
    ) -> TraceAdmission | None:
        async with use_session(self._sessions) as session:
            settings = await session.get(ConversationTraceSettingsRow, _SETTINGS_ID)
            if not (
                settings.enabled if settings is not None else self.local_development
            ):
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
                    SessionMetadataRow.trace_erasing.is_(False),
                    AgentInstanceRow.agent_instance_id == request.agent_instance_id,
                    AgentInstanceRow.source_runtime_id == runtime_id,
                )
                .with_for_update(of=SessionMetadataRow)
            )
            if agent_name is None:
                return None
            existing = (
                await session.execute(
                    select(
                        ConversationTraceTurnRow.capture_id,
                        ConversationTraceTurnRow.started_at,
                    ).where(
                        ConversationTraceTurnRow.session_id == request.session_id,
                        ConversationTraceTurnRow.exchange_id == request.exchange_id,
                    )
                )
            ).one_or_none()
            if existing is not None:
                offset = int(
                    (utcnow() - _utc(existing.started_at)).total_seconds() * 1000
                )
                return TraceAdmission(
                    capture_id=existing.capture_id,
                    stream_offset_ms=max(0, min(offset, 2**31 - 1)),
                )
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
            return TraceAdmission(capture_id=capture_id)

    async def can_write(self, runtime_id: str, capture_id: str) -> bool:
        row = ConversationTraceTurnRow
        owner = SessionMetadataRow
        async with use_session(self._sessions) as session:
            return bool(
                await session.scalar(
                    select(row.capture_id)
                    .join(owner, owner.session_id == row.session_id)
                    .where(
                        row.capture_id == capture_id,
                        row.runtime_id == runtime_id,
                        owner.deleted_at.is_(None),
                        owner.trace_erasing.is_(False),
                    )
                )
            )

    async def finalize(
        self, runtime_id: str, capture_id: str, result: TraceFinalization
    ) -> bool:
        async with use_session(self._sessions) as session:
            owner = SessionMetadataRow
            turn = ConversationTraceTurnRow
            permitted = await session.scalar(
                select(owner.session_id)
                .join(turn, turn.session_id == owner.session_id)
                .where(
                    turn.capture_id == capture_id,
                    turn.runtime_id == runtime_id,
                    owner.deleted_at.is_(None),
                    owner.trace_erasing.is_(False),
                )
                .with_for_update(of=owner)
            )
            if permitted is None:
                return False
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
                # A network retry for the same accepted refs must stay idempotent.
                accepted = (
                    {a["ref"] for a in (row.http_attempts or [])} if row else set()
                )
                accepted_sse = _sse_refs(row.sse_segments or []) if row else set()
                accepted_models = (
                    {item["ref"] for item in row.model_calls or []} if row else set()
                )
                return (
                    all(item.ref in accepted for item in result.http_attempts)
                    and (result.sse is None or result.sse.outgoing.ref in accepted_sse)
                    and all(item.ref in accepted_models for item in result.model_calls)
                )
            if result.discarded:
                if row.completed_at is None:
                    await session.delete(row)
                return True
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

            previous = row.http_attempts or []
            already = {item["ref"] for item in previous}
            incoming = [
                item for item in result.http_attempts if item.ref not in already
            ]
            combined = [*previous, *(item.model_dump(mode="json") for item in incoming)]
            sse_segments = row.sse_segments or []
            if result.sse is not None and result.sse.outgoing.ref not in _sse_refs(
                sse_segments
            ):
                sse_segments = [*sse_segments, result.sse.model_dump(mode="json")]
            model_calls = row.model_calls or []
            model_refs = {item["ref"] for item in model_calls}
            new_models = [
                item for item in result.model_calls if item.ref not in model_refs
            ]
            model_calls = [
                *model_calls,
                *(item.model_dump(mode="json") for item in new_models),
            ]
            if (
                len(combined) > TRACE_MAX_HTTP_ATTEMPTS
                or len(sse_segments) > TRACE_MAX_SSE_SEGMENTS
                or len(model_calls) > TRACE_MAX_MODEL_CALLS
            ):
                row.http_availability = TraceAvailability.PARTIAL
                return False
            row.http_attempts = combined or None
            row.sse_segments = sse_segments or None
            row.model_calls = model_calls or None
            if (
                result.http_incomplete
                or row.http_availability == TraceAvailability.PARTIAL
                or any(
                    item.completeness != TraceHttpCompleteness.COMPLETE
                    for item in [*incoming, *new_models]
                )
                or (
                    result.sse is not None
                    and any(
                        lane.availability == TraceSseAvailability.PARTIAL
                        for lane in (result.sse.outgoing, *result.sse.provider)
                    )
                )
            ):
                row.http_availability = TraceAvailability.PARTIAL
            elif combined or sse_segments or model_calls:
                row.http_availability = TraceAvailability.CAPTURED
            return True

    async def http_attempts(
        self, session_id: str, exchange_id: str
    ) -> list[TraceHttpAttempt]:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            attempts = await session.scalar(
                select(turn.http_attempts).where(
                    turn.session_id == session_id, turn.exchange_id == exchange_id
                )
            )
        return [TraceHttpAttempt.model_validate(item) for item in attempts or []]

    async def sse_segments(
        self, session_id: str, exchange_id: str
    ) -> list[TraceSseSegment]:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            segments = await session.scalar(
                select(turn.sse_segments).where(
                    turn.session_id == session_id, turn.exchange_id == exchange_id
                )
            )
        return [TraceSseSegment.model_validate(item) for item in segments or []]

    async def model_calls(
        self, session_id: str, exchange_id: str
    ) -> list[TraceModelIndex]:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            items = await session.scalar(
                select(turn.model_calls).where(
                    turn.session_id == session_id,
                    turn.exchange_id == exchange_id,
                )
            )
        return [TraceModelIndex.model_validate(item) for item in items or []]

    async def model_origins(
        self,
        session_id: str,
        exchange_id: str,
        call: TraceModelIndex,
        *,
        cutoff_rank: int | None,
    ) -> list[TraceModelOrigin]:
        keys = set(call.related_tools)
        if not keys:
            return []
        turn = ConversationTraceTurnRow
        # Search the earliest retained captures first. A bounded miss leaves
        # the origin unknown rather than inferring it from a later request.
        query = (
            select(
                turn.exchange_id, turn.history_rank, turn.turn_number, turn.model_calls
            )
            .where(turn.session_id == session_id, turn.model_calls.is_not(None))
            .order_by(turn.history_rank, turn.exchange_id)
            .limit(64)
        )
        if call.observed_through_rank is not None:
            query = query.where(turn.history_rank <= call.observed_through_rank)
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
        origins = []
        for observed_exchange, rank, number, items in rows:
            for item in items or []:
                prior = TraceModelIndex.model_validate(item)
                if cutoff_rank is not None and (
                    prior.observed_through_rank is None
                    or prior.observed_through_rank > cutoff_rank
                ):
                    continue
                if keys.intersection(prior.observed_invalid_tools):
                    keys.difference_update(prior.observed_invalid_tools)
                    origins.append(
                        TraceModelOrigin(
                            exchange_id=observed_exchange,
                            history_rank=rank,
                            turn_number=number,
                            call_id=prior.call_id,
                        )
                    )
                if not keys or (
                    observed_exchange == exchange_id and prior.ref == call.ref
                ):
                    return origins
        return origins

    async def reference(self, session_id: str) -> TraceConversationReference | None:
        active = ConversationTraceConsentRow
        captured = ConversationTraceTurnRow
        metadata = SessionMetadataRow
        instance = AgentInstanceRow
        latest = (
            select(captured.runtime_id, captured.agent_display_name)
            .where(captured.session_id == session_id)
            .order_by(captured.history_rank.desc(), captured.capture_id.desc())
            .limit(1)
            .subquery()
        )
        last_grant = aliased(active)
        latest_grant_id = (
            select(last_grant.grant_id)
            .where(last_grant.session_id == session_id)
            .order_by(last_grant.granted_at.desc(), last_grant.grant_id.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = (
            select(
                metadata,
                active,
                func.coalesce(
                    metadata.source_runtime_id,
                    instance.source_runtime_id,
                    latest.c.runtime_id,
                ),
                func.coalesce(
                    instance.display_name,
                    metadata.agent_display_name,
                    latest.c.agent_display_name,
                ),
                latest.c.runtime_id.is_not(None),
            )
            .select_from(metadata)
            .outerjoin(
                instance,
                and_(
                    instance.agent_instance_id == metadata.agent_instance_id,
                    instance.team_id == metadata.team_id,
                ),
            )
            .outerjoin(active, active.grant_id == latest_grant_id)
            .outerjoin(latest, literal(True))
            .where(
                metadata.session_id == session_id,
                metadata.deleted_at.is_(None),
                metadata.trace_erasing.is_(False),
            )
        )
        async with use_session(self._sessions) as session:
            row = (await session.execute(query)).one_or_none()
        if row is None:
            return None
        owner, grant, runtime_id, display_name, has_capture = row
        if owner.user_id is None:
            return None
        return TraceConversationReference(
            session_id=session_id,
            team_id=owner.team_id,
            owner_id=owner.user_id,
            runtime_id=runtime_id,
            agent_display_name=display_name or "",
            has_capture=bool(has_capture),
            consent=_consent(grant)
            if grant is not None and grant.revoked_at is None
            else None,
            consent_version=_consent_version(grant),
        )

    async def capture_start_rank(self, session_id: str, exchange_id: str) -> int | None:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            return await session.scalar(
                select(turn.history_rank).where(
                    turn.session_id == session_id, turn.exchange_id == exchange_id
                )
            )

    async def set_consent(
        self,
        reference: TraceConversationReference,
        cutoff: TraceHistoryBoundary | None,
        *,
        expected_version: str | None = None,
    ) -> tuple[TraceConsentGrant | None, str | None]:
        metadata = SessionMetadataRow
        active = ConversationTraceConsentRow
        async with use_session(self._sessions) as session:
            owner = await session.scalar(
                select(metadata.session_id)
                .where(
                    metadata.session_id == reference.session_id,
                    metadata.user_id == reference.owner_id,
                    metadata.team_id == reference.team_id,
                    metadata.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if owner is None:
                raise TraceSessionNotFound()
            latest = await session.scalar(
                select(active)
                .where(active.session_id == owner)
                .order_by(active.granted_at.desc(), active.grant_id.desc())
                .limit(1)
            )
            previous = (
                latest if latest is not None and latest.revoked_at is None else None
            )
            if cutoff is None:
                if previous is None:
                    return None, None
                previous.revoked_at = utcnow()
                return _consent(previous), "revoked"
            current = _consent(previous) if previous is not None else None
            if current is not None and current.cutoff == cutoff:
                return current, None
            if expected_version != _consent_version(latest):
                raise TraceConsentChanged()
            if previous is not None:
                if cutoff.first_rank <= previous.first_rank:
                    raise TraceConsentDoesNotExtend()
                previous.revoked_at = utcnow()
                await session.flush()
            granted_at = utcnow()
            if latest is not None:
                # Keep grant order stable when the next request lands on a different pod.
                granted_at = max(
                    granted_at, _utc(latest.granted_at) + timedelta(microseconds=1)
                )
            row = active(
                grant_id=str(uuid4()),
                session_id=owner,
                actor_id=reference.owner_id,
                source="owner",
                granted_at=granted_at,
                **cutoff.model_dump(),
            )
            session.add(row)
            return _consent(row), "extended" if previous is not None else "granted"

    async def list_conversations(
        self,
        *,
        failed_only: bool,
        limit: int,
        before: tuple[datetime, str] | None,
    ) -> ConversationTraceCatalog:
        turn = ConversationTraceTurnRow
        newer = aliased(turn)
        metadata = SessionMetadataRow
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
        captured = (
            select(
                turn.session_id.label("session_id"),
                turn.agent_display_name.label("agent_display_name"),
                metadata.team_id.label("team_id"),
                turn.started_at.label("started_at"),
                turn.capture_id.label("entry_id"),
                turn.outcome.label("outcome"),
                turn.completed_at.label("completed_at"),
                turn.http_availability.label("http_availability"),
                literal(False).label("history_only"),
            )
            .select_from(turn)
            .join(metadata, metadata.session_id == turn.session_id)
            .where(
                metadata.deleted_at.is_(None),
                metadata.trace_erasing.is_(False),
                ~superseded.exists(),
            )
        )
        if failed_only:
            entries = captured.where(
                turn.outcome == TraceOutcome.FAILED.value
            ).subquery()
        else:
            grant = ConversationTraceConsentRow
            instance = AgentInstanceRow
            shared = (
                select(
                    grant.session_id,
                    func.coalesce(
                        instance.display_name, metadata.agent_display_name, ""
                    ),
                    metadata.team_id,
                    grant.started_at,
                    grant.grant_id,
                    literal(TraceOutcome.UNKNOWN.value),
                    grant.granted_at,
                    literal(None),
                    literal(True),
                )
                .select_from(grant)
                .join(metadata, metadata.session_id == grant.session_id)
                .outerjoin(
                    instance,
                    and_(
                        instance.agent_instance_id == metadata.agent_instance_id,
                        instance.team_id == metadata.team_id,
                    ),
                )
                .where(
                    grant.revoked_at.is_(None),
                    metadata.deleted_at.is_(None),
                    metadata.trace_erasing.is_(False),
                    ~select(turn.capture_id)
                    .where(turn.session_id == grant.session_id)
                    .exists(),
                )
            )
            entries = union_all(captured, shared).subquery()
        query = (
            select(entries)
            .order_by(entries.c.started_at.desc(), entries.c.entry_id.desc())
            .limit(limit + 1)
        )
        if before is not None:
            date, entry_id = before
            query = query.where(
                or_(
                    entries.c.started_at < date,
                    and_(entries.c.started_at == date, entries.c.entry_id < entry_id),
                )
            )
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
        last = rows[limit - 1] if len(rows) > limit else None
        return ConversationTraceCatalog(
            conversations=[
                ConversationTraceSummary(
                    session_id=row.session_id,
                    agent_display_name=row.agent_display_name,
                    team_id=row.team_id,
                    latest_started_at=_utc(row.started_at),
                    outcome=TraceOutcome(row.outcome),
                    availability=(
                        TraceAvailability.HISTORY_ONLY
                        if row.history_only
                        else _availability(
                            row.completed_at, row.outcome, row.http_availability
                        )
                    ),
                )
                for row in rows[:limit]
            ],
            next_cursor=f"{_utc(last.started_at).isoformat()}|{last.entry_id}"
            if last
            else None,
        )

    async def conversation_page(
        self,
        reference: TraceConversationReference,
        *,
        limit: int,
        after: tuple[int, str] | None,
        retained_turns: list[TraceHistoryBoundary],
        local_content_access: bool,
    ) -> ConversationTraceDetail:
        turn = ConversationTraceTurnRow
        query = (
            select(turn)
            .options(
                defer(turn.http_attempts),
                defer(turn.sse_segments),
                defer(turn.model_calls),
            )
            .where(turn.session_id == reference.session_id)
            .order_by(turn.history_rank, turn.exchange_id)
            .limit(limit + 1)
        )
        if after is not None:
            rank, exchange_id = after
            query = query.where(
                or_(
                    turn.history_rank > rank,
                    and_(turn.history_rank == rank, turn.exchange_id > exchange_id),
                )
            )
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).scalars().all()
        cutoff = reference.consent.cutoff if reference.consent is not None else None

        def access(rank: int, exchange_id: str) -> TraceContentAccess:
            if local_content_access:
                return TraceContentAccess.LOCAL
            if cutoff is not None and (rank, exchange_id) <= (
                cutoff.first_rank,
                cutoff.exchange_id,
            ):
                return TraceContentAccess.SHARED
            return TraceContentAccess.MASKED

        points = {
            item.exchange_id: (
                item.first_rank,
                ConversationTraceTurn(
                    exchange_id=item.exchange_id,
                    turn_number=item.turn_number,
                    started_at=_utc(item.started_at),
                    duration_ms=None,
                    outcome=TraceOutcome.UNKNOWN,
                    availability=TraceAvailability.HISTORY_ONLY,
                    call_ids=[],
                    trace_id=None,
                    span_id=None,
                    access=access(item.first_rank, item.exchange_id),
                ),
            )
            for item in retained_turns
        }
        for row in rows:
            start_rank = points.get(row.exchange_id, (row.history_rank, None))[0]
            points[row.exchange_id] = (
                start_rank,
                ConversationTraceTurn(
                    exchange_id=row.exchange_id,
                    turn_number=row.turn_number,
                    started_at=_utc(row.started_at),
                    duration_ms=row.duration_ms,
                    outcome=TraceOutcome(row.outcome),
                    availability=_availability(
                        row.completed_at, row.outcome, row.http_availability
                    ),
                    call_ids=row.call_ids,
                    trace_id=row.trace_id,
                    span_id=row.span_id,
                    access=access(start_rank, row.exchange_id),
                ),
            )
        ordered = sorted(
            points.values(), key=lambda item: (item[0], item[1].exchange_id)
        )
        last = ordered[limit - 1] if len(ordered) > limit else None
        return ConversationTraceDetail(
            session_id=reference.session_id,
            agent_display_name=reference.agent_display_name,
            team_id=reference.team_id,
            turns=[item for _, item in ordered[:limit]],
            next_cursor=f"{last[0]}|{last[1].exchange_id}" if last else None,
            consent_cutoff=cutoff,
            local_content_access=local_content_access,
        )
