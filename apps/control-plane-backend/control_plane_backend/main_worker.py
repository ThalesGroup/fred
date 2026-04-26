from __future__ import annotations

import asyncio
import logging

from fred_core import log_setup
from fred_core.logs.null_log_store import NullLogStore
from fred_core.scheduler import SchedulerBackend

from control_plane_backend.app.container import (
    build_application_container,
    initialize_shared_stores,
)
from control_plane_backend.config.loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from control_plane_backend.scheduler.dependencies import (
    build_lifecycle_action_dependencies,
)
from control_plane_backend.scheduler.temporal.worker import run_worker

logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Bootstrap and run the control-plane Temporal worker process.

    Why this function exists:
    - the worker needs one explicit startup path that loads configuration,
      initializes shared stores, and then dispatches to the scheduler backend

    How to use it:
    - call from the module `__main__` block or a process runner
    - rely on configuration to decide whether a Temporal worker is needed

    Example:
    - `asyncio.run(main())`
    """
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

    container = build_application_container(configuration)
    initialize_shared_stores(container)
    try:
        if not configuration.scheduler.enabled:
            logger.warning(
                "Scheduler disabled via configuration.scheduler.enabled=false"
            )
            return

        scheduler_backend = container.get_scheduler_backend()
        if scheduler_backend == SchedulerBackend.MEMORY:
            logger.info(
                "Scheduler backend is 'memory'; no Temporal worker is required."
            )
            return

        await run_worker(
            configuration.scheduler.temporal,
            build_lifecycle_action_dependencies(container),
        )
    finally:
        await container.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
