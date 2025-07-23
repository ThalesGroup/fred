# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# http://www.apache.org/licenses/LICENSE-2.0

from datetime import timedelta
from app.features.scheduler.activities import extract_metadata, input_process, output_process
from temporalio import workflow
from app.features.scheduler.structure import PipelineDefinition
from temporalio.common import RetryPolicy

@workflow.defn
class ExtractMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"📂 ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(
            extract_metadata,
            args=[file],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class InputProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 InputProcess: {file}")
        return await workflow.execute_activity(
            input_process,
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 OutputProcess: {file}")
        await workflow.execute_activity(
            output_process,
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60)
        )

@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: PipelineDefinition) -> str:
        workflow.logger.info(f"📂 Ingesting pipeline: {definition.name}")

        for file in definition.files:
            workflow.logger.info(f"Before pipeline for file: {file}")
            metadata = await workflow.execute_child_workflow(
                ExtractMetadata.run,
                args=[file],
                id=f"extract-{file.display_name or 'unknown'}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            workflow.logger.info(f"Before  InputProcess: {file}")
            workflow.logger.info(f"Before  InputProcess: {metadata}")
            #file.document_uid = metadata.document_uid
            metadata = await workflow.execute_child_workflow(
                InputProcess.run,
                args=[file, metadata],
                id=f"input-process-{file.display_name or 'unknown'}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            workflow.logger.info(f"Before  OutputProcess: {file}")
            workflow.logger.info(f"Before  OutputProcess: {metadata}")
            await workflow.execute_child_workflow(
                OutputProcess.run,
                args=[file, metadata],
                id=f"output-process-{file.display_name or 'unknown'}",
                retry_policy=RetryPolicy(maximum_attempts=2)
            )

            workflow.logger.info(f"✅ Completed file: {file.display_name}")

        return "success"

