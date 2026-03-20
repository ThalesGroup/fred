from __future__ import annotations

import asyncio
import logging

from fred_core import log_setup
from fred_core.logs.null_log_store import NullLogStore
from fred_core.scheduler import SchedulerBackend

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.common.config_loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from control_plane_backend.scheduler.temporal.worker import run_worker

logger = logging.getLogger(__name__)


async def main() -> None:
    configuration = load_configuration()
    log_setup(
        service_name="control-plane-worker",
        log_level=configuration.app.log_level,
        store=NullLogStore(),
        use_rich=False,  # Temporal workflow sandbox disallows Rich imports.
    )

    env_file = get_loaded_env_file_path() or "<unset>"
    config_file = get_loaded_config_file_path() or "<unset>"
    logger.info("Environment file: %s | Configuration file: %s", env_file, config_file)

    ApplicationContext(configuration)

    if not configuration.scheduler.enabled:
        logger.warning("Scheduler disabled via configuration.scheduler.enabled=false")
        return

    scheduler_backend = ApplicationContext.get_instance().get_scheduler_backend()
    if scheduler_backend == SchedulerBackend.MEMORY:
        logger.info("Scheduler backend is 'memory'; no Temporal worker is required.")
        return

    await run_worker(
        configuration.scheduler.temporal,
    )


if __name__ == "__main__":
    asyncio.run(main())
