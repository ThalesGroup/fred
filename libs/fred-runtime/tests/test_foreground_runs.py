from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import replace
from typing import cast

import pytest
from fred_runtime.common.outbound_credentials import RunRecord
from fred_runtime.runtime_support.foreground_runs import (
    AttachmentError,
    ForegroundRun,
    ForegroundRunRegistry,
    ReplayLimits,
)
from fred_sdk.contracts.runtime import RuntimeErrorEvent


def _frame(kind: str, **values: object) -> str:
    return f"data: {json.dumps({'kind': kind, **values})}\n\n"


def _record(run_id: str = "run-a", *, ceiling: float = 60.0) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        person_id="person-a",
        agent_id="agent-a",
        started_monotonic=time.monotonic(),
        run_ceiling_seconds=ceiling,
    )


class _Callbacks:
    def __init__(self) -> None:
        self.ends: list[tuple[str, str | None]] = []
        self.cancels: list[str] = []
        self.ended = asyncio.Event()

    async def on_end(self, outcome: str, reason: str | None) -> None:
        self.ends.append((outcome, reason))
        self.ended.set()

    def on_cancel(self, reason: str) -> None:
        self.cancels.append(reason)


def _run(
    stream: AsyncIterator[str],
    *,
    callbacks: _Callbacks | None = None,
    limits: ReplayLimits | None = None,
    run_id: str = "run-a",
) -> tuple[ForegroundRun, _Callbacks]:
    callbacks = callbacks or _Callbacks()
    run = ForegroundRun(
        _record(run_id),
        stream,
        limits=limits or ReplayLimits(grace_seconds=0.03),
        on_end=callbacks.on_end,
        on_cancel=callbacks.on_cancel,
    )
    return run, callbacks


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    return [frame async for frame in stream]


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_producer_and_reconnect_replays() -> None:
    release = asyncio.Event()

    async def source() -> AsyncIterator[str]:
        yield _frame("progress", value=1)
        await release.wait()
        yield _frame("final", value=2)

    run, callbacks = _run(source())
    run.start()
    first_attachment = await run.attach(None)
    first = await anext(first_attachment)
    await cast(AsyncGenerator[str, None], first_attachment).aclose()

    release.set()
    await callbacks.ended.wait()
    second = await run.attach(0)
    replayed = await _collect(second)

    assert '"sequence": 0' in first
    assert len(replayed) == 1
    assert '"kind": "final"' in replayed[0]
    assert callbacks.cancels == []
    assert callbacks.ends == [("succeeded", None)]


@pytest.mark.asyncio
async def test_attachment_is_atomic_and_rejected_attach_does_not_extend_grace() -> None:
    async def source() -> AsyncIterator[str]:
        await asyncio.Event().wait()
        yield ""  # pragma: no cover

    run, callbacks = _run(source())
    run.start()
    unused = await run.attach(None)
    with pytest.raises(AttachmentError) as error:
        await run.attach(None)
    assert (error.value.status_code, error.value.reason) == (
        409,
        "run_already_attached",
    )

    await asyncio.wait_for(callbacks.ended.wait(), 0.2)
    with pytest.raises(AttachmentError) as expired:
        await run.attach(None)
    assert expired.value.status_code == 410
    await cast(AsyncGenerator[str, None], unused).aclose()
    assert callbacks.cancels == ["cancelled"]


@pytest.mark.asyncio
async def test_replay_bounds_reject_evicted_and_ahead_cursors() -> None:
    async def source() -> AsyncIterator[str]:
        yield _frame("progress", value=1)
        yield _frame("progress", value=2)
        yield _frame("final", value=3)

    run, callbacks = _run(
        source(), limits=ReplayLimits(grace_seconds=1, max_events=2, max_bytes=4096)
    )
    run.start()
    await callbacks.ended.wait()

    with pytest.raises(AttachmentError) as evicted:
        await run.attach(None)
    assert (evicted.value.status_code, evicted.value.reason) == (
        409,
        "replay_unavailable",
    )
    with pytest.raises(AttachmentError) as ahead:
        await run.attach(3)
    assert (ahead.value.status_code, ahead.value.reason) == (409, "replay_unavailable")

    replay = await run.attach(0)
    assert len(await _collect(replay)) == 2


@pytest.mark.asyncio
async def test_replay_byte_bound_evicts_complete_oldest_frames() -> None:
    progress = _frame("progress", value="x" * 80)
    final = _frame("final")
    # Enough for either frame by itself, but not both together.
    byte_limit = max(len(progress.encode()), len(final.encode())) + 40

    async def source() -> AsyncIterator[str]:
        yield progress
        yield final

    run, callbacks = _run(
        source(),
        limits=ReplayLimits(grace_seconds=1, max_events=10, max_bytes=byte_limit),
    )
    run.start()
    await callbacks.ended.wait()

    with pytest.raises(AttachmentError) as evicted:
        await run.attach(None)
    assert evicted.value.reason == "replay_unavailable"
    replay = await run.attach(0)
    frames = await _collect(replay)
    assert len(frames) == 1
    assert '"kind": "final"' in frames[0]


