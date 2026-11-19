# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Exercise shared trace accounting through independent store sessions."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from control_plane_backend.conversation_traces import capacity
from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceSettingsUpdate,
)
from control_plane_backend.conversation_traces.store import ConversationTraceStore
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
    ConversationTraceIncidentRow,
    ConversationTraceStorageRow,
    ConversationTraceTurnRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from control_plane_backend.scheduler.queue_store import PurgeQueueStore
from control_plane_backend.sessions.store import SessionMetadataStore
from fred_core.common import TeamId
from fred_core.conversation_trace import (
    TraceAdmissionRequest,
    TraceFinalization,
    TraceHistoryBoundary,
    TraceHistoryIncident,
    TraceOutcome,
    TraceStorageCleanupResult,
    TraceStoragePublication,
    TraceStorageReservation,
    TraceStorageReservationState,
)
from fred_core.history.history_schema import TraceFailureCategory
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_RUNTIME = "fred-agents"


async def _seed(engine: AsyncEngine, *sessions: str):
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            AgentInstanceRow(
                agent_instance_id="agent",
                team_id="team",
                template_id="synthetic",
                source_runtime_id=_RUNTIME,
                source_agent_id="synthetic",
                display_name="Synthetic assistant",
            )
        )
        session.add_all(
            [
                SessionMetadataRow(
                    session_id=identity,
                    team_id="team",
                    agent_instance_id="agent",
                    user_id="owner",
                )
                for identity in sessions
            ]
        )


async def _admit(store: ConversationTraceStore, session_id: str, rank: int = 0):
    return await store.admit(
        _RUNTIME,
        TraceAdmissionRequest(
            session_id=session_id,
            exchange_id=f"exchange-{rank}",
            user_id="owner",
            agent_instance_id="agent",
            history_rank=rank,
        ),
    )


def _draft(size: int):
    return TraceStorageReservation(publication_id=uuid4(), objects={uuid4().hex: size})


async def _publish(
    store: ConversationTraceStore,
    session_id: str,
    size: int,
    rank: int = 0,
):
    admission = await _admit(store, session_id, rank)
    assert admission is not None
    draft = _draft(size)
    assert (
        await store.reserve_storage(_RUNTIME, admission.capture_id, draft)
        == TraceStorageReservationState.RESERVED
    )
    # Persist a raw outgoing SSE fragment under the planned reference.
    assert await store.finalize(
        _RUNTIME, admission.capture_id, _publication_result(draft, rank)
    )
    return next(iter(draft.objects))


def _publication_result(draft: TraceStorageReservation, rank: int) -> TraceFinalization:
    return TraceFinalization.model_validate(
        {
            "outcome": "completed",
            "duration_ms": 20,
            "segment_id": draft.segment_id,
            "sse": {
                "observed_through_rank": rank,
                "outgoing": {
                    "ref": next(iter(draft.objects)),
                    "started_ms": 0,
                    "headers_ms": 0,
                    "end_ms": 20,
                    "last_event_ms": 19,
                    "longest_gap": [0, 19],
                    "availability": "captured",
                    "ending": "completed",
                    "frame_count": 1,
                    "frames": [{"at_ms": 19, "kind": "done", "size": 5, "offset": 0}],
                },
                "provider": [],
            },
            "storage": {
                "publication_id": draft.publication_id,
                "stored": draft.objects,
                "uncertain": [],
            },
        }
    )


