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
Bounded, interruptible execution of synchronous DuckDB work for the tabular feature.

Why this module exists:
- `TabularService` runs DuckDB inside `async def` route handlers that are also
  exported as MCP tools, so one caller could block the event loop and exhaust
  CPU/memory for the whole pod. The guard below moves that work onto a dedicated
  thread pool, bounds how much of it runs at once, bounds how long it may run,
  and gives the loop a way to abort a job it is no longer waiting for.
- It lives in its own module rather than in `service.py` because that file is
  already ~1200 lines and concurrency/abort orchestration is a separate concern
  (see `docs/swift/platform/DEVELOPER_CONTRACT.md` §4).

How to use:
- Write the whole logical operation as one synchronous `job(handle)` callable:
  open the connection with `open_duckdb_connection`, call
  `handle.raise_if_aborted()` at each safe point, and always finish with
  `close_duckdb_connection` in a `finally`. Then `await run_duckdb_job(job, ...)`.
- Never split one operation across two jobs, and never create the DuckDB
  connection outside the job: a connection must be created, used and closed on
  the one thread that owns it.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

import duckdb
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from knowledge_flow_backend.common.structures import TabularQueryConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")

# DuckDB does not fail when it reaches `memory_limit`: it spills the over-budget
# operator to disk and completes. Measured on 1.5.4 — a sort over 6M rows with
# memory_limit='256MB' writes its blocks to the working directory and succeeds,
# so the limit bounds nothing on its own and merely converts a memory problem
# into an ephemeral-storage one (kubelet eviction, or ENOSPC breaking ingestion,
# which shares the filesystem). An empty temp directory disables spilling, so an
# over-budget query raises OutOfMemoryException instead. Deliberately a constant
# and not a config field: a deployment that wants tabular queries to spill wants
# a different feature, not a different value.
_TEMP_DIRECTORY = ""

# `interrupt()` only aborts a statement that is already executing, and DuckDB
# clears the interrupt flag when the next statement starts. So an abort landing
# in the gap between a worker's `raise_if_aborted()` check and its `execute()`
# call is swallowed, and the runaway query then runs to completion holding its
# execution slot. Re-issuing the abort a few times closes that gap: whichever
# attempt lands while the statement is actually running takes effect. Each
# repeat is a no-op once the worker has released its connection.
_ABORT_RETRY_ATTEMPTS = 5
_ABORT_RETRY_INTERVAL_SECONDS = 0.1


class TabularCapacityExceededError(RuntimeError):
    """
    Raised when no DuckDB execution slot is available for a new tabular request.

    Why this exists:
    - Concurrency is bounded per process, so requests beyond the bound must fail
      fast and explicitly rather than queue without limit behind a busy pod.
    - It maps to HTTP 503, matching how this codebase already signals
      "temporarily unavailable, retry" — distinct from a 504 timeout, so an
      operator can tell overload from a slow query.

    How to use:
    - Let the tabular controller map it to 503; do not catch it in the service.
    """


class TabularExecutionTimeoutError(RuntimeError):
    """
    Raised when one DuckDB job exceeds its configured wall-clock budget.

    Why this exists:
    - An unbounded query pins CPU and its execution slot indefinitely. The
      orchestrator gives up at `query_timeout_seconds` and asks the worker to
      abort, so the caller gets a bounded answer.
    - It maps to HTTP 504, kept distinct from the 503 above.

    How to use:
    - Let the tabular controller map it to 504.
    - Note the abort is best-effort for work blocked on network I/O: DuckDB's
      `interrupt()` aborts query execution promptly but cannot unblock a socket
      read inside `httpfs`. The execution slot is released when the worker
      thread actually returns, never before.
    """


class _AbortRequested(Exception):
    """
    Internal signal raised inside a worker thread once an abort was requested.

    Why this exists:
    - `connection.interrupt()` only aborts a statement that is currently
      executing; it is a no-op between statements. A worker must therefore also
      check an explicit flag at each safe point, and needs one exception type to
      unwind with.

    How to use:
    - Never surfaced to callers: the orchestrator has already raised
      `TabularExecutionTimeoutError` or propagated `CancelledError` by the time
      this unwinds, and the worker's exception is discarded.
    """


