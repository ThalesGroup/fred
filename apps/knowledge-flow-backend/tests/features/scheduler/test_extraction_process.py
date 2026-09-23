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

"""Supervision of the extraction child process.

Real processes, real signals: what is under test is that a computation actually
stops and that a descendant it started stops with it, and a mock can show
neither. Most children are started with `fork` so each one costs nothing; one
test starts its child with `spawn`, the production method, because what the two
differ on — the child being a fresh interpreter that re-imports everything — is
the part `fork` cannot show.

Children report their pid through a file in the output directory rather than
through the pipe: the pipe carries the extraction's outcome, and on the
cancellation and timeout paths the supervisor closes it without reading.

Deliberately not covered here: docling. The subject is supervision, and it has
to hold for any child whatever it computes.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import pathlib
import signal
import time
from typing import Any

import pytest

from knowledge_flow_backend.features.scheduler import extraction_process
from knowledge_flow_backend.features.scheduler.extraction_process import (
    SHUTDOWN_RESERVE_SECONDS,
    ExtractionProcessError,
    ExtractionRequest,
    ExtractionStopUnconfirmed,
    ExtractionTimeout,
    _is_permanent,
    local_budget_seconds,
    run_extraction_in_process,
)

_TEST_START_METHOD = "fork"

# Not a pid any process can have as a parent, so the start-up guard's comparison
# is the only thing that can decide the outcome of that test.
_A_PARENT_WE_NEVER_HAD = 0


# ── test children ─────────────────────────────────────────────────────────────


def _report_pid(request: ExtractionRequest, name: str, pid: int) -> None:
    path = pathlib.Path(request.output_dir) / name
    staging = path.with_suffix(".staging")
    staging.write_text(str(pid))
    staging.replace(path)  # so the reader never sees a half-written pid


def _child_that_sleeps(request, _pipe, _parent_pid) -> None:
    os.setsid()
    _report_pid(request, "child.pid", os.getpid())
    time.sleep(300)


def _child_that_spawns_a_descendant(request, _pipe, _parent_pid) -> None:
    """The case the process-group signal exists for: killing the leader alone
    leaves this one holding the CPU the pod is about to hand to the next
    extraction."""
    os.setsid()
    descendant = multiprocessing.get_context("fork").Process(target=time.sleep, args=(300,), daemon=False)
    descendant.start()
    _report_pid(request, "descendant.pid", descendant.pid or 0)
    _report_pid(request, "child.pid", os.getpid())
    time.sleep(300)


def _child_that_leaves_a_descendant_behind(request, pipe, _parent_pid) -> None:
    """Ends by itself, successfully, having started a helper that outlives it."""
    os.setsid()
    descendant = multiprocessing.get_context("fork").Process(target=time.sleep, args=(300,), daemon=False)
    descendant.start()
    _report_pid(request, "descendant.pid", descendant.pid or 0)
    pipe.send({"error": None, "permanent": False})
    os._exit(0)


def _child_that_succeeds(_request, pipe, _parent_pid) -> None:
    pipe.send({"error": None, "permanent": False})
    os._exit(0)


def _child_that_fails_permanently(_request, pipe, _parent_pid) -> None:
    pipe.send({"error": "FileNotFoundError: no such document", "permanent": True})
    os._exit(1)


def _child_with_a_long_error(_request, pipe, _parent_pid) -> None:
    extraction_process._send_outcome(pipe, {"error": "Failure: " + "é" * 100_000, "permanent": True})
    os._exit(1)


@pytest.mark.asyncio
async def test_a_long_error_is_reported_without_blocking_child_exit(tmp_path) -> None:
    with pytest.raises(ExtractionProcessError, match="Failure:") as caught:
        await _supervise(_child_with_a_long_error, tmp_path, budget_seconds=5.0)
    assert caught.value.permanent is True
    assert len(str(caught.value).encode("utf-8")) <= 2048


def _child_that_is_killed(_request, _pipe, _parent_pid) -> None:
    # Reports nothing at all, exactly like a process the OOM killer takes.
    os.kill(os.getpid(), signal.SIGKILL)


def _child_checking_an_impossible_parent(request, _pipe, _parent_pid) -> None:
    """Runs the start-up guard against a parent that is not the one it was
    started by — what a child re-parented before its prctl call would see."""
    extraction_process._install_parent_death_signal(_A_PARENT_WE_NEVER_HAD)
    _report_pid(request, "survived.pid", os.getpid())
    time.sleep(5)


# ── helpers ───────────────────────────────────────────────────────────────────


class _SlowToDie:
    """A child that keeps answering `is_alive()` for a while.

    SIGKILL is immediate, so a real process cannot show what the supervisor does
    while it is still waiting for one. Carries no pid, so nothing is signalled.
    """

    pid = None

    def __init__(self, polls: int) -> None:
        self._polls = polls

    def is_alive(self) -> bool:
        self._polls -= 1
        return self._polls > 0


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _wait_gone(pid: int, timeout: float = 15.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline and _alive(pid):
        await asyncio.sleep(0.05)
    return not _alive(pid)


async def _read_pid(output_dir: pathlib.Path, name: str = "child.pid", timeout: float = 30.0) -> int:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if (output_dir / name).exists():
            return int((output_dir / name).read_text())
        await asyncio.sleep(0.05)
    raise AssertionError(f"the child never reported {name}")


def _request(output_dir: pathlib.Path) -> ExtractionRequest:
    return ExtractionRequest(input_path="/tmp/in", output_dir=str(output_dir), metadata_json="{}", profile="rich", config_file=None)


async def _supervise(target, output_dir: pathlib.Path, *, budget_seconds: float = 30.0, heartbeat=lambda: None, start_method: str = _TEST_START_METHOD):
    return await run_extraction_in_process(
        request=_request(output_dir),
        budget_seconds=budget_seconds,
        heartbeat=heartbeat,
        target=target,
        start_method=start_method,
    )


def _start_directly(target, output_dir: pathlib.Path) -> Any:
    """Start a child outside the supervisor, to drive the stop on its own."""
    context = multiprocessing.get_context(_TEST_START_METHOD)
    _parent_conn, child_conn = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(_request(output_dir), child_conn, os.getpid()), daemon=False)
    process.start()
    child_conn.close()
    return process


async def _stop(process: Any) -> bool:
    group = extraction_process._ChildGroup(process.pid)
    group.refresh()
    return await extraction_process._stop_group(process, group)


# ── outcomes keep their nature ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_successful_extraction_returns(tmp_path) -> None:
    await _supervise(_child_that_succeeds, tmp_path)


@pytest.mark.asyncio
async def test_a_permanent_error_is_reported_as_permanent(tmp_path) -> None:
    with pytest.raises(ExtractionProcessError) as raised:
        await _supervise(_child_that_fails_permanently, tmp_path)
    assert raised.value.permanent is True


@pytest.mark.asyncio
async def test_a_killed_child_is_not_reported_as_a_document_error(tmp_path) -> None:
    """An abnormal exit says nothing about the document. Reading it as permanent
    would condemn a file a retry on a healthier pod would have ingested."""
    with pytest.raises(ExtractionProcessError) as raised:
        await _supervise(_child_that_is_killed, tmp_path)
    assert raised.value.permanent is False
    assert "abnormally" in str(raised.value)


# ── stopping actually stops ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stopping_kills_the_child_and_reaps_it(tmp_path) -> None:
    process = _start_directly(_child_that_sleeps, tmp_path)
    pid = await _read_pid(tmp_path)
    try:
        assert await _stop(process) is True
        assert await _wait_gone(pid), "the child survived the stop"
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_a_descendant_of_the_child_is_stopped_too(tmp_path) -> None:
    """PDEATHSIG covers the child alone — it is not inherited — so a descendant is
    exactly why the activity signals the whole process group."""
    process = _start_directly(_child_that_spawns_a_descendant, tmp_path)
    pid = await _read_pid(tmp_path)
    descendant = await _read_pid(tmp_path, "descendant.pid")
    try:
        assert await _stop(process) is True
        assert await _wait_gone(pid), "the child survived the stop"
        assert await _wait_gone(descendant), "the descendant outlived its group"
    finally:
        for stray in (pid, descendant):
            if _alive(stray):
                os.kill(stray, signal.SIGKILL)


@pytest.mark.asyncio
async def test_a_child_that_ended_by_itself_does_not_leave_its_descendant(tmp_path) -> None:
    """The child can finish on its own — here successfully — and still have left
    a helper holding the CPU the pod is about to hand to the next extraction."""
    await _supervise(_child_that_leaves_a_descendant_behind, tmp_path)

    descendant = int((tmp_path / "descendant.pid").read_text())
    assert await _wait_gone(descendant), "a helper outlived the child that started it"


@pytest.mark.asyncio
async def test_the_local_budget_stops_the_child_itself(tmp_path) -> None:
    """Temporal's timeout does not kill anything, so the activity has to."""
    with pytest.raises(ExtractionTimeout):
        await _supervise(_child_that_sleeps, tmp_path, budget_seconds=1.0)
    assert await _wait_gone(await _read_pid(tmp_path)), "the child outlived its budget"