@pytest.mark.parametrize("reserve_before_resume", [False, True])
@pytest.mark.asyncio
async def test_late_pause_publication_preserves_resumed_failure_and_order(
    control_plane_sql_engine: AsyncEngine, reserve_before_resume: bool
):
    engine = control_plane_sql_engine
    await _seed(engine, "shared-exchange")
    one, two = ConversationTraceStore(engine), ConversationTraceStore(engine)
    await one.set_settings(ConversationTraceSettingsUpdate(enabled=True))
    request = TraceAdmissionRequest(
        session_id="shared-exchange",
        exchange_id="reused",
        user_id="owner",
        agent_instance_id="agent",
        history_rank=1,
    )
    pause, resume = uuid4(), uuid4()
    admission = await one.admit(_RUNTIME, request, segment_id=pause)
    assert admission and admission.segment_id == pause
    capture = admission.capture_id
    assert await two.admit(_RUNTIME, request, segment_id=pause) == admission
    pause_draft = TraceStorageReservation(
        publication_id=pause, segment_id=pause, objects={uuid4().hex: 10}
    )
    pause_result = _publication_result(pause_draft, 4).model_copy(
        update={"outcome": TraceOutcome.PAUSED}
    )
    if reserve_before_resume:
        assert (
            await one.reserve_storage(_RUNTIME, capture, pause_draft)
            == TraceStorageReservationState.RESERVED
        )
    resumed = await two.admit(
        _RUNTIME, request.model_copy(update={"history_rank": 5}), segment_id=resume
    )
    assert resumed and resumed.capture_id == capture
    failed = TraceFinalization(
        segment_id=resume,
        outcome=TraceOutcome.FAILED,
        evidence_pending=True,
        duration_ms=200,
        failure_category=TraceFailureCategory.HTTP_5XX,
        support_error_ref="4" * 32,
    )
    assert await two.finalize(_RUNTIME, capture, failed)
    async with async_sessionmaker(engine)() as session:
        terminal = await session.get(ConversationTraceTurnRow, capture)
        assert terminal is not None
    resume_draft = TraceStorageReservation(
        publication_id=resume, segment_id=resume, objects={uuid4().hex: 15}
    )
    assert (
        await two.reserve_storage(_RUNTIME, capture, resume_draft)
        == TraceStorageReservationState.RESERVED
    )
    resume_result = _publication_result(resume_draft, 7).model_copy(
        update={"outcome": TraceOutcome.FAILED}
    )
    assert await two.finalize(_RUNTIME, capture, resume_result)
    assert (
        await one.reserve_storage(_RUNTIME, capture, pause_draft)
        == TraceStorageReservationState.RESERVED
    )
    assert await one.finalize(_RUNTIME, capture, pause_result)
    assert await two.finalize(_RUNTIME, capture, pause_result)
    assert await one.finalize(_RUNTIME, capture, failed)
    assert (await one.settings()).used_bytes == 25
    assert (await two.settings()).reserved_bytes == 0
    assert [
        item.observed_through_rank
        for item in await one.sse_segments("shared-exchange", "reused")
    ] == [4, 7]
    async with async_sessionmaker(engine)() as session:
        row = await session.get(ConversationTraceTurnRow, capture)
        assert row is not None
        assert row.outcome == terminal.outcome == TraceOutcome.FAILED
        assert row.completed_at == terminal.completed_at
        assert row.duration_ms == terminal.duration_ms
        assert row.failure_category == TraceFailureCategory.HTTP_5XX
        assert row.support_error_ref == "4" * 32
    assert await one.flush_captures() == 1
    assert not await two.finalize(_RUNTIME, capture, pause_result)
    assert (
        await one.reserve_storage(_RUNTIME, capture, pause_draft)
        == TraceStorageReservationState.FENCED
    )


