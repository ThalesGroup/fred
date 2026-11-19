# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Shared trace byte accounting and retryable retention work."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from fred_core.conversation_trace import (
    TRACE_DEFAULT_RETENTION_DAYS,
    TRACE_DEFAULT_SAMPLING,
    TRACE_DEFAULT_STORAGE_BYTES,
    TraceDegradation,
    TraceStorageCleanup,
    TraceStorageCleanupResult,
    TraceStoragePublication,
    TraceStorageReservation,
    TraceStorageReservationState,
)
from sqlalchemy import Select, delete, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Exists

from control_plane_backend.conversation_traces.schemas import ConversationTraceSettings
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
    ConversationTraceIncidentRow,
    ConversationTraceSettingsRow,
    ConversationTraceStorageRow,
    ConversationTraceTurnRow,
)
from control_plane_backend.models.purge_queue_models import PurgeQueueRow
from control_plane_backend.models.session_metadata_models import SessionMetadataRow

SETTINGS_ID = 1
_BATCH_SIZE = 16
_CLEANUP_LEASE = timedelta(minutes=3)
# An abandoned write may leave a backend PUT in flight. Keep the reservation
# past the storage SDK's retry window before an unrelated replica removes it.
_ABANDONED_WRITE = timedelta(hours=3)
_UNCERTAIN_WRITE = timedelta(minutes=2)
_DEGRADED_WINDOW = timedelta(minutes=1)
_MAX_PUBLICATION_BYTES = 16 * 1024 * 1024

Settings = ConversationTraceSettingsRow
Storage = ConversationTraceStorageRow
Owner = SessionMetadataRow
Turn = ConversationTraceTurnRow
Grant = ConversationTraceConsentRow


class _State(StrEnum):
    RESERVED = "reserved"
    STORED = "stored"
    CLEANUP_RESERVED = "cleanup_reserved"
    CLEANUP_STORED = "cleanup_stored"
    MEASURE = "measure"
    CLEANUP_UNMEASURED = "cleanup_unmeasured"


class TraceFlushInProgress(Exception):
    """An eligible turn could not take the shared admission fence immediately."""


