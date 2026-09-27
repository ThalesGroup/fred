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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fred_core import (
    DocumentPermission,
    KeycloakUser,
    TagPermission,
    get_current_user,
)
from fred_core.common import raise_internal_error
from fred_core.documents.document_structures import ProcessingStage, ProcessingStatus
from fred_core.scheduler import TemporalClientProvider

from knowledge_flow_backend.application_context import ApplicationContext, get_rebac_engine
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionAlreadyActive
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
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
        app_context = ApplicationContext.get_instance()
        app_config = app_context.get_config()
        self.scheduler_config = app_config.scheduler
        self.effective_scheduler_backend = app_context.get_scheduler_backend()
        self.metadata_service = MetadataService()
        self.task_service = IngestionTaskService(
            scheduler_config=self.scheduler_config,
            processing_config=app_config.processing,
            metadata_service=self.metadata_service,
            temporal_client_provider=temporal_client_provider,
            max_parallelism=app_config.scheduler.temporal.ingestion_workflow_parallelism,
        )

        @router.post(
            "/process-documents",
            tags=["Processing"],
            response_model=ProcessDocumentsResponse,
            summary="Submit tracked ingestion for push/pull files",
            description=(
                "Accepts a list of files (document_uid or external_path) and launches the ingestion pipeline "
                "through the configured scheduler. Push and pull files must be submitted in separate requests."
            ),
        )
        async def process_documents(
            req: ProcessDocumentsRequest,
            background_tasks: BackgroundTasks,
            user: KeycloakUser = Depends(get_current_user),
        ):
            if not req.files:
                raise HTTPException(400, "At least one document is required")
            for file in req.files:
                if file.task_id:
                    raise HTTPException(400, "Task identifiers are assigned by the server")
                if file.is_push() and file.document_uid:
                    await get_rebac_engine().check_user_permission_or_raise(user, DocumentPermission.PROCESS, file.document_uid)
                    metadata = await self.metadata_service.get_document_metadata(user, file.document_uid)
                    file.tags = list(metadata.tags.tag_ids)
                    file.source_tag = metadata.source.source_tag or ""
                    file.display_name = metadata.document_name
                    if req.relaunch:
                        stages = metadata.processing.stages
                        failed = ProcessingStatus.FAILED in stages.values()
                        queryable = any(stages.get(stage) == ProcessingStatus.DONE for stage in (ProcessingStage.VECTORIZED, ProcessingStage.SQL_INDEXED))
                        if ProcessingStatus.IN_PROGRESS in stages.values() or (queryable and not failed):
                            raise HTTPException(409, "Only never-processed or failed documents can be relaunched")
                        if metadata.processing.profile is not None:
                            file.profile = metadata.processing.profile
                        elif "profile" not in file.model_fields_set:
                            raise HTTPException(422, "Choose an ingestion profile for this document")
                elif req.relaunch:
                    raise HTTPException(400, "Relaunch requires an existing document")

            # Authorize the document's stored tags, never a caller-supplied substitute.
            for file in req.files:
                if not file.tags:
                    raise HTTPException(400, "Documents must belong to an authorized folder")
            for file in req.files:
                for tag_id in file.tags:
                    await get_rebac_engine().check_user_permission_or_raise(user, TagPermission.UPDATE, tag_id)

            logger.info(
                "Processing %d file(s) via scheduler backend=%s",
                len(req.files),
                self.effective_scheduler_backend,
            )

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
                    task_ids={file.document_uid or file.to_virtual_metadata().document_uid: file.task_id for file in definition.files if file.task_id},
                )
            except IngestionAlreadyActive as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            except Exception as e:
                return raise_internal_error(logger, "Failed to submit process-documents workflow", e)

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
            await get_rebac_engine().check_user_permission_or_raise(user, TagPermission.UPDATE, req.library_tag)

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
                return raise_internal_error(logger, "Failed to submit process-library workflow", e)
