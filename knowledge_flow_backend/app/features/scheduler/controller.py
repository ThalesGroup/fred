# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Controller responsible for triggering asynchronous ingestion pipelines via Temporal.

This exposes a single endpoint to submit a structured pipeline definition, which is
dispatched as a Temporal workflow to a background worker. The actual processing is handled
by the DocumentIngestionWorkflow class.

The controller is modular and consistent with the Knowledge Flow architecture.
"""

import logging
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from temporalio.client import Client

from app.application_context import ApplicationContext
from app.features.scheduler.structure import PipelineDefinition
from app.features.scheduler.ingestion_workflow import DocumentIngestionWorkflow

logger = logging.getLogger(__name__)


class SchedulerController:
    """
    Controller for triggering ingestion workflows through Temporal.
    """

    def __init__(self, router: APIRouter):
        self.config = ApplicationContext.get_instance().get_config().scheduler.temporal
        self._register_routes(router)

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
                    DocumentIngestionWorkflow.run,
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
