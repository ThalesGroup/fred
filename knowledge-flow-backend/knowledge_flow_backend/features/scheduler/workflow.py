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
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

def _read(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _display_name(file: Any) -> str:
    return _read(file, "display_name") or "unknown"


def _is_pull(file: Any) -> bool:
    return _read(file, "external_path") is not None


@workflow.defn
class CreatePullFileMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"[SCHEDULER] ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(
            "create_pull_file_metadata",
            args=[file],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class GetPushFileMetadata:
    @workflow.run
    async def run(self, file):
        workflow.logger.info(f"[SCHEDULER] ExtractMetadataWorkflow: {file}")
        return await workflow.execute_activity(
            "get_push_file_metadata",
            args=[file],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class LoadPullFile:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"[SCHEDULER] LoadPullFile: {file}")
        return await workflow.execute_activity(
            "load_pull_file",
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class LoadPushFile:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"[SCHEDULER] LoadPushFile: {file}")
        return await workflow.execute_activity(
            "load_push_file",
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class InputProcess:
    @workflow.run
    async def run(self, user, input_file, metadata):
        workflow.logger.info(f"[SCHEDULER] InputProcess: {input_file}")
        return await workflow.execute_activity(
            "input_process",
            args=[user, input_file, metadata],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file, metadata):
        workflow.logger.info(f"[SCHEDULER] OutputProcess: {file}")
        await workflow.execute_activity(
            "output_process",
            args=[file, metadata, False],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class FastStoreVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity(
            "fast_store_vectors",
            args=[payload],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class FastDeleteVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity(
            "fast_delete_vectors",
            args=[payload],
            schedule_to_close_timeout=timedelta(seconds=30),
        )


@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: Any) -> str:
        pipeline_name = _read(definition, "name", "unknown")
        files = _read(definition, "files", []) or []
        workflow.logger.info(f"[SCHEDULER] Ingesting pipeline: {pipeline_name}")

        for file in files:
            display_name = _display_name(file)
            if _is_pull(file):
                workflow.logger.info(f"[SCHEDULER] Processing pull file: {display_name}")
                metadata = await workflow.execute_child_workflow(
                    CreatePullFileMetadata.run, args=[file], id=f"CreatePullFileMetadata-{display_name}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

                workflow.logger.info(f"[SCHEDULER] Loading pull file local copy: {display_name}")
                local_file_path = await workflow.execute_child_workflow(
                    LoadPullFile.run, args=[file, metadata], id=f"LoadPullFile-{display_name}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

            else:
                workflow.logger.info(f"[SCHEDULER] Processing push file: {display_name}")
                metadata = await workflow.execute_child_workflow(
                    GetPushFileMetadata.run, args=[file], id=f"GetPushFileMetadata-{display_name}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

                workflow.logger.info(f"[SCHEDULER] Loading push file local copy: {display_name}")
                local_file_path = await workflow.execute_child_workflow(
                    LoadPushFile.run, args=[file, metadata], id=f"LoadPushFile-{display_name}", retry_policy=RetryPolicy(maximum_attempts=2)
                )

            workflow.logger.info(f"[SCHEDULER] Input process local copy: {local_file_path or 'unknown'}")

            metadata = await workflow.execute_child_workflow(
                InputProcess.run,
                args=[_read(file, "processed_by"), local_file_path, metadata],
                id=f"InputProcess-{display_name}",
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            workflow.logger.info(f"[SCHEDULER] Output process local copy: {local_file_path or 'unknown'}")
            await workflow.execute_child_workflow(OutputProcess.run, args=[file, metadata], id=f"OutputProcess-{display_name}", retry_policy=RetryPolicy(maximum_attempts=2))

            workflow.logger.info(f"[SCHEDULER] Completed file: {display_name}")

        return "success"
