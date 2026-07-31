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
        pass
    return -1


def _debug_gc_and_trim() -> None:
    """SIGUSR1 handler: force a full GC cycle, then return freed pymalloc arenas
    to the OS via glibc's malloc_trim(0) — CPython's allocator does NOT do this on
    its own, so a `gc.collect()` alone can look like a no-op from `kubectl top`
    even when it genuinely freed Python objects.

    Diagnostic only, no scheduled/automatic trigger: run on demand from outside
    with `kubectl exec <pod> -- kill -USR1 1` while the worker is idle, then watch
    `kubectl top pod` / this log line. RSS drops after this -> reference-cycle
    garbage (needs a real gc.collect(), plain refcounting never freed it) or
    allocator-held-but-unused arenas. RSS unchanged -> either something still
    holds a real reference (a genuine leak, not just uncollected cycles) or the
    memory is native (e.g. onnxruntime/docling), outside gc's and malloc_trim's
    reach entirely.
    """
    before_kb = _current_rss_kb()
    objects_before = len(gc.get_objects())
    collected = gc.collect()
    uncollectable = len(gc.garbage)
    objects_after = len(gc.get_objects())

    trimmed = False
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        trimmed = True
    except OSError:
        logger.warning("[DEBUG][GC] malloc_trim unavailable (not glibc?) — RSS reading below only reflects gc.collect()")

    after_kb = _current_rss_kb()
    logger.warning(
        "[DEBUG][GC] SIGUSR1: gc.collect()=%d freed, %d uncollectable in gc.garbage, "
        "objects %d -> %d, malloc_trim=%s | RSS %dKi -> %dKi (delta %dKi)",
        collected,
        uncollectable,
        objects_before,
        objects_after,
        trimmed,
        before_kb,
        after_kb,
        before_kb - after_kb,
    )


def _debug_gc_types(top_n: int = 20) -> None:
    """SIGUSR2 handler: same idea as _debug_gc_and_trim (SIGUSR1), but reports WHICH
    object types make up the reference-cycle garbage instead of just a count — the
    piece ISSUE-009 left open (cycles confirmed real via 0-uncollectable SIGUSR1
    tests, never identified what they're made of).

    gc.DEBUG_SAVEALL makes gc.collect() keep collected-but-cyclic objects reachable
    via gc.garbage instead of destroying them immediately, just for this one
    collection, so their types can be inspected before release. gc.garbage is
    cleared explicitly afterward (dropping our references) and a second plain
    gc.collect() actually frees them — otherwise they'd stay pinned in gc.garbage
    forever, a leak of our own making. Heavier than SIGUSR1 (the type-counting pass
    itself), so kept as an explicit separate signal rather than folded into the
    periodic task.
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

    trimmed = False
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        trimmed = True
    except OSError:
        pass

    after_kb = _current_rss_kb()
    logger.warning(
        "[DEBUG][GC] SIGUSR2 type breakdown: gc.collect()=%d, %d objects held in gc.garbage "
        "for inspection then released (+%d freed on the follow-up collect), malloc_trim=%s | "
        "RSS %dKi -> %dKi | top types: %s",
        collected,
        garbage_count,
        freed_after_clear,
        trimmed,
        before_kb,
        after_kb,
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


async def _periodic_gc_and_trim(interval_s: float) -> None:
    """Call _debug_gc_and_trim on a fixed interval instead of waiting for a manual
    SIGUSR1. Mitigation for the reference-cycle growth confirmed live on fredlab
    2026-07-31 (ISSUE-009): repeated SIGUSR1 triggers freed real memory every time
    (0 uncollectable in gc.garbage — genuine cycles, not a hard leak), scaling with
    document volume (1930 objects/~260MB freed after ~1 doc, 8803 objects/~1.65GB
    after ~30 docs across two batches). Runs regardless of whether the worker is
    currently busy — gc.collect()'s own cost is small next to a PDF conversion, and
    waiting for "idle" would need tracking activity concurrency this module doesn't
    have visibility into today.
    """
    while True:
        await asyncio.sleep(interval_s)
        _debug_gc_and_trim()


def _start_periodic_gc_task() -> list[asyncio.Task[None]]:
    """Opt-in via KF_WORKER_GC_INTERVAL_SEC (seconds; unset or <=0 disables — matches
    the interval-driven KPI tasks' own on/off convention above). Env var rather than
    YAML: this is a deployment-level mitigation knob, not product configuration —
    same category as FRED_MODELS_CATALOG_FILE, not app.* config."""
    raw = os.environ.get("KF_WORKER_GC_INTERVAL_SEC", "0")
    try:
        interval_s = float(raw)
    except ValueError:
        logger.warning("[DEBUG][GC] Invalid KF_WORKER_GC_INTERVAL_SEC=%r, ignoring (periodic GC disabled)", raw)
        return []
    if interval_s <= 0:
        return []
    logger.warning("[DEBUG][GC] Periodic gc.collect()+malloc_trim() enabled every %.0fs (KF_WORKER_GC_INTERVAL_SEC)", interval_s)
    return [asyncio.create_task(_periodic_gc_and_trim(interval_s))]


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

    # Manual triggers always available regardless of KF_WORKER_GC_INTERVAL_SEC below:
    # `kubectl exec <pod> -- kill -USR1 1` to force gc.collect() + malloc_trim(0) and
    # log the RSS delta on demand (see _debug_gc_and_trim's docstring); `kill -USR2 1`
    # for the heavier type-breakdown variant (see _debug_gc_types's docstring).
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGUSR1, _debug_gc_and_trim)
    loop.add_signal_handler(signal.SIGUSR2, _debug_gc_types)

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
