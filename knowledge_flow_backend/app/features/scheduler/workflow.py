# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

from datetime import timedelta
from app.features.scheduler.activities import extract_metadata_activity, process_document_activity, vectorize_activity
from temporalio import workflow
from app.features.scheduler.structure import PipelineDefinition
from temporalio.common import RetryPolicy

@workflow.defn
class ExtractMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"📂 ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(
            extract_metadata_activity,
            args=[file],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class PreProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 PreProcess: {file}")
        await workflow.execute_activity(
            process_document_activity,
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class Vectorize:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 Vectorize: {file}")
        await workflow.execute_activity(
            vectorize_activity,
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: PipelineDefinition) -> str:
        workflow.logger.info(f"📂 Ingesting pipeline: {definition.name}")

        for file in definition.files:
            workflow.logger.info(f"➡️ Starting pipeline for file: {file.document_uid}")

            metadata = await workflow.execute_child_workflow(
                ExtractMetadata.run,
                args=[file],
                id=f"extract-{file.document_uid}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            await workflow.execute_child_workflow(
                PreProcess.run,
                args=[file, metadata],
                id=f"process-{file.document_uid}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            await workflow.execute_child_workflow(
                Vectorize.run,
                args=[file, metadata],
                id=f"vectorize-{file.document_uid}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            workflow.logger.info(f"✅ Completed file: {file.document_uid}")

        return "success"

