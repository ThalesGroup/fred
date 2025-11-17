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

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import BackgroundTasks
from fred_core import KeycloakUser

from knowledge_flow_backend.features.scheduler.activities import create_pull_file_metadata, get_push_file_metadata, input_process, load_pull_file, load_push_file, output_process
from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    PipelineDefinition,
)

logger = logging.getLogger(__name__)


def _run_ingestion_pipeline(definition: PipelineDefinition) -> str:
    """
    Local, in-process ingestion pipeline used when Temporal is disabled.

    This mirrors the behavior of the Temporal workflow but executes synchronously
    in a background thread managed by FastAPI's BackgroundTasks.
    """
    # Simulate slower per-file processing so that UI progress indicators remain
    # visible during local development/demo.
    simulated_delay_seconds = 0
    logger.info(
        "Starting local ingestion pipeline for %d file(s) with simulated delay of %d seconds per file",
        len(definition.files),
        simulated_delay_seconds,
    )

    for file in definition.files:
        logger.info("[SCHEDULER][IN_MEMORY] Processing file %s (pull=%s) via local ingestion pipeline", file.external_path, file.is_pull())

        if simulated_delay_seconds > 0:
            time.sleep(simulated_delay_seconds)

        if file.is_pull():
            metadata = create_pull_file_metadata(file)
            local_file_path = load_pull_file(file, metadata)
            metadata = input_process(user=file.processed_by, input_file=local_file_path, metadata=metadata)
            metadata = output_process(file=file, metadata=metadata, accept_memory_storage=True)
        else:
            metadata = get_push_file_metadata(file)
            local_file_path = load_push_file(file, metadata)
            metadata = input_process(user=file.processed_by, input_file=local_file_path, metadata=metadata)
            metadata = output_process(file=file, metadata=metadata, accept_memory_storage=True)

    return "success"


class InMemoryScheduler(BaseScheduler):
    """
    In-memory implementation of the ingestion workflow client.

    - Registers a workflow_id and associated document_uids.
    - Executes the ingestion pipeline locally via BackgroundTasks.
    """

    async def start_ingestion(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        handle = self._register_workflow(user, definition)

        if background_tasks is not None:
            background_tasks.add_task(_run_ingestion_pipeline, definition)
        else:
            # Fallback for non-HTTP contexts; this will block the caller.
            logger.warning("[SCHEDULER][IN_MEMORY] BackgroundTasks not provided, running ingestion pipeline synchronously")
            _run_ingestion_pipeline(definition)

        return handle
