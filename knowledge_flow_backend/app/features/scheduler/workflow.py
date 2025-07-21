# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

from temporalio import workflow
from app.features.scheduler.structure import PipelineDefinition


@workflow.defn
class DocumentIngestionWorkflow:
    """
    Simplified Temporal workflow to validate Temporal wiring.

    This version does not call any activities and simply logs file paths.
    Once validated, activities like `extract_metadata` can be added incrementally.
    """

    @workflow.run
    async def run(self, definition: PipelineDefinition) -> str:
        workflow.logger.info(f"📂 Starting ingestion for pipeline: {definition.name}")
        for file in definition.files:
            workflow.logger.info(f"📄 Processing file: {file.source_tag}::{file.document_uid}")
            # metadata = await workflow.execute_activity(
            #     extract_metadata,
            #     file,
            #     schedule_to_close_timeout=timedelta(seconds=60),
            # )
            #workflow.logger.info(f"📄 Metadata created: {metadata}")
            workflow.logger.info("📄 Metadata created")
        workflow.logger.info(f"✅ Ingestion workflow complete for pipeline: {definition.name}")
        return "success"
