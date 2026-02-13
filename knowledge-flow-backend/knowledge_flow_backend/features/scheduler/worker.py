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

from knowledge_flow_backend.common.structures import TemporalSchedulerConfig
from knowledge_flow_backend.features.scheduler.activities import (
    create_pull_file_metadata,
    fast_delete_vectors,
    fast_store_vectors,
    get_push_file_metadata,
    input_process,
    load_pull_file,
    load_push_file,
    output_process,
    record_current_document,
    record_workflow_status,
)
from knowledge_flow_backend.features.scheduler.workflow import (
    CreatePullFileMetadata,
    FastDeleteVectors,
    FastStoreVectors,
    GetPushFileMetadata,
    InputProcess,
    LoadPullFile,
    LoadPushFile,
    OutputProcess,
    Process,
    ProcessFile,
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
    logger.info(f"[SCHEDULER] Connected to Temporal. Registering worker on queue: '{config.task_queue}'")

    # Use thread pool executor for sync activities
    executor = concurrent.futures.ThreadPoolExecutor()
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[
            Process,
            ProcessFile,
            CreatePullFileMetadata,
            GetPushFileMetadata,
            LoadPullFile,
            LoadPushFile,
            InputProcess,
            OutputProcess,
            FastStoreVectors,
            FastDeleteVectors,
        ],
        activities=[
            create_pull_file_metadata,
            get_push_file_metadata,
            load_pull_file,
            load_push_file,
            input_process,
            output_process,
            fast_store_vectors,
            fast_delete_vectors,
            record_current_document,
            record_workflow_status,
        ],
        activity_executor=executor,
    )

    logger.info("[SCHEDULER] Temporal worker is now running and ready to receive ingestion jobs.")
    await worker.run()