@pytest.mark.asyncio
async def test_concurrent_publications_and_recovered_leases(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    await _seed(engine, "first", "second")
    first, second = ConversationTraceStore(engine), ConversationTraceStore(engine)
    await first.set_settings(
        ConversationTraceSettingsUpdate(enabled=True, storage_cap_bytes=100)
    )
    sessions = (await _admit(first, "first"), await _admit(second, "second"))
    assert sessions[0] is not None and sessions[1] is not None
    drafts = (_draft(70), _draft(70))
    states = await asyncio.gather(
        first.reserve_storage(_RUNTIME, sessions[0].capture_id, drafts[0]),
        second.reserve_storage(_RUNTIME, sessions[1].capture_id, drafts[1]),
    )
    assert set(states) == {
        TraceStorageReservationState.RESERVED,
        TraceStorageReservationState.CAPACITY,
    }
    winner = states.index(TraceStorageReservationState.RESERVED)
    capture = sessions[winner]
    assert capture is not None
    draft = drafts[winner]
    live = await second.settings()
    assert live.reserved_bytes == 70 and live.used_bytes == 0 and live.degraded
    assert (await second.next_storage_cleanup(_RUNTIME))[0] is None
    assert await first.finalize(
        _RUNTIME,
        capture.capture_id,
        TraceFinalization(
            outcome=TraceOutcome.COMPLETED,
            duration_ms=20,
            http_incomplete=True,
            storage=TraceStoragePublication(
                publication_id=draft.publication_id,
                stored={},
                uncertain=list(draft.objects),
            ),
        ),
    )
    state = await first.settings()
    assert state.reserved_bytes == 70 and state.used_bytes == 0
    assert (await first.next_storage_cleanup(_RUNTIME))[0] is None
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(ConversationTraceStorageRow)
            .where(ConversationTraceStorageRow.due_at.is_not(None))
            .values(due_at=utcnow() - timedelta(seconds=1))
        )
    job, _ = await second.next_storage_cleanup(_RUNTIME)
    assert job is not None and job.refs == list(draft.objects)
    assert (await first.next_storage_cleanup(_RUNTIME))[0] is None
    await first.finish_storage_cleanup(
        "other-runtime", str(job.id), TraceStorageCleanupResult(lease=job.lease)
    )
    assert (await first.settings()).reserved_bytes == 70
    await first.finish_storage_cleanup(
        _RUNTIME, str(job.id), TraceStorageCleanupResult(lease=job.lease, success=False)
    )
    assert (await second.settings()).reserved_bytes == 70
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(ConversationTraceStorageRow)
            .where(ConversationTraceStorageRow.id == str(job.id))
            .values(due_at=utcnow() - timedelta(seconds=1))
        )
    replacement, _ = await first.next_storage_cleanup(_RUNTIME)
    assert (
        replacement is not None
        and replacement.id == job.id
        and replacement.lease != job.lease
    )
    await second.finish_storage_cleanup(
        _RUNTIME, str(job.id), TraceStorageCleanupResult(lease=job.lease)
    )
    assert (await second.settings()).reserved_bytes == 70
    await second.finish_storage_cleanup(
        _RUNTIME, str(job.id), TraceStorageCleanupResult(lease=replacement.lease)
    )
    assert (await second.settings()).reserved_bytes == 0


