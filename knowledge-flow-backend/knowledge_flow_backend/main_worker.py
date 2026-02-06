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

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.scheduler.worker import run_worker
from knowledge_flow_backend.main import load_configuration

logger = logging.getLogger(__name__)


async def main() -> None:
    configuration = load_configuration()
    ApplicationContext(configuration)
    # Keep worker logging local-only: Temporal workflow sandbox must not trigger
    # external log sinks (OpenSearch/HTTP imports) from workflow threads.
    logging.basicConfig(
        level=getattr(logging, configuration.app.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | [pid=%(process)d %(threadName)s] | %(message)s",
    )

    if not configuration.scheduler.enabled:
        logger.warning("Scheduler disabled via configuration.scheduler.enabled=false")
        return
    if configuration.scheduler.backend.lower() != "temporal":
        raise ValueError(f"Scheduler backend '{configuration.scheduler.backend}' not supported; expected 'temporal'.")

    await run_worker(configuration.scheduler.temporal)


if __name__ == "__main__":
    asyncio.run(main())
