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
    KeycloakUser,
    get_current_user,
)
from fred_core.common import raise_internal_error
from fred_core.documents.document_structures import ProcessingStage, ProcessingStatus
from fred_core.scheduler import TemporalClientProvider

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.ingestion_delivery import IngestionAlreadyActive
from knowledge_flow_backend.features.scheduler.scheduler_service import IngestionTaskService
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    ProcessDocumentsRequest,
    ProcessDocumentsResponse,
    ProcessLibraryRequest,
    ProcessLibraryResponse,
)
from knowledge_flow_backend.features.tag.corpus_lifecycle import CorpusBusy

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
            if any(file.task_id for file in req.files):
                raise HTTPException(400, "Task identifiers are assigned by the server")
            document_uids = list({file.document_uid for file in req.files if file.is_push() and file.document_uid})
            stored = {doc.document_uid: doc for doc in await self.metadata_service.metadata_store.get_metadata_by_uids(document_uids)} if document_uids else {}
            for file in req.files:
                if file.is_push() and file.document_uid:
                    metadata = stored.get(file.document_uid)
                    if metadata is None:
                        raise HTTPException(404, "Document not found")
                    if metadata.kind != "corpus":
                        raise HTTPException(400, "Conversation attachments cannot be processed as corpus documents")
                    file.tags = list(metadata.tags.tag_ids)
                    file.source_tag = metadata.source.source_tag or ""
                    file.display_name = metadata.document_name
                elif req.relaunch:
                    raise HTTPException(400, "Relaunch requires an existing document")
                if len(file.tags) != 1:
                    raise HTTPException(400, "Documents must belong to exactly one authorized folder")

            # Stored membership determines admission; group checks by team/source root.
            await self.metadata_service.corpus_access.check_folders(user, list({file.tags[0] for file in req.files}), write=True)
            if req.relaunch:
                for file in req.files:
                    assert file.document_uid is not None
                    metadata = stored[file.document_uid]
                    stages = metadata.processing.stages
                    failed = ProcessingStatus.FAILED in stages.values()
                    queryable = any(stages.get(stage) == ProcessingStatus.DONE for stage in (ProcessingStage.VECTORIZED, ProcessingStage.SQL_INDEXED))
                    if ProcessingStatus.IN_PROGRESS in stages.values() or (queryable and not failed):
                        raise HTTPException(409, "Only never-processed or failed documents can be relaunched")
                    if metadata.processing.profile is not None:
                        file.profile = metadata.processing.profile
                    elif "profile" not in file.model_fields_set:
                        raise HTTPException(422, "Choose an ingestion profile for this document")

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
            except (IngestionAlreadyActive, CorpusBusy) as e:
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
            await self.metadata_service.corpus_access.get_folder(user, req.library_tag, write=True)

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
