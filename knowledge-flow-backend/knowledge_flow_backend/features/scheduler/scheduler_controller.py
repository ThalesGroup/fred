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

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user, raise_internal_error

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    FileToProcess,
    PipelineDefinition,
    ProcessDocumentsProgressRequest,
    ProcessDocumentsProgressResponse,
    ProcessDocumentsRequest,
    ProcessDocumentsResponse,
)
from knowledge_flow_backend.features.scheduler.temporal_scheduler import TemporalScheduler

logger = logging.getLogger(__name__)


class SchedulerController:
    """
    Controller for triggering ingestion workflows through Temporal.
    """

    def __init__(self, router: APIRouter):
        app_config = ApplicationContext.get_instance().get_config()
        self.scheduler_config = app_config.scheduler
        self.metadata_service = MetadataService()
        if self.scheduler_config.backend.lower() == "memory":
            self.workflow_client = InMemoryScheduler(self.metadata_service)
        elif self.scheduler_config.backend.lower() == "temporal":
            self.workflow_client = TemporalScheduler(self.scheduler_config, self.metadata_service)
        else:
            raise ValueError(f"Unsupported scheduler backend: {self.scheduler_config.backend}")

        @router.post(
            "/process-documents",
            tags=["Processing"],
            response_model=ProcessDocumentsResponse,
            summary="Submit processing for push/pull files in-process (fire-and-forget)",
            description="Accepts a list of files (document_uid or external_path) and launches the ingestion pipeline in a local background worker thread.",
        )
        async def process_documents(
            req: ProcessDocumentsRequest,
            background_tasks: BackgroundTasks,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.PROCESS, Resource.DOCUMENTS)

            logger.info("Processing %d file(s) via scheduler backend=%s", len(req.files), self.scheduler_config.backend)

            try:
                # You may batch files per-source_tag if needed
                definition = PipelineDefinition(
                    name=req.pipeline_name,
                    # Assign file to the authenticated user
                    files=[FileToProcess.from_file_to_process_without_user(f, user) for f in req.files],
                )
                handle = await self.workflow_client.start_ingestion(user, definition, background_tasks)

                return ProcessDocumentsResponse(
                    status="queued",
                    pipeline_name=definition.name,
                    total_files=len(definition.files),
                    workflow_id=handle.workflow_id,
                    run_id=handle.run_id,
                )
            except Exception as e:
                raise_internal_error(logger, "Failed to submit process-documents workflow", e)

        @router.post(
            "/process-documents/progress",
            tags=["Processing"],
            response_model=ProcessDocumentsProgressResponse,
            summary="Get processing progress for a set of documents",
            description="Given a list of document_uids, returns per-document and aggregate processing progress based on metadata stages.",
        )
        async def process_documents_progress(
            req: ProcessDocumentsProgressRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.PROCESS, Resource.DOCUMENTS)
            return await self.workflow_client.get_progress(user, workflow_id=req.workflow_id)
