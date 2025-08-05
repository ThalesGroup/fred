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

from datetime import timedelta
from app.features.scheduler.activities import create_pull_file_metadata, get_push_file_metadata, input_process, load_pull_file, load_push_file, output_process
from temporalio import workflow
from app.features.scheduler.structure import PipelineDefinition
from temporalio.common import RetryPolicy


@workflow.defn
class CreatePullFileMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"📂 ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(create_pull_file_metadata, args=[file], schedule_to_close_timeout=timedelta(seconds=60))


@workflow.defn
class GetPushFileMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"📂 ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(get_push_file_metadata, args=[file], schedule_to_close_timeout=timedelta(seconds=60))


workflow.defn


class LoadPullFile:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 LoadPullFile: {file}")
        return await workflow.execute_activity(load_pull_file, args=[file, metadata], schedule_to_close_timeout=timedelta(seconds=60))


workflow.defn


class LoadPushFile:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 LoadPushFile: {file}")
        return await workflow.execute_activity(load_push_file, args=[file, metadata], schedule_to_close_timeout=timedelta(seconds=60))


@workflow.defn
class InputProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 InputProcess: {file}")
        return await workflow.execute_activity(input_process, args=[file, metadata], schedule_to_close_timeout=timedelta(seconds=60))


@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"📂 OutputProcess: {file}")
        await workflow.execute_activity(output_process, args=[file, metadata, False], schedule_to_close_timeout=timedelta(seconds=60))


@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: PipelineDefinition) -> str:
        workflow.logger.info(f"📂 Ingesting pipeline: {definition.name}")

        for file in definition.files:
            if file.is_pull():
                workflow.logger.info(f"Processing pull file: {file.display_name or 'unknown'}")
                metadata = await workflow.execute_child_workflow(
                    CreatePullFileMetadata.run, args=[file], id=f"CreatePullFileMetadata-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

                workflow.logger.info(f"Loading pull file local copy: {file.display_name or 'unknown'}")
                local_file_path = await workflow.execute_child_workflow(
                    LoadPullFile.run, args=[file, metadata], id=f"LoadPullFile-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

            else:
                workflow.logger.info(f"Processing push file: {file.display_name or 'unknown'}")
                metadata = await workflow.execute_child_workflow(
                    GetPushFileMetadata.run, args=[file], id=f"GetPushFileMetadata-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

                workflow.logger.info(f"Loading push file local copy: {file.display_name or 'unknown'}")
                local_file_path = await workflow.execute_child_workflow(
                    LoadPushFile.run, args=[file, metadata], id=f"LoadPushFile-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

            workflow.logger.info(f"Input process local copy: {local_file_path or 'unknown'}")

            metadata = await workflow.execute_child_workflow(
                InputProcess.run, args=[local_file_path, metadata], id=f"InputProcess-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2)
            )

            workflow.logger.info(f"Output process local copy: {local_file_path or 'unknown'}")
            await workflow.execute_child_workflow(OutputProcess.run, args=[file, metadata], id=f"OutputProcess-{file.display_name or 'unknown'}", retry_policy=RetryPolicy(maximum_attempts=2))

            workflow.logger.info(f"✅ Completed file: {file.display_name}")

        return "success"
