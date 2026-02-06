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
from typing import Optional, Sequence

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from fred_core.scheduler import TemporalClientProvider

from knowledge_flow_backend.common.structures import SchedulerConfig
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    FileToProcess,
    FileToProcessWithoutUser,
    PipelineDefinition,
)
from knowledge_flow_backend.features.scheduler.temporal_scheduler import TemporalScheduler

logger = logging.getLogger(__name__)


class IngestionTaskService:
    """
    Wraps scheduler backend selection and orchestration.

    Mirrors the AgentTaskService pattern from the agentic backend to keep
    Temporal client handling and business logic out of the controller layer.
    """

    def __init__(
        self,
        *,
        scheduler_config: SchedulerConfig,
        metadata_service: MetadataService,
        temporal_client_provider: Optional[TemporalClientProvider] = None,
    ) -> None:
        self._scheduler_config = scheduler_config
        self._metadata_service = metadata_service
        self._client_provider = temporal_client_provider
        self._task_queue: Optional[str] = None

        backend = scheduler_config.backend.lower()
        if backend == "memory":
            self._scheduler = InMemoryScheduler(self._metadata_service)
        elif backend == "temporal":
            # Reuse the shared Temporal client provider if provided (preferred),
            # otherwise create a local one from configuration.
            self._client_provider = self._client_provider or TemporalClientProvider(scheduler_config.temporal)
            self._task_queue = scheduler_config.temporal.task_queue
            self._scheduler = TemporalScheduler(
                scheduler_config,
                self._metadata_service,
                self._client_provider,
            )
        else:
            raise ValueError(f"Unsupported scheduler backend: {scheduler_config.backend}")

    async def submit_documents(
        self,
        *,
        user: KeycloakUser,
        pipeline_name: str,
        files: Sequence[FileToProcessWithoutUser],
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Kick off a document processing pipeline.
        """
        definition = PipelineDefinition(
            name=pipeline_name,
            files=[FileToProcess.from_file_to_process_without_user(f, user) for f in files],
        )
        handle = await self._scheduler.start_document_processing(
            user=user,
            definition=definition,
            background_tasks=background_tasks,
        )
        return definition, handle

    async def submit_library_processing(
        self,
        *,
        user: KeycloakUser,
        library_tag: str,
        processor_path: str,
        document_uids: Optional[list[str]] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Trigger a library-level processing workflow.
        """
        handle = await self._scheduler.start_library_processing(
            user=user,
            library_tag=library_tag,
            processor_path=processor_path,
            document_uids=document_uids,
            background_tasks=background_tasks,
        )
        return handle

    async def get_progress(self, *, user: KeycloakUser, workflow_id: Optional[str]):
        """
        Proxy progress polling to the configured scheduler backend.
        """
        return await self._scheduler.get_progress(user, workflow_id)

    async def store_fast_vectors(self, *, payload: dict) -> dict:
        """
        Store fast-ingest vectors using the configured scheduler backend.
        """
        return await self._scheduler.store_fast_vectors(payload)

    async def delete_fast_vectors(self, *, payload: dict) -> dict:
        """
        Delete fast-ingest vectors using the configured scheduler backend.
        """
        return await self._scheduler.delete_fast_vectors(payload)
