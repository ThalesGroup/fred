# Copyright Thales 2025
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

"""
Entrypoint for the Knowledge Flow Temporal worker.

Start with:
  CONFIG_FILE=./config/configuration.yaml uv run python -m knowledge_flow_backend.main_worker
"""

import asyncio
import ctypes
import gc
import logging
import os
import signal
from collections import Counter
from contextlib import suppress

from fred_core.kpi import emit_process_kpis, emit_sql_pool_kpis
from fred_core.scheduler import SchedulerBackend
from prometheus_client import start_http_server

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from knowledge_flow_backend.features.scheduler.worker import run_worker

logger = logging.getLogger(__name__)


def _current_rss_kb() -> int:
    """Current resident set size, in KiB — unlike resource.getrusage().ru_maxrss
    (peak since process start, never decreases), this reflects the process's
    actual memory right now."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass  # /proc unavailable (non-Linux) — -1 tells callers "unknown", not "zero"
    return -1


def _format_rss_delta(before_kb: int, after_kb: int) -> str:
    """Render an RSS before->after pair for logging. Guards against `_current_rss_kb()`'s
    -1 "unknown" sentinel producing a misleading delta (e.g. `-1Ki -> 1234Ki` looking
    like a 1235Ki drop)."""
    if before_kb < 0 or after_kb < 0:
        return f"{before_kb}Ki -> {after_kb}Ki (delta unknown, /proc unreadable)"
    return f"{before_kb}Ki -> {after_kb}Ki (delta {before_kb - after_kb}Ki)"


def _malloc_trim() -> bool:
    """Return freed pymalloc arenas to the OS (glibc-only). CPython's allocator
    doesn't do this on its own, so gc.collect() alone can look like a no-op from
    `kubectl top` even after genuinely freeing objects."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        return True
    except OSError:
        return False


def _collect_and_trim(label: str) -> None:
    """Force a full GC cycle + malloc_trim(0), log the RSS delta. Manual trigger:
    `kubectl exec <pod> -- kill -USR1 1`; also the periodic mitigation task (see
    ISSUE-009). RSS drop -> reference-cycle garbage (plain refcounting never frees
    it) or reclaimed arenas. RSS unchanged -> either a real reference is still
    held, or the memory is native (onnxruntime/docling), outside gc's/malloc_trim's
    reach.
    """
    before_kb = _current_rss_kb()
    collected = gc.collect()
    uncollectable = len(gc.garbage)
    trimmed = _malloc_trim()
    after_kb = _current_rss_kb()
    logger.warning(
        "[GC][%s] collected=%d uncollectable=%d trimmed=%s RSS %s",
        label,
        collected,
        uncollectable,
        trimmed,
        _format_rss_delta(before_kb, after_kb),
    )


def _collect_and_report_types(top_n: int = 20) -> None:
    """SIGUSR2 handler: heavier variant of _collect_and_trim that reports WHICH
    object types make up the reference-cycle garbage, not just a count (ISSUE-010
    was found this way). gc.DEBUG_SAVEALL keeps this collection's cyclic garbage
    reachable via gc.garbage instead of destroying it immediately so its types can
    be inspected, then it's cleared and re-collected so nothing stays pinned.
    """
    before_kb = _current_rss_kb()
    old_flags = gc.get_debug()
    gc.set_debug(gc.DEBUG_SAVEALL)
    collected = gc.collect()
    gc.set_debug(old_flags)

    top_types = Counter(type(o).__name__ for o in gc.garbage).most_common(top_n)
    garbage_count = len(gc.garbage)
    gc.garbage.clear()
    freed_after_clear = gc.collect()
    trimmed = _malloc_trim()
    after_kb = _current_rss_kb()
    logger.warning(
        "[GC][SIGUSR2] collected=%d held_for_inspection=%d freed_after_clear=%d trimmed=%s RSS %s top_types=%s",
        collected,
        garbage_count,
        freed_after_clear,
        trimmed,
        _format_rss_delta(before_kb, after_kb),
        top_types,
    )


def _start_worker_kpi_tasks(configuration, app_context: ApplicationContext) -> list[asyncio.Task[None]]:
    """
    Start optional worker-side KPI tasks from the YAML configuration.

    Why:
        `process_metrics_interval_sec` should affect worker processes too, not
        only the API process, so worker KPI settings are consistent across runtime entrypoints.
    How:
        When the configured interval is positive, create background tasks for
        process KPIs and shared SQL pool KPIs and return them for shutdown cleanup.
    """
    interval_s = float(configuration.observability.kpi.process_metrics_interval_sec)
    if interval_s <= 0:
        return []

    kpi_writer = app_context.get_kpi_writer()
    return [
        asyncio.create_task(emit_process_kpis(interval_s, kpi_writer)),
        asyncio.create_task(
            emit_sql_pool_kpis(
                interval_s,
                kpi_writer,
                app_context.get_pg_async_engine(),
                pool_name="knowledge-flow-postgres",
            )
        ),
    ]