class DuckDBAbortHandle:
    """
    Cross-thread abort channel between the event loop and one DuckDB worker.

    Why this exists:
    - The loop must be able to stop work it is no longer waiting for (timeout or
      client disconnect) without touching the connection from its own thread —
      `close()` from another thread blocks for the whole duration of in-flight
      I/O, which would re-block the loop this fix exists to protect.
    - One lock guards the connection and the flag together, so an abort can
      never land on a connection the worker has already closed (which raises
      `duckdb.ConnectionException`).

    How to use:
    - The worker calls `bind` right after connecting, `raise_if_aborted` at each
      safe point, and `release` before closing.
    - The loop calls `request_abort`, which never raises and never blocks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._aborted = False

    def bind(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Publish the live connection, or raise when an abort already arrived."""

        with self._lock:
            if self._aborted:
                raise _AbortRequested()
            self._connection = connection

    def release(self) -> None:
        """Detach the connection so a later abort cannot touch it. Idempotent."""

        with self._lock:
            self._connection = None

    def raise_if_aborted(self) -> None:
        """Abort the worker at a safe point when the loop has given up."""

        with self._lock:
            if self._aborted:
                raise _AbortRequested()

    def request_abort(self) -> None:
        """
        Ask the worker to stop. Safe to call from the event loop, never raises.

        The interrupt is issued under the lock because it is non-blocking
        (sub-millisecond) and because holding the lock is what guarantees the
        worker cannot close the connection underneath it.
        """

        with self._lock:
            self._aborted = True
            connection = self._connection
            if connection is None:
                return
            try:
                connection.interrupt()
            except duckdb.Error as exc:  # pragma: no cover - defensive
                logger.debug("[TABULAR] interrupt on an unusable DuckDB connection: %s", exc)


