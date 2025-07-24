# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import logging
from uuid import uuid4
from app.common.utils import log_exception
from fastapi import APIRouter, HTTPException
from temporalio.client import Client

from app.application_context import ApplicationContext
from app.features.scheduler.structure import PipelineDefinition, ProcessDocumentsRequest
from app.features.scheduler.workflow import Process

logger = logging.getLogger(__name__)


class SchedulerController:
    """
    Controller for triggering ingestion workflows through Temporal.
    """

    def __init__(self, router: APIRouter):
        self.config = ApplicationContext.get_instance().get_config().scheduler.temporal
        self._register_routes(router)

        @router.post(
            "/pipelines/process-documents",
            tags=["Ingestion"],
            summary="Submit processing for push/pull files via Temporal",
            description="Accepts a list of files (document_uid or external_path) and launches the appropriate ingestion workflow"
        )
        async def process_documents(req: ProcessDocumentsRequest):
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

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/pipelines/submit",
            tags=["Ingestion"],
            summary="Submit a structured ingestion pipeline to Temporal",
            response_description="Temporal workflow ID and run ID"
        )
        async def submit_pipeline(definition: PipelineDefinition):
            logger.info(f"Received pipeline submission request: {definition.name}")
            try:
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
                logger.info(f"Workflow started: {workflow_id}")
                return {
                    "workflow_id": handle.id,
                    "run_id": handle.first_execution_run_id,
                }
            except Exception as e:
                logger.exception(f"Failed to submit ingestion pipeline: {e}")
                raise HTTPException(status_code=500, detail="Failed to start workflow")
