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
Entrypoint for the Agentic Temporal worker.

Start with:
  CONFIG_FILE=./config/configuration.yaml uv run python -m agentic_backend.main_worker
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from fred_core import log_setup

from agentic_backend.application_context import ApplicationContext, get_app_context
from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration
from agentic_backend.scheduler.temporal.worker import run_worker

logger = logging.getLogger(__name__)


def load_configuration() -> Configuration:
    dotenv_path = os.getenv("ENV_FILE", "./config/.env")
    load_dotenv(dotenv_path)
    config_file = os.getenv("CONFIG_FILE", "./config/configuration.yaml")
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    return parse_server_configuration(config_file)


async def main() -> None:
    configuration = load_configuration()
    ApplicationContext(configuration)
    app_context = get_app_context()
    log_setup(
        service_name="agentic-worker",
        log_level=configuration.app.log_level,
        store=app_context.get_log_store(),
    )

    if not configuration.scheduler.enabled:
        logger.warning("Scheduler disabled via configuration.scheduler.enabled=false")
        return
    if configuration.scheduler.backend.lower() != "temporal":
        raise ValueError(
            f"Scheduler backend '{configuration.scheduler.backend}' not supported; expected 'temporal'."
        )

    await run_worker(configuration.scheduler.temporal)


if __name__ == "__main__":
    asyncio.run(main())