@pytest.mark.asyncio
async def test_cancelling_terminates_the_child_before_propagating(tmp_path) -> None:
    """The ordering the whole design rests on: the slot is never reported free
    while the computation is still running."""
    task = asyncio.create_task(_supervise(_child_that_sleeps, tmp_path, budget_seconds=60.0))
    pid = await _read_pid(tmp_path)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task  # Propagate the task exception into pytest.raises.

    assert not _alive(pid), "the child was still running when the cancellation propagated"


@pytest.mark.asyncio
async def test_cancelling_during_start_up_leaves_nothing_running(tmp_path) -> None:
    """Cancellation can land before the supervisor has even reached its wait.
    Whatever process exists by then must still be gone when it gives up."""
    pids: list[int] = []
    original = extraction_process._stop_group

    async def _record_then_stop(process, group):
        if process.pid:
            pids.append(process.pid)
        return await original(process, group)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(extraction_process, "_stop_group", _record_then_stop)
        task = asyncio.create_task(_supervise(_child_that_sleeps, tmp_path, budget_seconds=60.0))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task  # Propagate the task exception into pytest.raises.

    assert pids, "the supervisor never reached its stop path"
    for pid in pids:
        assert await _wait_gone(pid), "a child outlived a cancellation during start-up"


@pytest.mark.asyncio
async def test_a_second_cancellation_lands_inside_the_stop_without_abandoning_it(tmp_path) -> None:
    """The activity can be cancelled again while it is already stopping. The
    second cancellation is made to land inside the stop, not around it, and the
    child must still be dead — and the stop finished, not left in flight — when
    the supervisor returns."""
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = False
    original = extraction_process._stop_group

    async def _slow_stop(process, group):
        nonlocal finished
        entered.set()
        await release.wait()
        stopped = await original(process, group)
        finished = True
        return stopped

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(extraction_process, "_stop_group", _slow_stop)
        task = asyncio.create_task(_supervise(_child_that_sleeps, tmp_path, budget_seconds=60.0))
        pid = await _read_pid(tmp_path)

        task.cancel()
        await entered.wait()  # the stop is running and has not returned
        task.cancel()  # ... so this one lands inside it
        await asyncio.sleep(0)
        release.set()

        with pytest.raises(asyncio.CancelledError):
            await task  # Propagate the task exception into pytest.raises.

    assert finished, "the second cancellation abandoned the stop"
    assert await _wait_gone(pid), "the child survived a second cancellation"