@pytest.mark.asyncio
async def test_unexpected_stream_end_emits_a_contract_valid_unclassified_error() -> (
    None
):
    async def source() -> AsyncIterator[str]:
        yield _frame("status", status="running")

    run, callbacks = _run(source())
    run.start()
    attachment = await run.attach(None)
    frames = await _collect(attachment)

    payload = json.loads(frames[-1].split("data: ", 1)[1])
    event = RuntimeErrorEvent.model_validate(payload)
    assert event.reason is None
    assert callbacks.ends == [("failed", "execution_failed")]


@pytest.mark.asyncio
async def test_terminal_frame_remains_authoritative_when_cancel_races_finish() -> None:
    hold = asyncio.Event()
    closed = False

    async def source() -> AsyncIterator[str]:
        nonlocal closed
        try:
            yield _frame("final")
            await hold.wait()
        finally:
            closed = True

    run, callbacks = _run(source())
    run.start()
    attachment = await run.attach(None)
    final = await anext(attachment)
    assert '"kind": "final"' in final

    await run.cancel("run_ceiling_reached")
    await callbacks.ended.wait()
    with pytest.raises(AttachmentError) as overlap:
        await run.attach(0)
    assert (overlap.value.status_code, overlap.value.reason) == (
        409,
        "run_already_attached",
    )
    await cast(AsyncGenerator[str, None], attachment).aclose()
    replay = await run.attach(0)
    assert await _collect(replay) == []
    assert callbacks.ends == [("succeeded", None)]
    assert callbacks.cancels == ["run_ceiling_reached"]
    assert closed is True


@pytest.mark.asyncio
async def test_cancel_before_producer_runs_closes_and_finalizes_once() -> None:
    closed = False

    async def source() -> AsyncIterator[str]:
        nonlocal closed
        try:
            yield _frame("progress")
        finally:
            closed = True

    run, callbacks = _run(source())
    run.start()
    await run.cancel()
    await asyncio.wait_for(callbacks.ended.wait(), 0.2)
    await run.cancel()

    assert callbacks.ends == [("cancelled", "cancelled")]
    assert callbacks.cancels == ["cancelled"]
    # An async generator cancelled before its first instruction cannot execute
    # its own finally block, but aclose still runs through the shared finalizer.
    assert closed is False


@pytest.mark.asyncio
async def test_registry_capacity_rejection_finalizes_rejected_run() -> None:
    async def source() -> AsyncIterator[str]:
        await asyncio.Event().wait()
        yield ""  # pragma: no cover

    limits = ReplayLimits(grace_seconds=0.01, max_runs=1)
    registry = ForegroundRunRegistry(limits)
    admitted, _ = _run(source(), limits=limits, run_id="run-a")
    rejected, callbacks = _run(source(), limits=limits, run_id="run-b")
    registry.add(admitted)

    with pytest.raises(AttachmentError) as error:
        registry.add(rejected)
    assert error.value.status_code == 503
    await asyncio.wait_for(callbacks.ended.wait(), 0.2)
    assert callbacks.ends == [("failed", "foreground_capacity_exceeded")]
    await registry.close()


@pytest.mark.asyncio
async def test_registry_distinguishes_unknown_from_expired_run() -> None:
    async def source() -> AsyncIterator[str]:
        yield _frame("final")

    limits = ReplayLimits(grace_seconds=0.01)
    registry = ForegroundRunRegistry(limits)
    run, callbacks = _run(source(), limits=limits)
    registry.add(run)
    run.start()
    await callbacks.ended.wait()
    await asyncio.sleep(0.02)

    with pytest.raises(AttachmentError) as expired:
        registry.get("run-a")
    assert expired.value.status_code == 410
    with pytest.raises(AttachmentError) as unknown:
        registry.get("run-unknown")
    assert unknown.value.status_code == 404
    await registry.close()


@pytest.mark.asyncio
async def test_attachment_does_not_reset_original_absolute_deadline() -> None:
    async def source() -> AsyncIterator[str]:
        await asyncio.Event().wait()
        yield ""  # pragma: no cover

    callbacks = _Callbacks()
    record = replace(_record(ceiling=0.05), started_monotonic=time.monotonic() - 0.04)
    run = ForegroundRun(
        record,
        source(),
        limits=ReplayLimits(grace_seconds=1),
        on_end=callbacks.on_end,
        on_cancel=callbacks.on_cancel,
    )
    run.start()
    attachment = await run.attach(None)
    await asyncio.wait_for(callbacks.ended.wait(), 0.2)

    assert callbacks.cancels == ["run_ceiling_reached"]
    assert callbacks.ends == [("failed", "run_ceiling_reached")]
    await cast(AsyncGenerator[str, None], attachment).aclose()


@pytest.mark.asyncio
async def test_awaiting_human_uses_disconnect_grace_without_resuming_source() -> None:
    resumes = 0

    async def source() -> AsyncIterator[str]:
        nonlocal resumes
        yield _frame("awaiting_human", checkpoint_id="checkpoint-a")
        resumes += 1

    run, callbacks = _run(source())
    run.start()
    attachment = await run.attach(None)
    await anext(attachment)
    await cast(AsyncGenerator[str, None], attachment).aclose()
    await asyncio.wait_for(callbacks.ended.wait(), 0.2)

    assert resumes == 1
    assert callbacks.cancels == ["cancelled"]
    assert callbacks.ends == [("cancelled", "cancelled")]