def as_utc(value: datetime) -> datetime:
    """Interpret dates returned from local SQLite with the same UTC clock as Postgres."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def sampled(session_id: str, percent: int) -> bool:
    """Apply a stable deployment-wide threshold to the canonical session ID."""
    if percent == 100:
        return True
    if percent == 0:
        return False
    bucket = int.from_bytes(sha256(session_id.encode()).digest()[:8])
    return bucket * 100 < percent * (1 << 64)


async def capture_eligible(
    session: AsyncSession, session_id: str, local_development: bool
) -> bool:
    """Read current policy without taking an admission or accounting lock."""
    policy = (
        await session.execute(
            select(Settings.enabled, Settings.sampling_percent).where(
                Settings.id == SETTINGS_ID
            )
        )
    ).one_or_none()
    if policy is None:
        return local_development
    return policy.enabled and sampled(session_id, policy.sampling_percent)


async def lock_settings(
    session: AsyncSession, local_development: bool, *, flush: bool = False
) -> Settings:
    """Serialize accounting and setting changes in the database."""
    if session.get_bind().dialect.name == "postgresql":
        lock = (
            select(Settings)
            .where(Settings.id == SETTINGS_ID)
            .with_for_update(key_share=not flush)
        )
        row = await session.scalar(lock)
        if row is None:
            await _insert_pg_settings(session, local_development)
            row = await session.scalar(lock)
    else:
        # SQLite ignores FOR UPDATE. Take its write lock before reading counters.
        await session.execute(
            sqlite_insert(Settings)
            .values(id=SETTINGS_ID, enabled=local_development)
            .on_conflict_do_nothing(index_elements=[Settings.id])
        )
        row = await session.get(Settings, SETTINGS_ID)
    assert row is not None
    return row


async def _insert_pg_settings(session: AsyncSession, local_development: bool) -> None:
    await session.execute(
        pg_insert(Settings)
        .values(id=SETTINGS_ID, enabled=local_development)
        .on_conflict_do_nothing(index_elements=[Settings.id])
    )


async def prepare_flush_fence(session: AsyncSession, local_development: bool) -> None:
    if session.get_bind().dialect.name == "postgresql" and not await session.scalar(
        select(Settings.id).where(Settings.id == SETTINGS_ID)
    ):
        await _insert_pg_settings(session, local_development)


async def lock_admission(
    session: AsyncSession,
    session_id: str,
    local_development: bool,
    *,
    resuming: bool = False,
) -> Settings | None:
    """Skip a held flush fence while allowing unrelated publishers."""
    if session.get_bind().dialect.name != "postgresql":
        if not resuming and not await capture_eligible(
            session, session_id, local_development
        ):
            return None
        return await lock_settings(session, local_development)
    lock = (
        select(Settings)
        .where(Settings.id == SETTINGS_ID)
        .with_for_update(read=True, key_share=True, skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if not resuming:
        lock = lock.where(Settings.enabled, Settings.sampling_percent > 0)
    settings = await session.scalar(lock)
    if (
        settings is None
        and resuming
        and await session.scalar(select(Settings.id).where(Settings.id == SETTINGS_ID))
    ):
        raise TraceFlushInProgress
    if settings is None and await capture_eligible(
        session, session_id, local_development
    ):
        # Only the uncommon flush or explicit first-use local path gets here.
        await prepare_flush_fence(session, local_development)
        settings = await session.scalar(lock)
        if settings is None and await capture_eligible(
            session, session_id, local_development
        ):
            raise TraceFlushInProgress
    return settings


def settings_view(
    row: Settings | None, local_development: bool, *, unmeasured: bool
) -> ConversationTraceSettings:
    """Present available bytes and a recent or ongoing shared degradation."""
    reason = None
    if row is not None:
        if (
            row.used_bytes + row.reserved_bytes > row.storage_cap_bytes
            or row.reclaim_target
        ):
            reason = TraceDegradation.CAPACITY
        elif (
            row.degradation_reason is not None
            and row.degraded_until is not None
            and as_utc(row.degraded_until) > utcnow()
        ):
            reason = TraceDegradation(row.degradation_reason)
    if unmeasured:
        reason = TraceDegradation.STORAGE
    return ConversationTraceSettings(
        enabled=row.enabled if row is not None else local_development,
        sampling_percent=row.sampling_percent
        if row is not None
        else TRACE_DEFAULT_SAMPLING,
        retention_days=row.retention_days
        if row is not None
        else TRACE_DEFAULT_RETENTION_DAYS,
        storage_cap_bytes=row.storage_cap_bytes
        if row is not None
        else TRACE_DEFAULT_STORAGE_BYTES,
        used_bytes=row.used_bytes if row is not None else 0,
        reserved_bytes=row.reserved_bytes if row is not None else 0,
        degraded=reason is not None,
        degradation_reason=reason,
    )


def degrade(settings: Settings, reason: TraceDegradation) -> None:
    """Keep brief pressure spikes visible across replicas and polling clients."""
    settings.degradation_reason = reason
    settings.degraded_until = utcnow() + _DEGRADED_WINDOW


async def has_unmeasured(session: AsyncSession) -> bool:
    """Avoid permitting more writes while pre-ledger stored bytes are unknown."""
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Storage.state.in_((_State.MEASURE, _State.CLEANUP_UNMEASURED))
                )
            )
        )
    )


def has_readable_artifacts() -> Exists:
    """Find retained bytes, including evidence still being measured after upgrade."""
    return exists().where(
        Storage.capture_id == Turn.capture_id,
        (Storage.state == _State.MEASURE)
        | ((Storage.state == _State.STORED) & (Storage.size_bytes > 0)),
    )


async def reserve(
    session: AsyncSession,
    settings: Settings,
    runtime_id: str,
    turn: Turn,
    request: TraceStorageReservation,
) -> TraceStorageReservationState:
    """Charge the upper bound before the background publisher can touch storage."""
    publication_id = str(request.publication_id)
    prior = await session.get(Storage, publication_id)
    if prior is not None:
        if (
            prior.runtime_id == runtime_id
            and prior.capture_id == turn.capture_id
            and prior.state == _State.RESERVED
            and prior.objects == request.objects
            and prior.due_at is not None
            and as_utc(prior.due_at) > utcnow()
        ):
            return TraceStorageReservationState.RESERVED
        return TraceStorageReservationState.FENCED
    size = sum(request.objects.values())
    if not 0 < size <= _MAX_PUBLICATION_BYTES or size > settings.storage_cap_bytes:
        degrade(settings, TraceDegradation.CAPACITY)
        return TraceStorageReservationState.CAPACITY
    if await has_unmeasured(session):
        degrade(settings, TraceDegradation.STORAGE)
        return TraceStorageReservationState.UNAVAILABLE
    available = (
        settings.storage_cap_bytes - settings.used_bytes - settings.reserved_bytes
    )
    if size > available:
        settings.reclaim_target = max(settings.reclaim_target, size)
        degrade(settings, TraceDegradation.CAPACITY)
        return TraceStorageReservationState.CAPACITY
    if available >= settings.reclaim_target:
        settings.reclaim_target = 0
    settings.reserved_bytes += size
    session.add(
        Storage(
            id=publication_id,
            runtime_id=runtime_id,
            session_id=turn.session_id,
            capture_id=turn.capture_id,
            objects=request.objects,
            size_bytes=size,
            state=_State.RESERVED,
            due_at=utcnow() + _ABANDONED_WRITE,
        )
    )
    return TraceStorageReservationState.RESERVED


async def publication_row(
    session: AsyncSession,
    runtime_id: str,
    capture_id: str,
    publication: TraceStoragePublication,
) -> Storage | None:
    """Validate that settlement refers to this runtime's own reserved or committed refs."""
    row = await session.get(Storage, str(publication.publication_id))
    if row is None or row.runtime_id != runtime_id or row.capture_id != capture_id:
        return None
    if row.state == _State.STORED:
        return row if row.objects == publication.stored else None
    if (
        row.state != _State.RESERVED
        or row.due_at is None
        or as_utc(row.due_at) <= utcnow()
        or set(publication.uncertain) & publication.stored.keys()
        or any(ref not in row.objects for ref in publication.uncertain)
        or any(
            not 0 < size <= row.objects.get(ref, 0)
            for ref, size in publication.stored.items()
        )
    ):
        return None
    return row


