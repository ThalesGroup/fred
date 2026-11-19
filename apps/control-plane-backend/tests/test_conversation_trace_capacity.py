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
    ConversationTraceStorageRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
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
    ref = next(iter(draft.objects))
    result = TraceFinalization.model_validate(
        {
            "outcome": "completed",
            "duration_ms": 20,
            "sse": {
                "observed_through_rank": rank,
                "outgoing": {
                    "ref": ref,
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
    assert await store.finalize(_RUNTIME, admission.capture_id, result)
    return ref


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
