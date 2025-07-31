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
Knowledge Flow Backend – API Entry Point

This module launches the main FastAPI web server used by the Knowledge Flow backend.

Responsibilities:
-----------------
- Load configuration and environment variables (via `configuration.yaml` and `.env`)
- Initialize the shared application context (singleton for config, stores, processors, etc.)
- Register FastAPI routes and controllers (e.g., ingestion, metadata, vector search)
- Start Uvicorn HTTP server to expose REST and MCP endpoints
- Optionally: spawn a background Temporal worker thread if enabled in config

Temporal Worker (Optional):
---------------------------
If `scheduler.enabled = true` and `scheduler.backend = temporal` is set in the configuration,
this entry point also starts a Temporal worker in a background thread. This worker:

- Connects to the Temporal server (e.g., localhost:7233)
- Registers ingestion-related workflows and activities
- Listens on the `ingestion` task queue
- Processes long-running ingestion pipelines asynchronously

This hybrid mode is convenient for local development and test environments.

Production Note:
----------------
In a production environment, it is recommended to split this into two separate processes:
- `main_api.py` → for the FastAPI HTTP server
- `main_worker.py` → for the dedicated Temporal worker service

This separation supports independent scaling and better resource management in Kubernetes or other orchestration platforms.
"""

import asyncio
import atexit
import logging
import os
from rich.logging import RichHandler
from app.features.scheduler.worker import run_worker
from app.application_context import ApplicationContext
from app.common.structures import Configuration
from app.common.utils import parse_server_configuration
from dotenv import load_dotenv

# -----------------------
# LOGGING + ENVIRONMENT
# -----------------------

logger = logging.getLogger(__name__)


def configure_logging(log_level: str):
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=False, show_time=False, show_path=False)],
    )
    logging.getLogger(__name__).info(f"Logging configured at {log_level.upper()} level.")


def load_environment(dotenv_path: str = "./config/.env"):
    if load_dotenv(dotenv_path):
        logging.getLogger().info(f"✅ Loaded environment variables from: {dotenv_path}")
    else:
        logging.getLogger().warning(f"⚠️ No .env file found at: {dotenv_path}")


# -----------------------
# MAIN ENTRYPOINT
# -----------------------


async def main():
    load_environment()
    config_file = os.environ["CONFIG_FILE"]
    configuration: Configuration = parse_server_configuration(config_file)
    configure_logging(configuration.app.log_level)
    ApplicationContext(configuration)

    if configuration.scheduler.enabled:
        if configuration.scheduler.backend == "temporal":
            logger.info("🛠️ Launching Temporal ingestion scheduler (backend: temporal)")
            await run_worker(configuration.scheduler.temporal)
        else:
            raise ValueError(f"Scheduler is enabled but unsupported backend '{configuration.scheduler.backend}' was provided. Expected: 'temporal'. Please check your configuration.yaml.")


if __name__ == "__main__":
    asyncio.run(main())

# Note: We do not define a global `app = FastAPI()` for ASGI (e.g., `uvicorn app.main:app`)
# because this application is always launched via the CLI `main()` function.
# This allows full control over configuration (e.g., --config-path, --base-url) and avoids
# the need for a static app instance required by ASGI-based servers like Uvicorn in import mode.
