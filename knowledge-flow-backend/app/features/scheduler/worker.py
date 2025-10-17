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
Temporal worker responsible for running ingestion pipelines.

This worker connects to the Temporal service, registers all ingestion-related
activities and workflows, and listens on the configured task queue.

It is launched in a background thread from main.py during application startup.
"""

import concurrent.futures
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.common.structures import TemporalSchedulerConfig
from app.features.scheduler.activities import (
    get_push_file_metadata,
    input_process,
    output_process,
)
from app.features.scheduler.workflow import GetPushFileMetadata, InputProcess, OutputProcess, Process

# Use basic logging instead of rich within the Temporal worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker(config: TemporalSchedulerConfig):
    """
    Connect to Temporal and start the ingestion worker.

    Args:
        config (TemporalSchedulerConfig): Temporal connection + task queue config
    """
    logger.info(f"🔗 Connecting to Temporal at {config.host} (namespace={config.namespace})")
    client = await Client.connect(
        target_host=config.host,
        namespace=config.namespace,
    )
    logger.info(f"✅ Connected to Temporal. Registering worker on queue: '{config.task_queue}'")

    # Use thread pool executor for sync activities
    executor = concurrent.futures.ThreadPoolExecutor()
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[
            Process,
            GetPushFileMetadata,
            InputProcess,
            OutputProcess,
        ],
        activities=[
            get_push_file_metadata,
            input_process,
            output_process,
        ],
        activity_executor=executor,
    )

    logger.info("🚀 Temporal worker is now running and ready to receive ingestion jobs.")
    await worker.run()