@pytest.mark.asyncio
async def test_eviction_and_retention_leave_ordinary_sessions(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    await _seed(engine, "shared", "unshared", "history")
    first, second = ConversationTraceStore(engine), ConversationTraceStore(engine)
    await first.set_settings(ConversationTraceSettingsUpdate(enabled=True))
    await _publish(first, "shared", 35)
    refs = {
        await _publish(second, "unshared", 20),
        await _publish(first, "unshared", 25, 5),
    }
    shared = await first.reference("shared")
    history = await second.reference("history")
    assert shared is not None and history is not None
    old = utcnow() - timedelta(days=8)
    older = old - timedelta(days=25)
    shared_boundary = TraceHistoryBoundary(
        exchange_id="exchange-0",
        first_rank=0,
        last_rank=0,
        turn_number=1,
        started_at=old,
    )
    await first.set_consent(shared, shared_boundary)
    await second.set_consent(
        history,
        shared_boundary.model_copy(update={"started_at": older}),
        incident=TraceHistoryIncident(
            cutoff=shared_boundary.model_copy(update={"started_at": older}),
            support_error_ref=uuid4().hex,
        ),
    )
    async with async_sessionmaker(engine).begin() as session:
        await session.execute(
            update(SessionMetadataRow)
            .where(SessionMetadataRow.session_id == "shared")
            .values(trace_last_captured_at=old)
        )
    await second.set_settings(ConversationTraceSettingsUpdate(storage_cap_bytes=50))
    observed: set[str] = set()
    for _ in range(2):
        work, retired = await first.next_storage_cleanup(_RUNTIME)
        assert work is not None and work.session_id == "unshared"
        observed.update(work.refs)
        if not observed == refs:
            assert retired == (0, 1, 1)
        await second.finish_storage_cleanup(
            _RUNTIME, str(work.id), TraceStorageCleanupResult(lease=work.lease)
        )
    assert observed == refs
    assert (await first.settings()).used_bytes == 35
    remaining = await second.reference("shared")
    evicted = await second.reference("unshared")
    expired = await second.reference("history")
    assert (
        remaining is not None
        and remaining.has_capture
        and remaining.consent is not None
    )
    assert evicted is not None and not evicted.visible
    assert expired is not None and not expired.visible
    await first.set_settings(ConversationTraceSettingsUpdate(retention_days=5))
    work, retired = await first.next_storage_cleanup(_RUNTIME)
    assert retired == (1, 0, 0)
    assert work is not None and work.session_id == "shared"
    async with async_sessionmaker(engine)() as session:
        assert set(await session.scalars(select(SessionMetadataRow.session_id))) == {
            "shared",
            "unshared",
            "history",
        }


@pytest.mark.asyncio
async def test_sampling_is_stable_across_store_instances(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    identities = [str(uuid4()) for _ in range(24)]
    await _seed(engine, *identities)
    one, two = ConversationTraceStore(engine), ConversationTraceStore(engine)
    await one.set_settings(
        ConversationTraceSettingsUpdate(enabled=True, sampling_percent=35)
    )
    for identity in identities:
        expected = capacity.sampled(identity, 35)
        assert bool(await _admit(one, identity)) == expected
        assert bool(await _admit(two, identity, 3)) == expected
    await two.set_settings(ConversationTraceSettingsUpdate(sampling_percent=100))
    for identity in identities:
        assert await _admit(one, identity, 6) is not None


@pytest.mark.asyncio
async def test_flush_fences_old_reservations_and_leaves_history_only_shares(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    await _seed(engine, "active", "history")
    first, second = ConversationTraceStore(engine), ConversationTraceStore(engine)
    await first.set_settings(ConversationTraceSettingsUpdate(enabled=True))
    old_ref = await _publish(first, "active", 30)
    pending = await _admit(second, "active", rank=4)
    assert pending is not None
    draft = _draft(25)
    assert (
        await second.reserve_storage(_RUNTIME, pending.capture_id, draft)
        == TraceStorageReservationState.RESERVED
    )
    history = await first.reference("history")
    assert history is not None
    boundary = TraceHistoryBoundary(
        exchange_id="exchange-0",
        first_rank=0,
        last_rank=1,
        turn_number=1,
        started_at=utcnow(),
    )
    await first.set_consent(
        history,
        boundary,
        incident=TraceHistoryIncident(cutoff=boundary, support_error_ref=uuid4().hex),
    )
    assert await first.flush_captures() == 1
    assert (await second.settings()).enabled
    assert (await second.settings()).reserved_bytes == 25
    kept = await second.reference("history")
    assert kept and kept.consent and not kept.has_capture
    active = await second.reference("active")
    assert active and not active.visible
    assert (
        await second.reserve_storage(_RUNTIME, pending.capture_id, _draft(5))
        == TraceStorageReservationState.FENCED
    )
    assert not await second.finalize(
        _RUNTIME,
        pending.capture_id,
        TraceFinalization(
            outcome=TraceOutcome.COMPLETED,
            duration_ms=20,
            http_incomplete=True,
            storage=TraceStoragePublication(
                publication_id=draft.publication_id,
                stored={},
                uncertain=list(draft.objects),
            ),
        ),
    )
    new_ref = await _publish(second, "active", 16, rank=8)
    job, _ = await first.next_storage_cleanup(_RUNTIME)
    assert job and job.refs == [old_ref] and new_ref not in job.refs
    await second.finish_storage_cleanup(
        _RUNTIME, str(job.id), TraceStorageCleanupResult(lease=job.lease)
    )
    active = await first.reference("active")
    assert active and active.has_capture
    assert (await first.settings()).used_bytes == 16
    assert (await first.settings()).reserved_bytes == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("removal", ["selected", "flush", "expiry"])
async def test_retained_chat_enters_ordinary_erasure_queue_when_diagnostics_end(
    control_plane_sql_engine: AsyncEngine,
    removal: str,
):
    engine = control_plane_sql_engine
    await _seed(engine, "kept", "unshared")
    store = ConversationTraceStore(engine)
    metadata = SessionMetadataStore(engine)
    queue = PurgeQueueStore(engine)
    team = TeamId("team")
    assert (
        await metadata.retain_for_support(
            "unshared", team, "owner", None, expected_grant_id=None
        )
        is None
    )
    await store.set_settings(ConversationTraceSettingsUpdate(enabled=True))
    if removal != "expiry":
        await _publish(store, "kept", 35)
    cutoff = TraceHistoryBoundary(
        exchange_id="exchange-0",
        first_rank=0,
        last_rank=1,
        turn_number=1,
        started_at=utcnow() - timedelta(days=31),
    )
    original = await store.reference("kept")
    assert original is not None
    grant, _ = await store.set_consent(
        original,
        cutoff,
        incident=TraceHistoryIncident(cutoff=cutoff, support_error_ref=uuid4().hex),
    )
    assert grant is not None
    current_grant, _ = await store.set_consent(
        original,
        cutoff.model_copy(update={"last_rank": cutoff.last_rank + 1}),
        expected_version=grant.grant_id,
    )
    assert current_grant is not None
    assert (
        await metadata.retain_for_support(
            "kept", team, "intruder", None, expected_grant_id=current_grant.grant_id
        )
        is None
    )
    assert (
        await metadata.retain_for_support(
            "kept", team, "owner", None, expected_grant_id=grant.grant_id
        )
        is None
    )
    visible = await store.reference("kept")
    assert visible and not visible.retained_after_delete
    grant_id = await metadata.retain_for_support(
        "kept", team, "owner", None, expected_grant_id=current_grant.grant_id
    )
    assert grant_id == current_grant.grant_id
    saved = await store.reference("kept")
    assert saved and saved.retained_after_delete and saved.consent
    assert saved.consent.cutoff.first_rank == cutoff.first_rank
    assert await metadata.owner_hidden_sessions(
        _RUNTIME, "owner", ["unshared", "kept"]
    ) == ["kept"]
    assert not await queue.list_due(limit=10)
    if removal == "selected":
        assert await store.delete_conversations(["unshared", "kept", "kept"]) == 1
        assert await store.delete_conversations(["kept"]) == 0
    elif removal == "expiry":
        _, retired = await store.next_storage_cleanup(_RUNTIME)
        assert retired == (0, 1, 0)
    else:
        assert await store.flush_captures() == 1
    due = await queue.list_due(limit=10)
    assert [(item.session_id, item.user_id) for item in due] == [("kept", "owner")]
    fenced = await store.reference("kept")
    assert fenced and not fenced.visible
    async with async_sessionmaker(engine)() as session:
        assert (
            await session.scalar(select(ConversationTraceIncidentRow.support_error_ref))
            is None
        )
    ordinary = await metadata.get("unshared")
    assert ordinary and not ordinary.trace_retained_after_delete
    assert await metadata.delete("kept", team, "owner")
    async with async_sessionmaker(engine)() as session:
        assert await session.get(ConversationTraceConsentRow, grant_id) is None
