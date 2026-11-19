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

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fred_core.conversation_trace import (
    MAX_TRACE_CALL_IDS,
    TRACE_MAX_HTTP_ATTEMPTS,
    TRACE_MAX_MODEL_CALLS,
    TRACE_MAX_SSE_SEGMENTS,
    TRACE_MAX_TOOL_CALLS,
    TRACE_MAX_TURN_SEGMENTS,
    TraceAdmission,
    TraceAdmissionReconciliation,
    TraceAdmissionRequest,
    TraceAvailability,
    TraceCheckpointStatus,
    TraceFinalization,
    TraceFinalizationFacts,
    TraceHistoryBoundary,
    TraceHistoryIncident,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceModelIndex,
    TraceModelOrigin,
    TraceOutcome,
    TraceSseAvailability,
    TraceSseSegment,
    TraceStorageCleanup,
    TraceStorageCleanupResult,
    TraceStorageReservation,
    TraceStorageReservationState,
    TraceToolCall,
)
from fred_core.history.history_schema import TraceFailureCategory
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import Select, and_, func, literal, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import aliased, defer, load_only

from control_plane_backend.conversation_traces import capacity
from control_plane_backend.conversation_traces.catalog import (
    catalog_rows,
    cursor_revision,
    list_catalog_teams,
)
from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceCatalog,
    ConversationTraceDetail,
    ConversationTraceSettings,
    ConversationTraceSettingsUpdate,
    ConversationTraceSummary,
    ConversationTraceTurn,
    TraceCatalogFilters,
    TraceConsentGrant,
    TraceContentAccess,
    TraceReportedFailure,
    TraceTeamOption,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
    ConversationTraceIncidentRow,
    ConversationTraceSettingsRow,
    ConversationTraceTurnRow,
    TraceSegmentReceipt,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow

_TERMINAL_OUTCOMES = (TraceOutcome.COMPLETED, TraceOutcome.FAILED)
_ADMISSION_DB_SECONDS = 0.75


def _admission_owner(
    runtime_id: str, request: TraceAdmissionRequest
) -> Select[tuple[str]]:
    owner = SessionMetadataRow
    agent = AgentInstanceRow
    return (
        select(agent.display_name)
        .select_from(owner)
        .join(
            agent,
            and_(
                agent.agent_instance_id == owner.agent_instance_id,
                agent.team_id == owner.team_id,
            ),
        )
        .where(
            owner.session_id == request.session_id,
            owner.user_id == request.user_id,
            owner.agent_instance_id == request.agent_instance_id,
            owner.deleted_at.is_(None),
            owner.trace_erasing.is_(False),
            agent.source_runtime_id == runtime_id,
        )
        .with_for_update(of=owner)
    )