class _TabularExecutionGuard:
    """
    Process-wide bound on concurrent DuckDB work, shared by every service instance.

    Why this exists:
    - `TabularService` is not a singleton: the tabular controller builds one and
      `ContentService` builds another, so per-instance state would multiply the
      configured bound by the number of live instances and fail open under load.
    - Both primitives are `threading` objects rather than asyncio ones, so no
      state is bound to an event loop. That matters because the test suite runs
      one loop per test, and a module-level `asyncio.Semaphore` raises
      "bound to a different event loop" as soon as a second test contends on it.

    How to use:
    - Internal. Reach it through `run_duckdb_job`; call
      `reset_execution_state_for_tests()` between tests that change the config.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._permits: threading.BoundedSemaphore | None = None
        self._key: tuple[int, int] | None = None

    def acquire(self, config: TabularQueryConfig) -> tuple[ThreadPoolExecutor, threading.BoundedSemaphore]:
        """Return the pool and the admission counter, rebuilding them on a config change."""

        key = (config.max_concurrent_queries, config.max_queued_queries)
        with self._lock:
            if self._key != key or self._executor is None or self._permits is None:
                previous = self._executor
                self._executor = ThreadPoolExecutor(
                    max_workers=config.max_concurrent_queries,
                    thread_name_prefix="tabular-duckdb",
                )
                self._permits = threading.BoundedSemaphore(config.max_concurrent_queries + config.max_queued_queries)
                self._key = key
                if previous is not None:
                    previous.shutdown(wait=False)
            return self._executor, self._permits

    def reset(self) -> None:
        """Drop the pool and the counter so the next call rebuilds them."""

        with self._lock:
            previous = self._executor
            self._executor = None
            self._permits = None
            self._key = None
        if previous is not None:
            previous.shutdown(wait=False)


_GUARD = _TabularExecutionGuard()


def reset_execution_state_for_tests() -> None:
    """
    Drop the process-wide pool and admission counter.

    Why this exists:
    - The guard is sized from configuration on first use and then reused for the
      process lifetime, which is right in production and wrong in a test suite
      that rebuilds `ApplicationContext` with different limits per test.

    How to use:
    - Call from a pytest fixture before a test that changes tabular query
      configuration. Never call it from application code.
    """

    _GUARD.reset()


def open_duckdb_connection(handle: DuckDBAbortHandle, *, config: TabularQueryConfig) -> duckdb.DuckDBPyConnection:
    """
    Open one resource-bounded in-memory DuckDB connection inside a worker thread.

    Why this exists:
    - DuckDB auto-detects threads and memory from the host, not from the
      container's cgroup, so every connection must be told its budget explicitly.
    - Binding the connection to the abort handle has to happen while the
      connection is still guarded by this function's cleanup, otherwise an abort
      arriving between `connect()` and `bind()` would orphan an open connection.

    How to use:
    - Call as the first statement of a job, and pair it with
      `close_duckdb_connection` in that job's `finally`.

    Example:
    ```python
    connection = open_duckdb_connection(handle, config=query_config)
    try:
        ...
    finally:
        close_duckdb_connection(handle, connection)
    ```
    """

    connection = duckdb.connect(database=":memory:")
    try:
        # Machine-built from validated config values, never from caller text:
        # duckdb_threads is an int and duckdb_memory_limit is pattern-checked.
        connection.execute(f"SET threads={int(config.duckdb_threads)}")
        connection.execute(f"SET memory_limit='{config.duckdb_memory_limit}'")
        connection.execute(f"SET temp_directory='{_TEMP_DIRECTORY}'")
        handle.bind(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def close_duckdb_connection(handle: DuckDBAbortHandle, connection: duckdb.DuckDBPyConnection) -> None:
    """
    Detach the connection from the abort handle, then close it.

    Why this exists:
    - Releasing before closing is what makes a late `request_abort()` from the
      loop a no-op instead of a `duckdb.ConnectionException` on a closed handle.

    How to use:
    - Call in the `finally` of every job that opened a connection.
    """

    handle.release()
    connection.close()


def register_tabular_exception_handlers(app: FastAPI) -> None:
    """
    Map the two execution-guard errors to their HTTP statuses, once, app-wide.

    Why this exists:
    - The guard wraps a helper (`_load_dataset_frame`) reached from several
      features, not just the tabular routes: the document-preview route, the
      summarize service, and the corpus virtual filesystem all render CSV
      previews through it. Mapping per route was tried and silently missed two
      of those callers, so a saturated pod answered an ordinary summarize
      request with a 500 and made corpus grep skip CSV documents without a
      signal. One registration covers every present and future caller.
    - Registering app-wide is safe here specifically because both types are
      narrow and purpose-built, with exactly one meaning each. Do not extend
      this to broad builtins — an app-wide handler for a type like `ValueError`
      changes the status of unrelated failures across the whole service.

    How to use:
    - Call once from `create_app`, next to `register_exception_handlers(app)`.
      Tests that build their own `FastAPI` app must call it too.
    """

    @app.exception_handler(TabularCapacityExceededError)
    async def _capacity_exceeded(_request: Request, exc: TabularCapacityExceededError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(TabularExecutionTimeoutError)
    async def _execution_timeout(_request: Request, exc: TabularExecutionTimeoutError) -> JSONResponse:
        return JSONResponse(status_code=504, content={"detail": str(exc)})


def _abort_repeatedly(handle: DuckDBAbortHandle, attempts: int = _ABORT_RETRY_ATTEMPTS) -> None:
    """
    Abort one worker, re-issuing the interrupt so it cannot be swallowed.

    Why this exists:
    - See `_ABORT_RETRY_ATTEMPTS`: a single `interrupt()` is lost when it lands
      between the worker's abort check and the start of its next statement.

    How to use:
    - Call from the event loop instead of `handle.request_abort()` directly.
      Never blocks: the repeats are scheduled on the loop, not awaited.
    """

    handle.request_abort()
    if attempts <= 1:
        return
    try:
        asyncio.get_running_loop().call_later(_ABORT_RETRY_INTERVAL_SECONDS, _abort_repeatedly, handle, attempts - 1)
    except RuntimeError:  # pragma: no cover - loop already closed, nothing left to abort
        pass


async def run_duckdb_job(
    job: Callable[[DuckDBAbortHandle], T],
    *,
    config: TabularQueryConfig,
    operation: str,
) -> T:
    """
    Run one synchronous DuckDB operation off the event loop, bounded and abortable.

    Why this exists:
    - This is the single place that enforces the tabular execution contract:
      admission control, a dedicated thread pool, a wall-clock budget, and abort
      on timeout or client disconnect.

    How to use:
    - Pass a callable that performs the whole operation and returns its result;
      it receives the abort handle. `operation` is a low-cardinality label
      (`query`, `search`, `preview`) used only for logging.
    - Raises `TabularCapacityExceededError` (503) when the process is saturated
      and `TabularExecutionTimeoutError` (504) when the budget elapses; any
      exception raised by the job itself propagates unchanged.

    Example:
    ```python
    rows = await run_duckdb_job(_read_rows, config=query_config, operation="query")
    ```
    """

    executor, permits = _GUARD.acquire(config)

    # Non-blocking on purpose: burst absorption is `max_queued_queries` worth of
    # pool queue, so there is no second waiting mechanism to tune here, and the
    # event loop never waits for a slot.
    if not permits.acquire(blocking=False):
        logger.warning("[TABULAR] %s rejected: no execution slot available", operation)
        raise TabularCapacityExceededError("Tabular query capacity is saturated; retry shortly.")

    handle = DuckDBAbortHandle()
    # Set by the pool thread the instant it picks the job up. The budget clock
    # starts at submit, so a job can burn all of it queued behind others and
    # never run; this flag is what tells "saturated" (503) apart from "slow
    # query" (504) afterwards. A plain Event rather than the future's own state:
    # a queued future is not reliably reported as cancelled once wait_for has
    # unwound, so its state cannot answer the question.
    started = threading.Event()

    def _runner() -> T:
        started.set()
        return job(handle)

    try:
        # copy_context() keeps request-scoped context vars (logging correlation)
        # visible inside the worker, matching what asyncio.to_thread does.
        future = executor.submit(contextvars.copy_context().run, _runner)
    except BaseException:
        # submit() raises synchronously on a shut-down pool, before any callback
        # exists to release the permit.
        permits.release()
        raise

    # The single release point for the permit. It fires when the worker thread
    # actually finishes — including after a timeout, so a job that outlives its
    # caller still holds its slot until it truly ends.
    future.add_done_callback(lambda _future: permits.release())

    try:
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=config.query_timeout_seconds)
    except TimeoutError:
        # The worker can finish in the very loop iteration the budget expires —
        # its result is copied across before the timer callback runs, so the
        # future is already done. Honour that instead of discarding a completed
        # query: `result()` returns the rows, or re-raises whatever the job
        # itself raised (including a `socket.timeout`, which *is* `TimeoutError`
        # since 3.10 now that network I/O runs inside the job). Either way the
        # answer is the job's, not a budget expiry.
        if future.done() and not future.cancelled():
            return future.result()
        # Abort first, unconditionally. The pool marks a future RUNNING before
        # the worker reaches `started.set()`, so a job dispatched at exactly the
        # wrong instant looks un-started here; without this it would keep its
        # slot with nothing left to stop it.
        _abort_repeatedly(handle)
        if not started.is_set():
            # It never got a thread: it burned its budget queued behind other
            # jobs. That is overload (503), not a slow query (504) — reporting
            # 504 would send an operator hunting for a slow query that never
            # ran, and collapse the very distinction this guard exists to keep.
            logger.warning("[TABULAR] %s rejected: queued past the %.1fs budget without starting", operation, config.query_timeout_seconds)
            raise TabularCapacityExceededError("Tabular query capacity is saturated; retry shortly.") from None
        logger.warning("[TABULAR] %s aborted after %.1fs execution budget", operation, config.query_timeout_seconds)
        raise TabularExecutionTimeoutError(f"Tabular {operation} exceeded the {config.query_timeout_seconds:g}s execution budget.") from None
    except asyncio.CancelledError:
        _abort_repeatedly(handle)
        raise
