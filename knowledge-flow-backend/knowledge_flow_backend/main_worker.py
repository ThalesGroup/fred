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

from fred_core.scheduler import SchedulerBackend

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.config_loader import (
    get_loaded_config_file_path,
    get_loaded_env_file_path,
    load_configuration,
)
from knowledge_flow_backend.features.scheduler.worker import run_worker

logger = logging.getLogger(__name__)


async def main() -> None:
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

    await run_worker(configuration.scheduler.temporal)


if __name__ == "__main__":
    asyncio.run(main())
