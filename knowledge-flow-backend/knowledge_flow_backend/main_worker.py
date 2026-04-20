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
import logging
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


def _start_worker_kpi_tasks(configuration, app_context: ApplicationContext) -> list[asyncio.Task[None]]:
    """
    Start optional worker-side KPI tasks from the YAML configuration.

    Why:
        `kpi_process_metrics_interval_sec` should affect worker processes too, not
        only the API process, so worker KPI settings are consistent across runtime entrypoints.
    How:
        When the configured interval is positive, create background tasks for
        process KPIs and shared SQL pool KPIs and return them for shutdown cleanup.
    """
    interval_s = float(configuration.app.kpi_process_metrics_interval_sec)
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
    if configuration.app.metrics_enabled:
        start_http_server(
            configuration.app.metrics_port,
            addr=configuration.app.metrics_address,
        )
    kpi_tasks = _start_worker_kpi_tasks(configuration, app_context)

    try:
        await run_worker(
            configuration.scheduler.temporal,
            max_concurrent_workflow_tasks=configuration.scheduler.temporal.ingestion_max_concurrent_workflow_tasks,
            max_concurrent_activities=configuration.scheduler.temporal.ingestion_max_concurrent_activities,
        )
    finally:
        for task in kpi_tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    logger.error("Background KPI task %r failed during shutdown", task, exc_info=exc)
        await app_context.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
