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
    TagPermission,
    get_current_user,
)
from fred_core.common import raise_internal_error
from fred_core.scheduler import TemporalClientProvider

from knowledge_flow_backend.application_context import ApplicationContext, get_rebac_engine
from knowledge_flow_backend.features.metadata.service import MetadataService
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
            summary="Submit processing for push/pull files in-process (fire-and-forget)",
            description=(
                "Accepts a list of files (document_uid or external_path) and launches the ingestion pipeline "
                "in a local background worker thread. Push and pull files must be submitted in separate requests."
            ),
        )
        async def process_documents(
            req: ProcessDocumentsRequest,
            background_tasks: BackgroundTasks,
            user: KeycloakUser = Depends(get_current_user),
        ):
            # AUTHZ-05 §27: team-scoped via the tags carried on each file, mirroring
            # the same per-tag pattern already used by upload-process-documents
            # (ingestion_controller.py), instead of the org-level
            # CAN_PROCESS_CONTENT gate (any global Keycloak `editor` could
            # otherwise process any team's content). A file with no tags has no
            # ReBAC object to check against, so — like the empty-scope case in
            # corpus_manager_controller.py's `_authorize_scope` — it is denied
            # rather than silently allowed through.
            for file in req.files:
                if not file.tags:
                    raise HTTPException(
                        400,
                        f"File '{file.display_name or file.document_uid or file.external_path}' cannot be authorized yet: pass at least one tag (files with no tags are not team-checkable).",
                    )
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
                )
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