async def _lock_writable_owner(
    session: AsyncSession, runtime_id: str, capture_id: str
) -> str | None:
    owner = SessionMetadataRow
    turn = ConversationTraceTurnRow
    return await session.scalar(
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


def _segment_receipt(
    row: ConversationTraceTurnRow, segment_id: UUID | None
) -> TraceSegmentReceipt | None:
    if segment_id is None:
        return None
    return next(
        (
            receipt
            for receipt in row.segment_receipts or []
            if receipt["id"] == str(segment_id)
        ),
        None,
    )


def _replace_receipt(
    row: ConversationTraceTurnRow,
    receipt: TraceSegmentReceipt,
    *,
    facts: bool = True,
    published: bool,
    discarded: bool = False,
) -> None:
    row.segment_receipts = [
        TraceSegmentReceipt(
            id=entry["id"],
            offset_ms=entry["offset_ms"],
            facts=facts,
            published=published,
            discarded=discarded,
        )
        if entry is receipt
        else entry
        for entry in row.segment_receipts or []
    ]


def _record_segment_facts(
    row: ConversationTraceTurnRow,
    result: TraceFinalizationFacts,
    receipt: TraceSegmentReceipt | None,
) -> None:
    receipts = row.segment_receipts or []
    newer_facts = receipt is not None and any(
        entry["facts"] and not entry["discarded"]
        for entry in receipts[receipts.index(receipt) + 1 :]
    )
    if row.outcome not in _TERMINAL_OUTCOMES and (
        not newer_facts or result.outcome in _TERMINAL_OUTCOMES
    ):
        row.completed_at = utcnow()
        row.outcome = result.outcome.value
        if result.outcome == TraceOutcome.FAILED:
            row.failure_category = result.failure_category
            row.support_error_ref = result.support_error_ref
        start = receipt["offset_ms"] if receipt is not None else (row.duration_ms or 0)
        row.duration_ms = min(start + result.duration_ms, 2**31 - 1)
    if (
        result.checkpoint_status != TraceCheckpointStatus.UNKNOWN
        and row.checkpoint_status != TraceCheckpointStatus.PERSISTED
    ):
        row.checkpoint_status = result.checkpoint_status.value
    row.turn_number = row.turn_number or result.turn_number
    row.trace_id = row.trace_id or result.trace_id
    row.span_id = row.span_id or result.span_id
    row.call_ids = list(dict.fromkeys([*row.call_ids, *result.call_ids]))[
        :MAX_TRACE_CALL_IDS
    ]


async def _discard_segment(
    session: AsyncSession,
    row: ConversationTraceTurnRow,
    receipt: TraceSegmentReceipt | None,
) -> bool:
    if receipt is not None:
        if receipt["discarded"]:
            return True
        if receipt["facts"] or receipt["published"]:
            return False
        _replace_receipt(row, receipt, discarded=True, published=True)
    if row.completed_at is not None or not all(
        entry["discarded"] for entry in row.segment_receipts or []
    ):
        return True
    owner = SessionMetadataRow
    turn = ConversationTraceTurnRow
    session_id = row.session_id
    await session.delete(row)
    await session.flush()
    latest = select(func.max(turn.started_at)).where(turn.session_id == session_id)
    await session.execute(
        update(owner)
        .where(owner.session_id == session_id)
        .values(
            trace_last_captured_at=latest.scalar_subquery(),
            updated_at=owner.updated_at,
        )
    )
    return True


def _by_observed_rank(items: list[dict[str, object]]) -> list[dict[str, object]]:
    def rank(item: dict[str, object]) -> int:
        value = item.get("observed_through_rank")
        return value if isinstance(value, int) else 2**31

    return sorted(items, key=rank)


def _sse_start(segment: dict[str, object]) -> int:
    lane = segment.get("outgoing")
    provider = segment.get("provider")
    if lane is None and isinstance(provider, list) and provider:
        lane = provider[0]
    if isinstance(lane, dict) and isinstance(start := lane.get("started_ms"), int):
        return start
    return 2**31


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
    refs = set()
    for item in segments:
        lane = item.get("outgoing")
        provider = item.get("provider")
        if lane is None and isinstance(provider, list) and provider:
            lane = provider[0]
        if isinstance(lane, dict) and isinstance(ref := lane.get("ref"), str):
            refs.add(ref)
    return refs


def _stored_refs(result: TraceFinalization) -> set[str]:
    """Find every reference that finalization presents as physically readable."""
    refs = {
        item.ref
        for item in [*result.http_attempts, *result.model_calls, *result.tool_calls]
        if item.completeness != TraceHttpCompleteness.UNAVAILABLE
    }
    if result.sse is not None:
        refs.update(
            lane.ref
            for lane in result.sse.lanes
            if lane.headers_available
            or any(frame.offset is not None for frame in lane.frames)
        )
    return refs


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
    retained_after_delete: bool = False
    title: str | None = None
    title_revision: str | None = None
    title_authorized: bool = False

    @property
    def visible(self) -> bool:
        return self.has_capture or self.consent is not None


@dataclass(frozen=True)
class TraceExportState:
    session_id: str
    grant_id: str | None
    title_revision: str | None
    retained_after_delete: bool
    capture_id: str | None


@dataclass(frozen=True)
class TraceEvidenceIndex:
    http: list[TraceHttpAttempt]
    sse: list[TraceSseSegment]
    model: list[TraceModelIndex]
    tool: list[TraceToolCall]


class TraceSessionNotFound(Exception):
    pass


class TraceAdmissionUnavailable(Exception):
    """The bounded diagnostic transaction could not complete."""


class TraceConsentDoesNotExtend(Exception):
    pass


class TraceConsentChanged(Exception):
    pass


class ConversationTraceStore:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        local_development: bool = False,
        admission_slots: int = 7,
    ) -> None:
        self._sessions = make_session_factory(engine)
        self._admissions = asyncio.Semaphore(admission_slots)
        self.local_development = local_development

    @asynccontextmanager
    async def _admission_session(self) -> AsyncIterator[AsyncSession]:
        try:
            async with asyncio.timeout(_ADMISSION_DB_SECONDS), self._admissions:
                async with use_session(self._sessions) as session:
                    if session.get_bind().dialect.name == "postgresql":
                        await session.execute(text("SET LOCAL lock_timeout = '120ms'"))
                    yield session
        except TimeoutError as exc:
            raise TraceAdmissionUnavailable from exc
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "55P03":
                raise TraceAdmissionUnavailable from exc
            raise

    async def settings(self) -> ConversationTraceSettings:
        """Read live settings and byte usage without a write lock."""
        async with use_session(self._sessions) as session:
            return capacity.settings_view(
                await session.get(ConversationTraceSettingsRow, capacity.SETTINGS_ID),
                self.local_development,
                unmeasured=await capacity.has_unmeasured(session),
            )

    async def set_settings(
        self, update: ConversationTraceSettingsUpdate
    ) -> ConversationTraceSettings:
        """Apply the operator's changed admission and retention settings."""
        async with use_session(self._sessions) as session:
            row = await capacity.lock_settings(session, self.local_development)
            if update.enabled is not None:
                row.enabled = update.enabled
            if update.sampling_percent is not None:
                row.sampling_percent = update.sampling_percent
            if update.retention_days is not None:
                row.retention_days = update.retention_days
            if update.storage_cap_bytes is not None:
                row.storage_cap_bytes = update.storage_cap_bytes
                if row.reclaim_target > update.storage_cap_bytes:
                    row.reclaim_target = 0
            return capacity.settings_view(
                row,
                self.local_development,
                unmeasured=await capacity.has_unmeasured(session),
            )

    async def admit(
        self,
        runtime_id: str,
        request: TraceAdmissionRequest,
        *,
        segment_id: UUID | None = None,
    ) -> TraceAdmission | None:
        owner = SessionMetadataRow
        turn = ConversationTraceTurnRow
        async with self._admission_session() as session:
            settings = await capacity.lock_admission(
                session, request.session_id, self.local_development
            )
            if (
                settings is None
                or not settings.enabled
                or not capacity.sampled(request.session_id, settings.sampling_percent)
            ):
                return None
            agent_name = await session.scalar(_admission_owner(runtime_id, request))
            if agent_name is None:
                return None
            existing = await session.scalar(
                select(turn)
                .options(
                    load_only(
                        turn.capture_id,
                        turn.started_at,
                        turn.outcome,
                        turn.segment_receipts,
                    )
                )
                .where(
                    turn.session_id == request.session_id,
                    turn.exchange_id == request.exchange_id,
                    turn.runtime_id == runtime_id,
                )
            )
            if existing is not None:
                return self._admit_segment(existing, segment_id)
            capture_id = str(uuid4())
            started_at = utcnow()
            await session.execute(
                update(owner)
                .where(owner.session_id == request.session_id)
                .values(
                    trace_last_captured_at=started_at,
                    updated_at=owner.updated_at,
                )
            )
            row = ConversationTraceTurnRow(
                capture_id=capture_id,
                session_id=request.session_id,
                exchange_id=request.exchange_id,
                runtime_id=runtime_id,
                agent_display_name=agent_name,
                history_rank=request.history_rank,
                started_at=started_at,
                outcome=TraceOutcome.UNKNOWN,
            )
            session.add(row)
            return self._admit_segment(row, segment_id, offset_ms=0)

    async def reconcile_admission(
        self, runtime_id: str, segment_id: UUID, report: TraceAdmissionReconciliation
    ) -> bool:
        """Finish an existing receipt after a lost admission acknowledgement."""
        admission = report.admission
        owner = SessionMetadataRow
        turn = ConversationTraceTurnRow
        async with self._admission_session() as session:
            capture_id = await session.scalar(
                _admission_owner(runtime_id, admission)
                .join(turn, turn.session_id == owner.session_id)
                .with_only_columns(turn.capture_id)
                .where(
                    turn.exchange_id == admission.exchange_id,
                    turn.runtime_id == runtime_id,
                )
            )
            if capture_id is None:
                return False
            row = await session.get(turn, capture_id, with_for_update=True)
            if row is None:
                return False
            receipt = _segment_receipt(row, segment_id)
            if receipt is None:
                return False
            if report.facts.discarded:
                return await _discard_segment(session, row, receipt)
            if receipt["discarded"]:
                return False
            if receipt["facts"] or receipt["published"]:
                return receipt["facts"]
            _record_segment_facts(row, report.facts, receipt)
            _replace_receipt(row, receipt, published=True)
            row.http_availability = TraceAvailability.PARTIAL
            return True

    @staticmethod
    def _admit_segment(
        row: ConversationTraceTurnRow,
        segment_id: UUID | None,
        *,
        offset_ms: int | None = None,
    ) -> TraceAdmission | None:
        if receipt := _segment_receipt(row, segment_id):
            if receipt["discarded"]:
                return None
            return TraceAdmission(
                capture_id=row.capture_id,
                segment_id=segment_id,
                stream_offset_ms=receipt["offset_ms"],
            )
        if row.outcome in _TERMINAL_OUTCOMES:
            return None
        if offset_ms is None:
            offset = int((utcnow() - _utc(row.started_at)).total_seconds() * 1000)
            offset_ms = max(0, min(offset, 2**31 - 1))
        if segment_id is not None:
            receipts = row.segment_receipts or []
            if len(receipts) >= TRACE_MAX_TURN_SEGMENTS:
                return None
            row.segment_receipts = [
                *receipts,
                TraceSegmentReceipt(
                    id=str(segment_id),
                    offset_ms=offset_ms,
                    facts=False,
                    published=False,
                    discarded=False,
                ),
            ]
        return TraceAdmission(
            capture_id=row.capture_id, segment_id=segment_id, stream_offset_ms=offset_ms
        )

    async def delete_conversations(self, session_ids: list[str]) -> int:
        """Remove only the requested diagnostic records."""
        owner = SessionMetadataRow
        turn = ConversationTraceTurnRow
        grant = ConversationTraceConsentRow
        async with use_session(self._sessions) as session:
            await capacity.lock_settings(session, self.local_development)
            targets = tuple(
                await session.scalars(
                    select(owner.session_id)
                    .where(
                        owner.session_id.in_(session_ids),
                        ~owner.trace_erasing,
                        or_(
                            select(turn.capture_id)
                            .where(turn.session_id == owner.session_id)
                            .exists(),
                            select(grant.grant_id)
                            .where(
                                grant.session_id == owner.session_id,
                                grant.revoked_at.is_(None),
                            )
                            .exists(),
                        ),
                    )
                    .order_by(owner.session_id)
                    .with_for_update()
                )
            )
            if not targets:
                return 0
            return await capacity.retire_conversations(session, targets, utcnow())

    async def flush_captures(self) -> int:
        """Remove the current capture set atomically with respect to admission."""
        async with use_session(self._sessions) as session:
            await capacity.prepare_flush_fence(session, self.local_development)
        async with use_session(self._sessions) as session:
            settings = await capacity.lock_settings(
                session, self.local_development, flush=True
            )
            removed = await capacity.retire_conversations(
                session, select(ConversationTraceTurnRow.session_id), utcnow()
            )
            settings.reclaim_target = 0
            return removed

    async def reserve_storage(
        self,
        runtime_id: str,
        capture_id: str,
        request: TraceStorageReservation,
    ) -> TraceStorageReservationState:
        """Reserve bytes for one publication only while its admitted turn is writable."""
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            settings = await capacity.lock_settings(session, self.local_development)
            if await _lock_writable_owner(session, runtime_id, capture_id) is None:
                return TraceStorageReservationState.FENCED
            row = await session.scalar(
                select(turn)
                .options(
                    load_only(
                        turn.capture_id,
                        turn.session_id,
                        turn.outcome,
                        turn.segment_receipts,
                    )
                )
                .where(turn.capture_id == capture_id)
            )
            if row is None:
                return TraceStorageReservationState.FENCED
            if request.segment_id is None:
                if row.outcome in _TERMINAL_OUTCOMES:
                    return TraceStorageReservationState.FENCED
            else:
                receipt = _segment_receipt(row, request.segment_id)
                if (
                    request.publication_id != request.segment_id
                    or receipt is None
                    or receipt["published"]
                    or receipt["discarded"]
                ):
                    return TraceStorageReservationState.FENCED
            return await capacity.reserve(session, settings, runtime_id, row, request)

    async def next_storage_cleanup(
        self, runtime_id: str
    ) -> tuple[TraceStorageCleanup | None, tuple[int, int, int]]:
        """Run a bounded lifecycle tick and hand off work to the bucket owner."""
        async with use_session(self._sessions) as session:
            settings = await capacity.lock_settings(session, self.local_development)
            expired = await capacity.maintain(session, settings)
            return await capacity.claim_cleanup(session, runtime_id), expired

    async def finish_storage_cleanup(
        self,
        runtime_id: str,
        work_id: str,
        result: TraceStorageCleanupResult,
    ) -> None:
        """Acknowledge cleanup only through the runtime's current SQL lease."""
        async with use_session(self._sessions) as session:
            settings = await capacity.lock_settings(session, self.local_development)
            await capacity.complete_cleanup(
                session, settings, runtime_id, work_id, result
            )

    async def finalize(
        self, runtime_id: str, capture_id: str, result: TraceFinalization
    ) -> bool:
        """Publish evidence and settle its global byte reservation in one transaction."""
        async with use_session(self._sessions) as session:
            settings = None
            storage = None
            publication = result.storage
            refs = _stored_refs(result)
            if result.segment_id is not None and (
                (
                    publication is not None
                    and publication.publication_id != result.segment_id
                )
                or (result.evidence_pending and (publication is not None or refs))
            ):
                return False
            if publication is None and refs:
                return False
            if publication is not None or result.degradation is not None:
                settings = await capacity.lock_settings(session, self.local_development)
            if publication is not None:
                storage = await capacity.publication_row(
                    session, runtime_id, capture_id, publication
                )
                if storage is None:
                    return False
                if refs != publication.stored.keys():
                    capacity.abandon(storage)
                    return False
            permitted = await _lock_writable_owner(session, runtime_id, capture_id)
            if permitted is None:
                if storage is not None:
                    capacity.abandon(storage)
                return False
            if settings is not None and result.degradation is not None:
                capacity.degrade(settings, result.degradation)
            row = await session.scalar(
                select(ConversationTraceTurnRow)
                .where(
                    ConversationTraceTurnRow.capture_id == capture_id,
                    ConversationTraceTurnRow.runtime_id == runtime_id,
                )
                .with_for_update()
            )
            if row is None:
                if storage is not None:
                    capacity.abandon(storage)
                return False
            receipt = _segment_receipt(row, result.segment_id)
            if result.segment_id is not None and receipt is None:
                if storage is not None:
                    capacity.abandon(storage)
                return False
            if storage is not None and storage.due_at is None:
                # A paused segment can also be retried after its result committed.
                return True
            if receipt is None and row.outcome in _TERMINAL_OUTCOMES:
                # A network retry for the same accepted refs must stay idempotent.
                accepted = {a["ref"] for a in (row.http_attempts or [])}
                accepted_sse = _sse_refs(row.sse_segments or [])
                accepted_models = {item["ref"] for item in row.model_calls or []}
                accepted_tools = {item["ref"] for item in row.tool_calls or []}
                already_published = (
                    all(item.ref in accepted for item in result.http_attempts)
                    and (result.sse is None or result.sse.ref in accepted_sse)
                    and all(item.ref in accepted_models for item in result.model_calls)
                    and all(item.ref in accepted_tools for item in result.tool_calls)
                )
                if storage is not None:
                    capacity.abandon(storage)
                    return False
                return already_published
            if result.discarded:
                if storage is not None:
                    capacity.abandon(storage)
                return await _discard_segment(session, row, receipt)
            if receipt is not None and receipt["discarded"]:
                if storage is not None:
                    capacity.abandon(storage)
                return False
            if receipt is None or not receipt["facts"]:
                _record_segment_facts(row, result, receipt)
            row.turn_number = row.turn_number or result.turn_number
            if receipt is not None:
                if receipt["published"] or (
                    result.evidence_pending and receipt["facts"]
                ):
                    if storage is not None:
                        capacity.abandon(storage)
                    return storage is None
                _replace_receipt(
                    row, receipt, facts=True, published=not result.evidence_pending
                )
            if result.evidence_pending:
                return True

            previous = row.http_attempts or []
            already = {item["ref"] for item in previous}
            incoming = [
                item for item in result.http_attempts if item.ref not in already
            ]
            combined = [*previous, *(item.model_dump(mode="json") for item in incoming)]
            sse_segments = row.sse_segments or []
            if result.sse is not None and result.sse.ref not in _sse_refs(sse_segments):
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
            tool_calls = row.tool_calls or []
            tool_refs = {item["ref"] for item in tool_calls}
            new_tools = [
                item for item in result.tool_calls if item.ref not in tool_refs
            ]
            tool_calls = [
                *tool_calls,
                *(item.model_dump(mode="json") for item in new_tools),
            ]
            if (
                len(combined) > TRACE_MAX_HTTP_ATTEMPTS
                or len(sse_segments) > TRACE_MAX_SSE_SEGMENTS
                or len(model_calls) > TRACE_MAX_MODEL_CALLS
                or len(tool_calls) > TRACE_MAX_TOOL_CALLS
            ):
                row.http_availability = TraceAvailability.PARTIAL
                if storage is not None:
                    capacity.abandon(storage)
                return False
            row.http_attempts = _by_observed_rank(combined) or None
            row.sse_segments = (
                sorted(_by_observed_rank(sse_segments), key=_sse_start) or None
            )
            row.model_calls = _by_observed_rank(model_calls) or None
            row.tool_calls = _by_observed_rank(tool_calls) or None
            if (
                result.http_incomplete
                or row.http_availability == TraceAvailability.PARTIAL
                or any(
                    item.completeness != TraceHttpCompleteness.COMPLETE
                    for item in [*incoming, *new_models, *new_tools]
                )
                or (
                    result.sse is not None
                    and any(
                        lane.availability == TraceSseAvailability.PARTIAL
                        for lane in result.sse.lanes
                    )
                )
            ):
                row.http_availability = TraceAvailability.PARTIAL
            elif combined or sse_segments or model_calls or tool_calls:
                row.http_availability = TraceAvailability.CAPTURED
            elif row.http_availability is None:
                row.http_availability = TraceAvailability.METADATA_ONLY
            if storage is not None and settings is not None and publication is not None:
                capacity.settle(session, settings, storage, publication)
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

    async def tool_calls(
        self, session_id: str, exchange_id: str
    ) -> list[TraceToolCall]:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            items = await session.scalar(
                select(turn.tool_calls).where(
                    turn.session_id == session_id, turn.exchange_id == exchange_id
                )
            )
        return [TraceToolCall.model_validate(item) for item in items or []]

    async def export_state(
        self, session_ids: list[str], *, limit: int
    ) -> list[TraceExportState]:
        """Read visibility, grant and capture identities together for download fencing."""
        owner, grant, turn = (
            SessionMetadataRow,
            ConversationTraceConsentRow,
            ConversationTraceTurnRow,
        )
        query = (
            select(
                owner.session_id,
                grant.grant_id,
                owner.title_revision,
                owner.trace_retained_after_delete,
                turn.capture_id,
            )
            .select_from(owner)
            .outerjoin(
                grant,
                and_(grant.session_id == owner.session_id, grant.revoked_at.is_(None)),
            )
            .outerjoin(turn, turn.session_id == owner.session_id)
            .where(
                owner.session_id.in_(session_ids),
                owner.user_id.is_not(None),
                owner.trace_erasing.is_(False),
                or_(owner.deleted_at.is_(None), owner.trace_retained_after_delete),
                or_(turn.capture_id.is_not(None), grant.grant_id.is_not(None)),
            )
            .order_by(owner.session_id, turn.capture_id)
            .limit(limit)
        )
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
            return [TraceExportState(*row) for row in rows]

    async def export_evidence_indexes(
        self, session_id: str, exchange_ids: list[str]
    ) -> dict[str, TraceEvidenceIndex]:
        """Read the safe evidence indexes for a bounded export batch."""
        turn = ConversationTraceTurnRow
        query = select(
            turn.exchange_id,
            turn.http_attempts,
            turn.sse_segments,
            turn.model_calls,
            turn.tool_calls,
        ).where(turn.session_id == session_id, turn.exchange_id.in_(exchange_ids))
        async with use_session(self._sessions) as session:
            rows = (await session.execute(query)).all()
        return {
            exchange_id: TraceEvidenceIndex(
                [TraceHttpAttempt.model_validate(item) for item in http or []],
                [TraceSseSegment.model_validate(item) for item in sse or []],
                [TraceModelIndex.model_validate(item) for item in model or []],
                [TraceToolCall.model_validate(item) for item in tool or []],
            )
            for exchange_id, http, sse, model, tool in rows
        }

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
        current = aliased(turn)
        anchor = (
            select(current.history_rank)
            .where(current.session_id == session_id, current.exchange_id == exchange_id)
            .scalar_subquery()
        )
        query = (
            select(
                turn.exchange_id, turn.history_rank, turn.turn_number, turn.model_calls
            )
            .where(
                turn.session_id == session_id,
                turn.model_calls.is_not(None),
                or_(
                    turn.history_rank < anchor,
                    and_(turn.history_rank == anchor, turn.exchange_id <= exchange_id),
                ),
            )
            .order_by(turn.history_rank, turn.exchange_id)
            .limit(64)
        )
        rank_limits = [
            rank
            for rank in (cutoff_rank, call.observed_through_rank)
            if rank is not None
        ]
        rank_limit = min(rank_limits, default=None)
        if rank_limit is not None:
            query = query.where(turn.history_rank <= rank_limit)
        origins: list[TraceModelOrigin] = []
        page = query
        async with use_session(self._sessions) as session:
            while rows := (await session.execute(page)).all():
                for observed_exchange, rank, number, items in rows:
                    for item in items or []:
                        prior = TraceModelIndex.model_validate(item)
                        if (
                            (
                                cutoff_rank is None
                                or prior.observed_through_rank is not None
                            )
                            and (
                                rank_limit is None
                                or prior.observed_through_rank is None
                                or prior.observed_through_rank <= rank_limit
                            )
                            and keys.intersection(prior.observed_invalid_tools)
                        ):
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
                exchange, rank, _, _ = rows[-1]
                if exchange == exchange_id:
                    break
                page = query.where(
                    or_(
                        turn.history_rank > rank,
                        and_(turn.history_rank == rank, turn.exchange_id > exchange),
                    )
                )
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
                or_(
                    metadata.deleted_at.is_(None),
                    metadata.trace_retained_after_delete.is_(True),
                ),
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
            retained_after_delete=owner.trace_retained_after_delete,
            title=owner.title,
            title_revision=owner.title_revision,
            title_authorized=bool(
                grant is not None
                and grant.revoked_at is None
                and owner.title_revision is not None
                and grant.title_revision == owner.title_revision
            ),
        )

    async def capture_start_rank(self, session_id: str, exchange_id: str) -> int | None:
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            return await session.scalar(
                select(turn.history_rank).where(
                    turn.session_id == session_id, turn.exchange_id == exchange_id
                )
            )

    async def has_capture_through(
        self, session_id: str, cutoff: TraceHistoryBoundary
    ) -> bool:
        """Warn about retained raw evidence and any capture still being published."""
        turn = ConversationTraceTurnRow
        async with use_session(self._sessions) as session:
            return bool(
                await session.scalar(
                    select(turn.capture_id)
                    .where(
                        turn.session_id == session_id,
                        or_(
                            turn.completed_at.is_(None),
                            and_(
                                turn.segment_receipts.is_not(None),
                                turn.http_availability.is_(None),
                            ),
                            capacity.has_readable_artifacts(),
                        ),
                        or_(
                            turn.history_rank < cutoff.first_rank,
                            and_(
                                turn.history_rank == cutoff.first_rank,
                                turn.exchange_id <= cutoff.exchange_id,
                            ),
                        ),
                    )
                    .limit(1)
                )
            )

    async def set_consent(
        self,
        reference: TraceConversationReference,
        cutoff: TraceHistoryBoundary | None,
        *,
        expected_version: str | None = None,
        incident: TraceHistoryIncident | None = None,
        actor_id: str | None = None,
        source_note: str | None = None,
        title_covered: bool = False,
    ) -> tuple[TraceConsentGrant | None, str | None]:
        reporting = incident is not None
        metadata = SessionMetadataRow
        active = ConversationTraceConsentRow
        report = ConversationTraceIncidentRow
        async with use_session(self._sessions) as session:
            owner = await session.scalar(
                select(metadata)
                .where(
                    metadata.session_id == reference.session_id,
                    metadata.user_id == reference.owner_id,
                    metadata.team_id == reference.team_id,
                    metadata.deleted_at.is_(None),
                    metadata.trace_erasing.is_(False),
                )
                .with_for_update()
            )
            if owner is None:
                raise TraceSessionNotFound()
            session_id = owner.session_id
            latest = await session.scalar(
                select(active)
                .where(active.session_id == session_id)
                .order_by(active.granted_at.desc(), active.grant_id.desc())
                .limit(1)
            )
            previous = (
                latest if latest is not None and latest.revoked_at is None else None
            )
            if cutoff is None:
                if previous is None:
                    return None, None
                await capacity.revoke_conversation_grants(
                    session, (session_id,), utcnow()
                )
                return _consent(previous), "revoked"
            current = _consent(previous) if previous is not None else None
            already_reported = (
                incident is not None
                and previous is not None
                and await session.get(report, (session_id, incident.support_error_ref))
                is not None
            )
            if (
                current is not None
                and current.cutoff == cutoff
                and source_note is None
                and (incident is None or already_reported)
            ):
                return current, None
            if expected_version != _consent_version(latest):
                raise TraceConsentChanged()
            if already_reported and current is not None:
                return current, None
            if source_note is not None and previous is None:
                captured = ConversationTraceTurnRow
                if not await session.scalar(
                    select(captured.capture_id)
                    .where(captured.session_id == session_id)
                    .limit(1)
                ):
                    raise TraceSessionNotFound()
            if previous is not None and current is not None:
                at_same_exchange = cutoff.exchange_id == previous.exchange_id
                advancing = cutoff.first_rank > previous.first_rank or (
                    at_same_exchange
                    and cutoff.first_rank == previous.first_rank
                    and cutoff.last_rank > previous.last_rank
                )
                if cutoff != current.cutoff and not advancing:
                    if not reporting:
                        raise TraceConsentDoesNotExtend()
                    # Reporting an earlier failure does not narrow an active grant.
                    cutoff = current.cutoff
                previous.revoked_at = utcnow()
                await session.flush()
            if incident is not None:
                session.add(
                    report(
                        session_id=session_id,
                        support_error_ref=incident.support_error_ref,
                        failure_category=incident.failure_category,
                        **incident.cutoff.model_dump(),
                    )
                )
                await session.flush()
            latest_report = await session.scalar(
                select(report)
                .where(report.session_id == session_id)
                .order_by(
                    report.started_at.desc(),
                    report.last_rank.desc(),
                    report.support_error_ref.desc(),
                )
                .limit(1)
            )
            granted_at = utcnow()
            if latest is not None:
                # Keep grant order stable when the next request lands on a different pod.
                granted_at = max(
                    granted_at, _utc(latest.granted_at) + timedelta(microseconds=1)
                )
            row = active(
                grant_id=str(uuid4()),
                session_id=session_id,
                actor_id=actor_id or reference.owner_id,
                source="manual" if source_note is not None else "owner",
                source_note=source_note,
                title_revision=owner.title_revision
                if (
                    (title_covered and owner.title_revision == reference.title_revision)
                    or (
                        previous is not None
                        and previous.title_revision == owner.title_revision
                    )
                )
                else None,
                incident=self._legacy_incident(latest_report),
                diagnostic_at=latest_report.started_at
                if latest_report is not None
                else cutoff.started_at,
                granted_at=granted_at,
                **cutoff.model_dump(),
            )
            session.add(row)
            return _consent(row), (
                "recorded"
                if source_note is not None
                else "reported"
                if reporting
                else "extended"
                if previous is not None
                else "granted"
            )

    @staticmethod
    def _legacy_incident(
        report: ConversationTraceIncidentRow | None,
    ) -> dict[str, object] | None:
        if report is None:
            return None
        return TraceHistoryIncident(
            cutoff=TraceHistoryBoundary(
                exchange_id=report.exchange_id,
                first_rank=report.first_rank,
                last_rank=report.last_rank,
                turn_number=report.turn_number,
                started_at=_utc(report.started_at),
            ),
            support_error_ref=report.support_error_ref,
            failure_category=TraceFailureCategory(report.failure_category)
            if report.failure_category is not None
            else None,
        ).model_dump(mode="json")

    async def incident_reported(
        self, session_id: str, grant_id: str | None, support_error_ref: str
    ) -> bool:
        if grant_id is None:
            return False
        grant, report = ConversationTraceConsentRow, ConversationTraceIncidentRow
        async with use_session(self._sessions) as session:
            return bool(
                await session.scalar(
                    select(report.support_error_ref)
                    .join(grant, grant.session_id == report.session_id)
                    .where(
                        report.session_id == session_id,
                        report.support_error_ref == support_error_ref,
                        grant.grant_id == grant_id,
                        grant.revoked_at.is_(None),
                    )
                )
            )

    async def list_conversations(
        self,
        filters: TraceCatalogFilters,
        *,
        cursor: str | None = None,
        expected_revision: str | None = None,
        before: tuple[datetime, str] | None = None,
        local_content_access: bool = False,
    ) -> ConversationTraceCatalog:
        limit = filters.limit
        async with use_session(self._sessions) as session:
            rows = await catalog_rows(
                session,
                filters,
                postgres=session.get_bind().dialect.name == "postgresql",
                local_content_access=local_content_access,
                limit=limit,
                cursor=cursor,
                expected_revision=expected_revision,
                before=before,
            )
        last = rows[limit - 1] if len(rows) > limit else None
        return ConversationTraceCatalog(
            conversations=[
                ConversationTraceSummary(
                    session_id=row.session_id,
                    agent_display_name=row.display_name,
                    title=row.title,
                    user_id=row.user_id,
                    username=row.username,
                    team_id=row.team_id,
                    team_name=row.team_name,
                    access=TraceContentAccess(row.access),
                    latest_started_at=_utc(row.latest_started_at),
                    outcome=TraceOutcome(row.outcome),
                    failure_category=TraceFailureCategory(row.failure_category)
                    if row.failure_category is not None
                    else None,
                    support_error_ref=row.support_error_ref,
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
            next_cursor=f"v2|{cursor_revision(last._mapping, filters.sort)}|{last.session_id}"
            if last is not None
            else None,
        )

    async def list_teams(self) -> list[TraceTeamOption]:
        async with use_session(self._sessions) as session:
            return await list_catalog_teams(session)

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
                defer(turn.tool_calls),
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
            incidents = await self._incident_page(session, reference, after, limit)
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
                    retained_cutoff=item,
                ),
            )
            for item in retained_turns
        }
        for row in rows:
            retained = points.get(row.exchange_id)
            start_rank = retained[0] if retained is not None else row.history_rank
            points[row.exchange_id] = (
                start_rank,
                ConversationTraceTurn(
                    exchange_id=row.exchange_id,
                    turn_number=row.turn_number,
                    started_at=_utc(row.started_at),
                    duration_ms=row.duration_ms,
                    outcome=TraceOutcome(row.outcome),
                    checkpoint_status=TraceCheckpointStatus(
                        row.checkpoint_status or TraceCheckpointStatus.UNKNOWN
                    ),
                    failure_category=TraceFailureCategory(row.failure_category)
                    if row.failure_category is not None
                    else None,
                    support_error_ref=row.support_error_ref,
                    availability=_availability(
                        row.completed_at, row.outcome, row.http_availability
                    ),
                    call_ids=row.call_ids,
                    trace_id=row.trace_id,
                    span_id=row.span_id,
                    access=access(start_rank, row.exchange_id),
                    retained_cutoff=retained[1].retained_cutoff
                    if retained is not None
                    else None,
                ),
            )
        for incident in incidents:
            key = (incident.first_rank, incident.exchange_id)
            point = points.get(incident.exchange_id)
            if point is None:
                point = (
                    incident.first_rank,
                    ConversationTraceTurn(
                        exchange_id=incident.exchange_id,
                        turn_number=incident.turn_number,
                        started_at=_utc(incident.started_at),
                        duration_ms=None,
                        outcome=TraceOutcome.FAILED,
                        availability=TraceAvailability.HISTORY_ONLY,
                        call_ids=[],
                        trace_id=None,
                        span_id=None,
                        access=access(*key),
                    ),
                )
            item = point[1]
            failure = TraceReportedFailure(
                support_error_ref=incident.support_error_ref,
                failure_category=TraceFailureCategory(incident.failure_category)
                if incident.failure_category is not None
                else None,
            )
            if not item.reported_failures:
                item.outcome = TraceOutcome.FAILED
                item.support_error_ref = (
                    item.support_error_ref or failure.support_error_ref
                )
                item.failure_category = (
                    failure.failure_category or item.failure_category
                )
            item.reported_failures.append(failure)
            points[incident.exchange_id] = point
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
            consent_version=reference.consent_version,
            local_content_access=local_content_access,
            retained_after_delete=reference.retained_after_delete,
            title=reference.title
            if local_content_access or reference.title_authorized
            else None,
        )

    @staticmethod
    async def _incident_page(
        session: AsyncSession,
        reference: TraceConversationReference,
        after: tuple[int, str] | None,
        limit: int,
    ) -> list[ConversationTraceIncidentRow]:
        if reference.consent is None:
            return []
        report, grant = ConversationTraceIncidentRow, ConversationTraceConsentRow
        exchanges = select(report.exchange_id, report.first_rank).where(
            report.session_id == reference.session_id
        )
        if after is not None:
            rank, exchange_id = after
            exchanges = exchanges.where(
                or_(
                    report.first_rank > rank,
                    and_(report.first_rank == rank, report.exchange_id > exchange_id),
                )
            )
        page = (
            exchanges.distinct()
            .order_by(report.first_rank, report.exchange_id)
            .limit(limit + 1)
            .subquery()
        )
        return list(
            await session.scalars(
                select(report)
                .join(page, page.c.exchange_id == report.exchange_id)
                .join(grant, grant.session_id == report.session_id)
                .where(
                    report.session_id == reference.session_id,
                    grant.grant_id == reference.consent.grant_id,
                    grant.revoked_at.is_(None),
                )
                .order_by(
                    report.first_rank,
                    report.exchange_id,
                    report.last_rank.desc(),
                    report.support_error_ref,
                )
            )
        )
