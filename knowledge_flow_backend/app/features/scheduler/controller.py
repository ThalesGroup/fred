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
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user, raise_internal_error
from temporalio.client import Client

from app.application_context import ApplicationContext
from app.common.utils import log_exception
from app.features.scheduler.activities import create_pull_file_metadata, get_push_file_metadata, input_process, load_pull_file, load_push_file, output_process
from app.features.scheduler.structure import PipelineDefinition, ProcessDocumentsRequest
from app.features.scheduler.workflow import Process

logger = logging.getLogger(__name__)


async def run_ingestion_pipeline(definition: PipelineDefinition) -> str:
    for file in definition.files:
        if file.is_pull():
            metadata = create_pull_file_metadata(file)
            local_file_path = load_pull_file(file, metadata)
            metadata = input_process(input_file=local_file_path, metadata=metadata)
            metadata = output_process(file=file, metadata=metadata, accept_memory_storage=True)
        else:
            metadata = get_push_file_metadata(file)
            local_file_path = load_push_file(file, metadata)
            metadata = input_process(input_file=local_file_path, metadata=metadata)
            metadata = output_process(file=file, metadata=metadata, accept_memory_storage=True)
    return "success"


class SchedulerController:
    """
    Controller for triggering ingestion workflows through Temporal.
    """

    def __init__(self, router: APIRouter):
        self.config = ApplicationContext.get_instance().get_config().scheduler.temporal

        @router.post(
            "/process-documents",
            tags=["Processing"],
            summary="Submit processing for push/pull files via Temporal",
            description="Accepts a list of files (document_uid or external_path) and launches the appropriate ingestion workflow",
        )
        async def process_documents(req: ProcessDocumentsRequest, _: KeycloakUser = Depends(get_current_user)):
            logger.info(f"Processing {len(req.files)} file(s) via Temporal pipeline")

            try:
                # You may batch files per-source_tag if needed
                definition = PipelineDefinition(
                    name=req.pipeline_name,
                    files=req.files,
                )
                result = await run_ingestion_pipeline(definition)
                return {"status": result}
            except Exception as e:
                raise_internal_error(logger, "Failed to submit process-documents workflow", e)

        @router.post(
            "/schedule-documents",
            tags=["Processing"],
            summary="Submit processing for push/pull files via Temporal",
            description="Accepts a list of files (document_uid or external_path) and launches the appropriate ingestion workflow",
        )
        async def schedule_documents(req: ProcessDocumentsRequest, _: KeycloakUser = Depends(get_current_user)):
            logger.info(f"Processing {len(req.files)} file(s) via Temporal pipeline")

            try:
                # You may batch files per-source_tag if needed
                definition = PipelineDefinition(
                    name=req.pipeline_name,
                    files=req.files,
                )

                client = await Client.connect(
                    target_host=self.config.host,
                    namespace=self.config.namespace,
                )
                workflow_id = f"{self.config.workflow_prefix}-{uuid4()}"
                handle = await client.start_workflow(
                    Process.run,
                    definition,
                    id=workflow_id,
                    task_queue=self.config.task_queue,
                )
                logger.info(f"🛠️ started temporal workflow={workflow_id}")
                return {
                    "workflow_id": handle.id,
                    "run_id": handle.first_execution_run_id,
                }

            except Exception as e:
                log_exception(e, "Failed to submit process-documents workflow")
                raise HTTPException(status_code=500, detail="Workflow submission failed")
