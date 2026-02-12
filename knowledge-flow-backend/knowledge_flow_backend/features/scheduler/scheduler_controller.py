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
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user, raise_internal_error
from fred_core.scheduler import TemporalClientProvider

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    ProcessDocumentsProgressRequest,
    ProcessDocumentsProgressResponse,
    ProcessDocumentsRequest,
    ProcessDocumentsResponse,
    ProcessLibraryRequest,
    ProcessLibraryResponse,
)

logger = logging.getLogger(__name__)


class SchedulerController:
    """
    Controller for triggering ingestion workflows through Temporal.
    """

    def __init__(self, router: APIRouter, temporal_client_provider: Optional[TemporalClientProvider] = None):
        app_config = ApplicationContext.get_instance().get_config()
        self.scheduler_config = app_config.scheduler
        self.metadata_service = MetadataService()
        self.task_service = IngestionTaskService(
            scheduler_config=self.scheduler_config,
            metadata_service=self.metadata_service,
            temporal_client_provider=temporal_client_provider,
            max_parallelism=app_config.app.max_ingestion_workers,
        )

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
                definition, handle = await self.task_service.submit_documents(
                    user=user,
                    pipeline_name=req.pipeline_name,
                    files=req.files,
                    background_tasks=background_tasks,
                )

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
            "/process-library",
            tags=["Processing"],
            response_model=ProcessLibraryResponse,
            summary="Run a library-level processor for a given tag (in-process when using memory scheduler)",
        )
        async def process_library(
            req: ProcessLibraryRequest,
            background_tasks: BackgroundTasks,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.PROCESS, Resource.DOCUMENTS)

            try:
                handle = await self.task_service.submit_library_processing(
                    user=user,
                    library_tag=req.library_tag,
                    processor_path=req.processor,
                    document_uids=req.document_uids,
                    background_tasks=background_tasks,
                )
                return ProcessLibraryResponse(
                    status="queued",
                    library_tag=req.library_tag,
                    workflow_id=handle.workflow_id,
                    run_id=handle.run_id,
                    document_count=len(req.document_uids) if req.document_uids else None,
                )
            except Exception as e:
                raise_internal_error(logger, "Failed to submit process-library workflow", e)

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
            return await self.task_service.get_progress(user=user, workflow_id=req.workflow_id)