@pytest.mark.asyncio
async def test_an_unconfirmed_stop_is_not_reported_as_a_freed_slot(tmp_path) -> None:
    """A budget timeout tells Temporal this pod is free for the next attempt. It
    must not be what the activity reports when it could not confirm the child is
    gone — that is the overlap this whole mechanism exists to refuse."""
    original = extraction_process._stop_group

    async def _stops_but_never_confirms(process, group):
        await original(process, group)
        return False

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(extraction_process, "_stop_group", _stops_but_never_confirms)
        with pytest.raises(ExtractionStopUnconfirmed) as raised:
            await _supervise(_child_that_sleeps, tmp_path, budget_seconds=1.0)

    assert raised.value.permanent is False, "an unstoppable child says nothing about the document"


@pytest.mark.asyncio
async def test_an_unconfirmed_stop_outranks_the_cancellation_itself(tmp_path) -> None:
    """Even a cancellation — the outcome that normally means "this document is
    done with the pod" — must not be reported while the computation may still be
    running."""
    original = extraction_process._stop_group

    async def _stops_but_never_confirms(process, group):
        await original(process, group)
        return False

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(extraction_process, "_stop_group", _stops_but_never_confirms)
        task = asyncio.create_task(_supervise(_child_that_sleeps, tmp_path, budget_seconds=60.0))
        await _read_pid(tmp_path)
        task.cancel()
        with pytest.raises(ExtractionStopUnconfirmed):
            await task  # Propagate the task exception into pytest.raises.