def settle(
    session: AsyncSession,
    settings: Settings,
    row: Storage,
    publication: TraceStoragePublication,
) -> None:
    """Atomically replace the reservation with exact committed bytes and cleanup debt."""
    if row.state == _State.STORED:
        return
    uncertain = {ref: row.objects[ref] for ref in publication.uncertain}
    debt = sum(uncertain.values())
    stored = sum(publication.stored.values())
    settings.reserved_bytes -= row.size_bytes - debt
    settings.used_bytes += stored
    row.objects = publication.stored
    row.size_bytes = stored
    row.state = _State.STORED
    row.due_at = None
    # Keep a zero-byte receipt for an idempotent retry, tied to the captured turn.
    if uncertain:
        session.add(
            Storage(
                id=str(uuid4()),
                session_id=row.session_id,
                runtime_id=row.runtime_id,
                capture_id=row.capture_id,
                objects=uncertain,
                size_bytes=debt,
                state=_State.CLEANUP_RESERVED,
                due_at=utcnow() + _UNCERTAIN_WRITE,
            )
        )


def abandon(row: Storage) -> None:
    """Keep bytes charged after a publisher settles against an already fenced turn."""
    if row.state == _State.RESERVED:
        row.state = _State.CLEANUP_RESERVED
        row.due_at = utcnow() + _UNCERTAIN_WRITE


