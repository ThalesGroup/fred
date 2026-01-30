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

from fred_core import log_setup

from knowledge_flow_backend.application_context import ApplicationContext, get_app_context
from knowledge_flow_backend.main import load_configuration
from knowledge_flow_backend.features.scheduler.worker import run_worker

logger = logging.getLogger(__name__)


async def main() -> None:
    configuration = load_configuration()
    ApplicationContext(configuration)
    app_context = get_app_context()
    log_setup(
        service_name="knowledge-flow-worker",
        log_level=configuration.app.log_level,
        store=app_context.get_log_store(),
        use_rich=False,  # Temporal workflow sandbox disallows Rich imports; use plain logging.
    )

    if not configuration.scheduler.enabled:
        logger.warning("Scheduler disabled via configuration.scheduler.enabled=false")
        return
    if configuration.scheduler.backend.lower() != "temporal":
        raise ValueError(f"Scheduler backend '{configuration.scheduler.backend}' not supported; expected 'temporal'.")

    await run_worker(configuration.scheduler.temporal)


if __name__ == "__main__":
    asyncio.run(main())