@pytest.mark.asyncio
async def test_the_supervisor_keeps_heartbeating_while_it_waits(tmp_path) -> None:
    """Temporal delivers cancellation through heartbeat responses, so a
    supervisor that stopped beating could not be cancelled."""
    beats = 0

    def _beat() -> None:
        nonlocal beats
        beats += 1

    with pytest.raises(ExtractionTimeout):
        await _supervise(_child_that_sleeps, tmp_path, budget_seconds=1.0, heartbeat=_beat)

    assert beats > 1


@pytest.mark.asyncio
async def test_the_supervisor_does_not_block_the_event_loop(tmp_path) -> None:
    """`process.join()` would freeze every other activity's heartbeat on this
    worker, including the ones this supervisor needs to receive its own cancel."""
    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    ticker = asyncio.create_task(_ticker())
    with pytest.raises(ExtractionTimeout):
        await _supervise(_child_that_sleeps, tmp_path, budget_seconds=1.0)
    ticker.cancel()

    assert ticks > 5


@pytest.mark.asyncio
async def test_the_event_loop_stays_available_while_the_stop_waits() -> None:
    """The stop is the other half of the same rule: waiting for a child to be
    reaped must not block the loop either, or the worker stops heartbeating for
    every other activity precisely while it is cancelling one."""
    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    slow: Any = _SlowToDie(polls=6)
    ticker = asyncio.create_task(_ticker())
    stopped = await extraction_process._stop_group(slow, extraction_process._ChildGroup(None))
    ticker.cancel()

    assert stopped is True
    assert ticks > 3, "the loop was blocked while the stop waited"


# ── the start-up guard ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_child_whose_parent_is_not_the_expected_one_refuses_to_run(tmp_path) -> None:
    """PDEATHSIG is lost when the parent dies between the fork and the prctl
    call. Comparing the parent's identity is what detects it — `getppid() == 1`
    does not, under a subreaper or when pid 1 is the worker itself."""
    process = _start_directly(_child_checking_an_impossible_parent, tmp_path)
    for _ in range(100):
        if process.exitcode is not None:
            break
        await asyncio.sleep(0.05)

    assert process.exitcode == 1
    assert not (tmp_path / "survived.pid").exists(), "the child ran on without its parent"


# ── the production start method ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_spawned_child_is_started_and_stopped(tmp_path) -> None:
    """Production spawns; the tests above fork. Spawn is a fresh interpreter that
    re-imports everything and reaches the supervisor's wait much later, so the
    start, the group it creates and the stop are worth exercising once on the
    method that actually ships."""
    task = asyncio.create_task(_supervise(_child_that_sleeps, tmp_path, budget_seconds=180.0, start_method="spawn"))
    pid = await _read_pid(tmp_path, timeout=120.0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task  # Propagate the task exception into pytest.raises.

    assert not _alive(pid), "the spawned child was still running when the cancellation propagated"


# ── the derived budget ────────────────────────────────────────────────────────


def test_the_local_budget_reserves_time_to_stop_the_child() -> None:
    assert local_budget_seconds(activity_timeout_seconds=7200, elapsed_seconds=100) == 7200 - 100 - SHUTDOWN_RESERVE_SECONDS


def test_an_attempt_with_nothing_left_gets_no_budget() -> None:
    """No floor: a floor would start an extraction the attempt has no time to
    finish, and the child would be killed part-way through for nothing."""
    assert local_budget_seconds(activity_timeout_seconds=60, elapsed_seconds=59) < 0


@pytest.mark.asyncio
async def test_an_exhausted_attempt_starts_no_process(tmp_path) -> None:
    started: list[Any] = []

    def _record(*args, **kwargs):
        started.append(args)
        raise AssertionError("a process was started with no budget to run it")

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(multiprocessing, "get_context", _record)
        with pytest.raises(ExtractionTimeout):
            await _supervise(_child_that_sleeps, tmp_path, budget_seconds=-29.0)

    assert not started


# ── which errors are settled ──────────────────────────────────────────────────


@pytest.mark.parametrize("exc", [FileNotFoundError("gone"), ValueError("unsupported"), UnicodeDecodeError("utf-8", b"", 0, 1, "bad")])
def test_settled_errors_are_permanent(exc) -> None:
    assert _is_permanent(exc) is True


@pytest.mark.parametrize("exc", [ConnectionError("minio down"), TimeoutError("slow"), MemoryError(), OSError("disk")])
def test_transient_errors_stay_retryable(exc) -> None:
    assert _is_permanent(exc) is False