_SessionIds = tuple[str, ...] | Select[str]


async def enqueue_retained_erasure(
    session: AsyncSession, session_ids: _SessionIds, due_at: datetime
) -> None:
    """Schedule the existing full erasure workflow for removed owner chats."""
    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    owners = select(
        Owner.session_id,
        Owner.team_id,
        Owner.user_id,
        literal(due_at),
        literal("pending"),
    ).where(
        Owner.session_id.in_(session_ids),
        Owner.trace_retained_after_delete.is_(True),
        Owner.user_id.is_not(None),
    )
    statement = insert(PurgeQueueRow).from_select(
        ("session_id", "team_id", "user_id", "due_at", "status"), owners
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PurgeQueueRow.session_id],
            set_={"due_at": due_at, "status": "pending"},
            where=PurgeQueueRow.status == "done",
        )
    )


async def retire_conversations(
    session: AsyncSession,
    session_ids: _SessionIds,
    now: datetime,
) -> int:
    """Fence catalog access and queue immutable artifact refs for cleanup."""
    owners = cast(
        CursorResult,
        await session.execute(
            update(Owner)
            .where(Owner.session_id.in_(session_ids))
            .values(trace_last_captured_at=None, updated_at=Owner.updated_at)
            .execution_options(synchronize_session=False)
        ),
    )
    await revoke_conversation_grants(session, session_ids, now)
    await enqueue_retained_erasure(session, session_ids, now)
    await queue_artifact_cleanup(session, session_ids, now)
    await session.execute(
        delete(Turn)
        .where(Turn.session_id.in_(session_ids))
        .execution_options(synchronize_session=False)
    )
    return owners.rowcount


async def revoke_conversation_grants(
    session: AsyncSession, session_ids: _SessionIds, now: datetime
) -> None:
    await session.execute(
        update(Grant)
        .where(
            Grant.session_id.in_(session_ids),
            or_(Grant.revoked_at.is_(None), Grant.incident.is_not(None)),
        )
        .values(revoked_at=func.coalesce(Grant.revoked_at, now), incident=None)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        delete(ConversationTraceIncidentRow).where(
            ConversationTraceIncidentRow.session_id.in_(session_ids)
        )
    )


async def queue_artifact_cleanup(
    session: AsyncSession,
    session_ids: _SessionIds,
    now: datetime,
) -> None:
    """Retain accounted bytes while scheduling an erased or evicted session's objects."""
    for original, pending in (
        (_State.STORED, _State.CLEANUP_STORED),
        (_State.MEASURE, _State.CLEANUP_UNMEASURED),
    ):
        await session.execute(
            update(Storage)
            .where(Storage.session_id.in_(session_ids), Storage.state == original)
            .values(state=pending, due_at=now, lease=None)
            .execution_options(synchronize_session=False)
        )