async def _periodic_gc_loop(interval_s: float) -> None:
    """Mitigation for the reference-cycle growth confirmed live on fredlab
    2026-07-31 (ISSUE-009, root-caused by ISSUE-010): runs unconditionally rather
    than only when idle — gc.collect()'s cost is small next to a PDF conversion,
    and this module has no visibility into activity concurrency to detect "idle".
    """
    while True:
        await asyncio.sleep(interval_s)
        _collect_and_trim("periodic")


def _start_periodic_gc_task() -> list[asyncio.Task[None]]:
    """Opt-in via KF_WORKER_GC_INTERVAL_SEC (seconds; unset or <=0 disables — matches
    the interval-driven KPI tasks' own on/off convention above). Env var rather than
    YAML: a deployment-level mitigation knob, not product configuration — same
    category as FRED_MODELS_CATALOG_FILE, not app.* config."""
    raw = os.environ.get("KF_WORKER_GC_INTERVAL_SEC", "0")
    try:
        interval_s = float(raw)
    except ValueError:
        logger.warning("[GC] Invalid KF_WORKER_GC_INTERVAL_SEC=%r, ignoring (periodic GC disabled)", raw)
        return []
    if interval_s <= 0:
        return []
    logger.warning("[GC] Periodic gc.collect()+malloc_trim() enabled every %.0fs (KF_WORKER_GC_INTERVAL_SEC)", interval_s)
    return [asyncio.create_task(_periodic_gc_loop(interval_s))]


async def main() -> None:
    """
    Run the Knowledge Flow Temporal worker with worker-side observability enabled.

    Why:
        Enabling worker metrics in configuration should have a real runtime effect,
        otherwise Helm and config changes would not expose any telemetry.
    How:
        Load the worker configuration, initialize the application context, start the
        optional Prometheus exporter and KPI background tasks, then run the Temporal worker.
    """
    configuration = load_configuration()
    ApplicationContext(configuration)
    app_context = ApplicationContext.get_instance()
    # Keep worker logging local-only: Temporal workflow sandbox must not trigger
    # external log sinks (OpenSearch/HTTP imports) from workflow threads.
    logging.basicConfig(
        level=getattr(logging, configuration.app.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | [pid=%(process)d %(threadName)s] | %(message)s",
    )
    env_file = get_loaded_env_file_path() or "<unset>"
    config_file = get_loaded_config_file_path() or "<unset>"
    logger.info("Environment file: %s | Configuration file: %s", env_file, config_file)

    # Manual triggers, always available regardless of KF_WORKER_GC_INTERVAL_SEC below:
    # `kubectl exec <pod> -- kill -USR1 1` / `-USR2 1`. See _collect_and_trim and
    # _collect_and_report_types. add_signal_handler is Unix-only and main-thread-only
    # (NotImplementedError / RuntimeError otherwise) — this is a diagnostic convenience,
    # not a requirement, so a platform/thread that can't register it just runs without it.
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGUSR1, lambda: _collect_and_trim("SIGUSR1"))
        loop.add_signal_handler(signal.SIGUSR2, _collect_and_report_types)
    except (NotImplementedError, RuntimeError) as exc:
        logger.warning("[GC] SIGUSR1/SIGUSR2 manual triggers unavailable on this platform/thread: %s", exc)

    if not configuration.scheduler.enabled:
        logger.warning("Scheduler disabled via configuration.scheduler.enabled=false")
        return
    scheduler_backend = app_context.get_scheduler_backend()
    if scheduler_backend == SchedulerBackend.MEMORY:
        logger.info("Scheduler backend is 'memory'; no Temporal worker is required.")
        return
    if scheduler_backend != SchedulerBackend.TEMPORAL:
        raise ValueError(f"Scheduler backend '{scheduler_backend}' not supported; expected 'temporal'.")

    # Unlike the API entrypoints, the Temporal worker has no FastAPI app to pass
    # to `Instrumentator().instrument(app)`. We still expose Prometheus metrics
    # on the dedicated metrics port using the same toggle and exporter startup.
    prom_cfg = configuration.observability.kpi.prometheus
    if prom_cfg.enabled:
        start_http_server(prom_cfg.port, addr=prom_cfg.address)
    kpi_tasks = _start_worker_kpi_tasks(configuration, app_context)
    gc_tasks = _start_periodic_gc_task()
    background_tasks = kpi_tasks + gc_tasks

    try:
        await run_worker(
            configuration.scheduler.temporal,
            max_concurrent_workflow_tasks=configuration.scheduler.temporal.ingestion_max_concurrent_workflow_tasks,
            max_concurrent_activities=configuration.scheduler.temporal.ingestion_max_concurrent_activities,
        )
    finally:
        for task in background_tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    logger.error("Background task %r failed during shutdown", task, exc_info=exc)
        await app_context.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
