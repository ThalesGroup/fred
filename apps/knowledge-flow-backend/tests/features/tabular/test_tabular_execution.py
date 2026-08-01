# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Execution-guard behaviour for tabular DuckDB jobs (issue #2182).

These tests exercise `features/tabular/execution.py` directly: it holds no
ApplicationContext or dataset knowledge, so nothing here needs an ingestion
fixture, a content store, or a network.
"""

from __future__ import annotations

import asyncio
import threading
import time

import duckdb
import pytest

from knowledge_flow_backend.common.structures import TabularQueryConfig
from knowledge_flow_backend.features.tabular.execution import (
    DuckDBAbortHandle,
    TabularCapacityExceededError,
    TabularExecutionTimeoutError,
    close_duckdb_connection,
    open_duckdb_connection,
    reset_execution_state_for_tests,
    run_duckdb_job,
)


@pytest.fixture(autouse=True)
def _fresh_guard():
    """The pool and admission counter are process-wide; give every test its own."""

    reset_execution_state_for_tests()
    yield
    reset_execution_state_for_tests()


def _config(**overrides) -> TabularQueryConfig:
    return TabularQueryConfig(**overrides)


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_while_a_duckdb_job_blocks():
    """AC: no synchronous DuckDB work executes on the event loop."""

    release = threading.Event()
    ticks = 0

    def _job(handle: DuckDBAbortHandle) -> str:
        del handle
        release.wait(timeout=5)
        return "done"

    async def _ticker():
        nonlocal ticks
        while not release.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    ticker = asyncio.create_task(_ticker())
    job = asyncio.create_task(run_duckdb_job(_job, config=_config(), operation="query"))
    await asyncio.sleep(0.1)
    # If the job ran on the loop, the ticker could not have advanced at all.
    assert ticks > 3
    release.set()
    assert await job == "done"
    await ticker


@pytest.mark.asyncio
async def test_never_more_than_max_concurrent_queries_run_at_once():
    """AC: DuckDB jobs per process are bounded."""

    config = _config(max_concurrent_queries=2, max_queued_queries=8)
    lock = threading.Lock()
    inflight = 0
    peak = 0
    release = threading.Event()

    def _job(handle: DuckDBAbortHandle) -> None:
        nonlocal inflight, peak
        del handle
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        release.wait(timeout=5)
        with lock:
            inflight -= 1

    tasks = [asyncio.create_task(run_duckdb_job(_job, config=config, operation="query")) for _ in range(8)]
    await asyncio.sleep(0.2)
    assert peak <= 2
    release.set()
    await asyncio.gather(*tasks)
    assert peak == 2


@pytest.mark.asyncio
async def test_requests_beyond_the_queue_depth_are_rejected_without_starting_a_job():
    """AC: overload is rejected as capacity (503), and no worker is started for it."""

    config = _config(max_concurrent_queries=1, max_queued_queries=1)
    started = 0
    release = threading.Event()

    def _job(handle: DuckDBAbortHandle) -> None:
        nonlocal started
        del handle
        started += 1
        release.wait(timeout=5)

    accepted = [asyncio.create_task(run_duckdb_job(_job, config=config, operation="query")) for _ in range(2)]
    await asyncio.sleep(0.1)

    with pytest.raises(TabularCapacityExceededError):
        await run_duckdb_job(_job, config=config, operation="query")

    assert started == 1, "the rejected request must not have started a DuckDB worker"
    release.set()
    await asyncio.gather(*accepted)
    assert started == 2


@pytest.mark.asyncio
async def test_rejected_request_does_not_leak_a_slot():
    """A 503 must not consume capacity, or the feature would wedge under load."""

    config = _config(max_concurrent_queries=1, max_queued_queries=0)
    release = threading.Event()

    def _blocking(handle: DuckDBAbortHandle) -> str:
        del handle
        release.wait(timeout=5)
        return "first"

    first = asyncio.create_task(run_duckdb_job(_blocking, config=config, operation="query"))
    await asyncio.sleep(0.05)
    for _ in range(5):
        with pytest.raises(TabularCapacityExceededError):
            await run_duckdb_job(_blocking, config=config, operation="query")
    release.set()
    assert await first == "first"

    # After the blocking job drained, capacity is back — the five rejections
    # released nothing they never took.
    assert await run_duckdb_job(lambda handle: "second", config=config, operation="query") == "second"


@pytest.mark.asyncio
async def test_execution_timeout_interrupts_the_query_and_closes_the_connection():
    """AC: wall time is bounded and the underlying DuckDB work is actually aborted."""

    config = _config(query_timeout_seconds=0.3, max_concurrent_queries=1, max_queued_queries=0)
    observed: dict[str, object] = {}
    finished = threading.Event()

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=config)
        try:
            connection.execute("SELECT count(*) FROM range(50000000000) t1").fetchone()
            observed["outcome"] = "completed"
        except duckdb.InterruptException:
            observed["outcome"] = "interrupted"
        finally:
            close_duckdb_connection(handle, connection)
            try:
                connection.execute("SELECT 1")
                observed["closed"] = False
            except duckdb.Error:
                observed["closed"] = True
            finished.set()

    started_at = time.perf_counter()
    with pytest.raises(TabularExecutionTimeoutError):
        await run_duckdb_job(_job, config=config, operation="query")
    elapsed = time.perf_counter() - started_at

    assert elapsed < 3, "the caller must not wait for the runaway query to finish"
    assert finished.wait(timeout=5), "the worker must actually terminate, not run on"
    assert observed["outcome"] == "interrupted"
    assert observed["closed"] is True


@pytest.mark.asyncio
async def test_slot_is_released_after_a_timeout_so_capacity_recovers():
    config = _config(query_timeout_seconds=0.2, max_concurrent_queries=1, max_queued_queries=0)

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=config)
        try:
            connection.execute("SELECT count(*) FROM range(50000000000) t1").fetchone()
        except duckdb.InterruptException:
            pass
        finally:
            close_duckdb_connection(handle, connection)

    with pytest.raises(TabularExecutionTimeoutError):
        await run_duckdb_job(_job, config=config, operation="query")

    for _ in range(50):
        try:
            assert await run_duckdb_job(lambda handle: "ok", config=config, operation="query") == "ok"
            return
        except TabularCapacityExceededError:
            await asyncio.sleep(0.05)
    pytest.fail("capacity never recovered after a timeout")


@pytest.mark.asyncio
async def test_caller_cancellation_aborts_the_worker_and_reraises():
    """A disconnecting client must not leave DuckDB work running unattended."""

    config = _config(query_timeout_seconds=30.0, max_concurrent_queries=1, max_queued_queries=0)
    finished = threading.Event()
    outcome: dict[str, object] = {}

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=config)
        try:
            connection.execute("SELECT count(*) FROM range(50000000000) t1").fetchone()
            outcome["result"] = "completed"
        except duckdb.InterruptException:
            outcome["result"] = "interrupted"
        finally:
            close_duckdb_connection(handle, connection)
            finished.set()

    task = asyncio.create_task(run_duckdb_job(_job, config=config, operation="query"))
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished.wait(timeout=5)
    assert outcome["result"] == "interrupted"


@pytest.mark.asyncio
async def test_abort_before_the_query_starts_still_stops_the_worker():
    """`interrupt()` is a no-op between statements, so the flag must be checked too."""

    handle = DuckDBAbortHandle()
    handle.request_abort()

    config = _config()
    with pytest.raises(Exception) as excinfo:
        connection = open_duckdb_connection(handle, config=config)
        close_duckdb_connection(handle, connection)
    assert type(excinfo.value).__name__ == "_AbortRequested"


@pytest.mark.asyncio
async def test_abort_after_close_does_not_raise():
    """A late abort must not blow up on an already-closed connection."""

    handle = DuckDBAbortHandle()
    connection = open_duckdb_connection(handle, config=_config())
    close_duckdb_connection(handle, connection)

    handle.request_abort()  # must be a no-op, not duckdb.ConnectionException


@pytest.mark.asyncio
async def test_job_runs_entirely_on_one_dedicated_pool_thread():
    """AC: one connection is created, used and closed on the same worker thread."""

    seen: list[str] = []

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=_config())
        try:
            seen.append(threading.current_thread().name)
            connection.execute("SELECT 1").fetchone()
            seen.append(threading.current_thread().name)
        finally:
            close_duckdb_connection(handle, connection)
            seen.append(threading.current_thread().name)

    loop_thread = threading.current_thread().name
    await run_duckdb_job(_job, config=_config(), operation="query")

    assert len(set(seen)) == 1, f"connection crossed threads: {seen}"
    assert seen[0] != loop_thread
    assert seen[0].startswith("tabular-duckdb"), "must use the dedicated pool, not the shared default executor"


@pytest.mark.asyncio
async def test_job_exceptions_propagate_unchanged_and_release_the_slot():
    config = _config(max_concurrent_queries=1, max_queued_queries=0)

    def _boom(handle: DuckDBAbortHandle) -> None:
        del handle
        raise ValueError("bad sql")

    for _ in range(3):
        with pytest.raises(ValueError, match="bad sql"):
            await run_duckdb_job(_boom, config=config, operation="query")

    assert await run_duckdb_job(lambda handle: "ok", config=config, operation="query") == "ok"


@pytest.mark.asyncio
async def test_connection_is_closed_when_configuration_fails():
    """An error between connect() and bind() must not orphan a DuckDB instance."""

    # model_construct bypasses the pattern check to simulate a value DuckDB
    # itself rejects, which is what would happen if the SET statements changed.
    broken = TabularQueryConfig.model_construct(duckdb_threads=1, duckdb_memory_limit="not-a-size")
    handle = DuckDBAbortHandle()

    with pytest.raises(duckdb.Error):
        open_duckdb_connection(handle, config=broken)

    # The handle never received a connection, so a later abort is inert rather
    # than reaching a connection nobody closed.
    handle.request_abort()


@pytest.mark.asyncio
async def test_duckdb_resource_limits_are_applied_to_every_connection():
    """AC: threads/memory_limit are set explicitly on every online connection."""

    config = _config(duckdb_threads=1, duckdb_memory_limit="256MB")
    settings: dict[str, object] = {}

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=config)
        try:
            row = connection.execute("SELECT current_setting('threads'), current_setting('memory_limit'), current_setting('temp_directory')").fetchone()
            assert row is not None
            settings["threads"], settings["memory_limit"], settings["temp_directory"] = row
        finally:
            close_duckdb_connection(handle, connection)

    await run_duckdb_job(_job, config=config, operation="query")

    assert settings["threads"] == 1
    assert "244" in str(settings["memory_limit"])  # DuckDB reports 256MB as 244.1 MiB
    assert settings["temp_directory"] == ""


@pytest.mark.asyncio
async def test_spilling_is_disabled_so_the_memory_limit_is_a_real_ceiling():
    """`memory_limit` alone does not bound anything: DuckDB spills to disk instead."""

    config = _config(duckdb_threads=1, duckdb_memory_limit="256MB")

    def _job(handle: DuckDBAbortHandle) -> str:
        connection = open_duckdb_connection(handle, config=config)
        try:
            connection.execute("SELECT count(*) FROM (SELECT i, repeat('y', 200) p FROM range(6000000) t(i) ORDER BY p, i)").fetchone()
            return "completed"
        except duckdb.OutOfMemoryException:
            return "bounded"
        finally:
            close_duckdb_connection(handle, connection)

    assert await run_duckdb_job(_job, config=config, operation="query") == "bounded"


@pytest.mark.asyncio
async def test_abort_is_reissued_so_it_cannot_be_swallowed():
    """
    DuckDB clears its interrupt flag when the next statement starts, so an abort
    landing between the worker's check and its `execute()` is lost and the
    runaway query would run to completion still holding its slot.
    """

    config = _config(query_timeout_seconds=0.2, max_concurrent_queries=1, max_queued_queries=0)
    outcome: dict[str, object] = {}
    finished = threading.Event()

    def _job(handle: DuckDBAbortHandle) -> None:
        connection = open_duckdb_connection(handle, config=config)
        try:
            # Emulate the lost-abort window: the worker passes its abort check,
            # then stalls before executing, so the first interrupt lands on an
            # idle connection and is erased.
            handle.raise_if_aborted()
            time.sleep(0.35)
            try:
                connection.execute("SELECT count(*) FROM range(50000000000) t1").fetchone()
                outcome["result"] = "ran to completion"
            except duckdb.InterruptException:
                outcome["result"] = "interrupted"
        finally:
            close_duckdb_connection(handle, connection)
            finished.set()

    with pytest.raises(TabularExecutionTimeoutError):
        await run_duckdb_job(_job, config=config, operation="query")

    # Let the scheduled retries fire on the loop.
    for _ in range(40):
        if finished.is_set():
            break
        await asyncio.sleep(0.05)

    assert finished.wait(timeout=5)
    assert outcome["result"] == "interrupted", "a re-issued abort must catch the query once it starts"


@pytest.mark.asyncio
async def test_a_job_that_never_started_is_reported_as_overload_not_timeout():
    """
    Queue time counts against the execution budget, so a request can exhaust it
    without ever running. Reporting that as 504 would send an operator hunting
    for a slow query that never executed; the real cause is saturation.
    """

    # Same (max_concurrent, max_queued) so both share one pool, but the blocker
    # gets a generous budget: only the queued request should run out of time.
    blocking_config = _config(max_concurrent_queries=1, max_queued_queries=4, query_timeout_seconds=10.0)
    queued_config = _config(max_concurrent_queries=1, max_queued_queries=4, query_timeout_seconds=0.3)
    release = threading.Event()

    def _job(handle: DuckDBAbortHandle) -> str:
        del handle
        release.wait(timeout=5)
        return "done"

    blocker = asyncio.create_task(run_duckdb_job(_job, config=blocking_config, operation="query"))
    await asyncio.sleep(0.05)

    # This one can never get a thread before its budget elapses.
    with pytest.raises(TabularCapacityExceededError):
        await run_duckdb_job(_job, config=queued_config, operation="query")

    release.set()
    assert await blocker == "done"


@pytest.mark.asyncio
async def test_a_timeout_raised_by_the_job_itself_is_not_relabelled_as_a_budget_expiry():
    """`socket.timeout is TimeoutError`, and network I/O now runs inside the job."""

    config = _config(query_timeout_seconds=30.0, max_concurrent_queries=1, max_queued_queries=0)

    def _job(handle: DuckDBAbortHandle) -> None:
        del handle
        raise TimeoutError("object store read timed out")

    with pytest.raises(TimeoutError) as excinfo:
        await run_duckdb_job(_job, config=config, operation="query")

    assert not isinstance(excinfo.value, TabularExecutionTimeoutError)
    assert "object store read timed out" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_job_finishing_at_the_deadline_returns_its_result_not_a_timeout():
    """
    The worker can set its result in the very loop iteration the budget expires.
    Discarding it would turn a query that succeeded into a 500 — the exact
    "reads as an outage" failure this guard exists to remove.
    """

    config = _config(query_timeout_seconds=0.05, max_concurrent_queries=1, max_queued_queries=0)

    def _job(_handle: DuckDBAbortHandle) -> str:
        time.sleep(0.10)
        return "ROWS"

    async def _block_the_loop() -> None:
        # Blocking the loop is precisely the condition #2182 is about, and it is
        # what lets the worker finish before the timer callback gets to run.
        time.sleep(0.30)

    task = asyncio.create_task(run_duckdb_job(_job, config=config, operation="query"))
    await asyncio.sleep(0)
    await _block_the_loop()

    assert await task == "ROWS"


@pytest.mark.asyncio
async def test_a_job_raising_at_the_deadline_surfaces_its_own_error():
    """The same window must not relabel a job's own failure as a budget expiry."""

    config = _config(query_timeout_seconds=0.05, max_concurrent_queries=1, max_queued_queries=0)

    def _job(_handle: DuckDBAbortHandle) -> str:
        time.sleep(0.10)
        raise ValueError("bad sql")

    task = asyncio.create_task(run_duckdb_job(_job, config=config, operation="query"))
    await asyncio.sleep(0)
    time.sleep(0.30)

    with pytest.raises(ValueError, match="bad sql"):
        await task