async def maintain(session: AsyncSession, settings: Settings) -> tuple[int, int, int]:
    """Fence bounded batches of expired or capacity-evicted diagnostics."""
    now = utcnow()
    cutoff = now - timedelta(days=settings.retention_days)
    expired_ids = tuple(
        await session.scalars(
            select(Owner.session_id)
            .where(Owner.trace_last_captured_at <= cutoff)
            .order_by(Owner.trace_last_captured_at, Owner.session_id)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    if expired_ids:
        await retire_conversations(session, expired_ids, now)

    stale_grants = (
        select(Grant.grant_id)
        .join(Owner, Owner.session_id == Grant.session_id)
        .where(
            Grant.revoked_at.is_(None),
            Grant.diagnostic_at <= cutoff,
            Owner.trace_last_captured_at.is_(None),
        )
        .order_by(Grant.diagnostic_at, Grant.grant_id)
        .limit(_BATCH_SIZE)
        .with_for_update(of=Owner, skip_locked=True)
    )
    stale_grant_ids = list(await session.scalars(stale_grants))
    if stale_grant_ids:
        stale_sessions = select(Grant.session_id).where(
            Grant.grant_id.in_(stale_grant_ids)
        )
        await enqueue_retained_erasure(session, stale_sessions, now)
        await revoke_conversation_grants(session, stale_sessions, now)

    need = (
        settings.used_bytes
        + settings.reserved_bytes
        + settings.reclaim_target
        - settings.storage_cap_bytes
    )
    if need <= 0:
        settings.reclaim_target = 0
        return len(expired_ids), len(stale_grant_ids), 0
    pending = await session.scalar(
        select(func.sum(Storage.size_bytes)).where(
            Storage.state.in_((_State.CLEANUP_STORED, _State.CLEANUP_RESERVED))
        )
    )
    need -= pending or 0
    if need <= 0:
        return len(expired_ids), len(stale_grant_ids), 0
    shared = exists().where(
        Grant.session_id == Owner.session_id, Grant.revoked_at.is_(None)
    )
    writes = exists().where(
        Storage.session_id == Owner.session_id,
        Storage.state == _State.STORED,
        Storage.size_bytes > 0,
    )
    victims = list(
        await session.scalars(
            select(Owner.session_id)
            .where(Owner.trace_last_captured_at.is_not(None), writes)
            .order_by(shared, Owner.trace_last_captured_at, Owner.session_id)
            .limit(_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    if not victims:
        return len(expired_ids), len(stale_grant_ids), 0
    totals = await session.execute(
        select(Storage.session_id, func.sum(Storage.size_bytes))
        .where(Storage.session_id.in_(victims), Storage.state == _State.STORED)
        .group_by(Storage.session_id)
    )
    sizes = {session_id: size for session_id, size in totals}
    evictions: list[str] = []
    for session_id in victims:
        evictions.append(session_id)
        need -= sizes.get(session_id, 0)
        if need <= 0:
            break
    evicted = await retire_conversations(session, tuple(evictions), now)
    return len(expired_ids), len(stale_grant_ids), evicted


async def claim_cleanup(
    session: AsyncSession, runtime_id: str
) -> TraceStorageCleanup | None:
    """Lease one due unit of work exclusively to a replica of its owning runtime."""
    now = utcnow()
    row = await session.scalar(
        select(Storage)
        .where(
            Storage.runtime_id == runtime_id,
            Storage.due_at <= now,
        )
        .order_by(Storage.due_at, Storage.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    if row.state == _State.RESERVED:
        row.state = _State.CLEANUP_RESERVED
    lease = uuid4()
    row.lease = str(lease)
    row.due_at = now + _CLEANUP_LEASE
    return TraceStorageCleanup(
        id=UUID(row.id),
        lease=lease,
        session_id=row.session_id,
        refs=list(row.objects),
        measure=row.state == _State.MEASURE,
    )


async def complete_cleanup(
    session: AsyncSession,
    settings: Settings,
    runtime_id: str,
    work_id: str,
    result: TraceStorageCleanupResult,
) -> None:
    """Release charges only after the current lease confirms erasure."""
    row = await session.scalar(
        select(Storage).where(Storage.id == work_id).with_for_update()
    )
    if row is None or row.runtime_id != runtime_id or row.lease != str(result.lease):
        return
    if not result.success:
        degrade(settings, TraceDegradation.STORAGE)
        return
    if row.state == _State.MEASURE:
        if result.measured is None or result.measured.keys() != row.objects.keys():
            return
        row.objects = result.measured
        row.size_bytes = sum(row.objects.values())
        settings.used_bytes += row.size_bytes
        row.state = _State.STORED
        row.lease = None
        row.due_at = None
        return
    if row.state == _State.CLEANUP_STORED:
        settings.used_bytes -= row.size_bytes
    elif row.state == _State.CLEANUP_RESERVED:
        settings.reserved_bytes -= row.size_bytes
    await session.delete(row)
