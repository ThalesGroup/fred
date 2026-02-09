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
from typing import Optional
from uuid import uuid4

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from fred_core.scheduler import TemporalClientProvider
from temporalio.client import Client

from knowledge_flow_backend.common.structures import SchedulerConfig
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    PipelineDefinition,
)
from knowledge_flow_backend.features.scheduler.workflow import FastDeleteVectors, FastStoreVectors, Process

logger = logging.getLogger(__name__)


class TemporalScheduler(BaseScheduler):
    """
    Temporal-backed implementation of the ingestion workflow client.

    - Registers a workflow_id and associated document_uids.
    - Starts a Temporal workflow that orchestrates ingestion.
    """

    def __init__(
        self,
        scheduler_config: SchedulerConfig,
        metadata_service: MetadataService,
        temporal_client_provider: Optional[TemporalClientProvider] = None,
    ) -> None:
        super().__init__(metadata_service)
        self._scheduler_config = scheduler_config
        # Prefer a shared Temporal client provider (mirrors agentic backend pattern)
        self._client_provider = temporal_client_provider or TemporalClientProvider(scheduler_config.temporal)

    async def start_document_processing(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,  # kept for interface symmetry, not used
    ) -> WorkflowHandle:
        handle = self._register_workflow(user, definition)

        client: Client = await self._client_provider.get_client()

        workflow_handle = await client.start_workflow(
            Process.run,
            definition,
            id=handle.workflow_id,
            task_queue=self._scheduler_config.temporal.task_queue,
        )

        logger.info("🛠️ started temporal workflow=%s", workflow_handle.id)

        return WorkflowHandle(workflow_id=workflow_handle.id, run_id=workflow_handle.first_execution_run_id)

    async def start_library_processing(
        self,
        user: KeycloakUser,
        library_tag: str,
        processor_path: str,
        document_uids: Optional[list[str]] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        raise NotImplementedError("Library processing is not yet supported with the Temporal scheduler.")

    async def store_fast_vectors(self, payload: dict) -> dict:
        client: Client = await self._client_provider.get_client()
        return await client.execute_workflow(
            FastStoreVectors.run,
            payload,
            id=f"fast-ingest-{uuid4().hex}",
            task_queue=self._scheduler_config.temporal.task_queue,
        )

    async def delete_fast_vectors(self, payload: dict) -> dict:
        client: Client = await self._client_provider.get_client()
        return await client.execute_workflow(
            FastDeleteVectors.run,
            payload,
            id=f"fast-delete-{uuid4().hex}",
            task_queue=self._scheduler_config.temporal.task_queue,
        )
