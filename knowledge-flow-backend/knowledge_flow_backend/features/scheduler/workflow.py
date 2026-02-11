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

import hashlib
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


def _wf_get(item: Any, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _wf_document_uid(file: Any) -> str | None:
    doc_uid = _wf_get(file, "document_uid", None)
    if doc_uid:
        return doc_uid
    external_path = _wf_get(file, "external_path", None)
    source_tag = _wf_get(file, "source_tag", None)
    if not external_path or not source_tag:
        return None
    hash_val = _wf_get(file, "hash", None)
    if not hash_val:
        hash_val = hashlib.sha256(str(external_path).encode()).hexdigest()
    return f"pull-{source_tag}-{hash_val}"


@workflow.defn
class CreatePullFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        workflow.logger.info("[SCHEDULER] CreatePullFileMetadata: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity(
            "create_pull_file_metadata",
            args=[file],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class GetPushFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        workflow.logger.info("[SCHEDULER] GetPushFileMetadata: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity(
            "get_push_file_metadata",
            args=[file],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class LoadPullFile:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> str:
        workflow.logger.info("[SCHEDULER] LoadPullFile: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity(
            "load_pull_file",
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class LoadPushFile:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> str:
        workflow.logger.info("[SCHEDULER] LoadPushFile: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity(
            "load_push_file",
            args=[file, metadata],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class InputProcess:
    @workflow.run
    async def run(self, user: Any, input_file: str, metadata: Any) -> Any:
        workflow.logger.info("[SCHEDULER] InputProcess: %s", input_file)
        return await workflow.execute_activity(
            "input_process",
            args=[user, input_file, metadata],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> None:
        workflow.logger.info("[SCHEDULER] OutputProcess: %s", _wf_get(file, "display_name", "unknown"))
        await workflow.execute_activity(
            "output_process",
            args=[file, metadata, False],
            schedule_to_close_timeout=timedelta(hours=1),
        )


@workflow.defn
class FastStoreVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity(
            "fast_store_vectors",
            args=[payload],
            schedule_to_close_timeout=timedelta(hours=1),
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
        pipeline_name = _wf_get(definition, "name", "unknown")
        files = _wf_get(definition, "files", []) or []
        workflow.logger.info(f"[SCHEDULER] Ingesting pipeline: {pipeline_name}")
        workflow_id = workflow.info().workflow_id
        last_document_uid: str | None = None
        last_filename: str | None = None

        try:
            for file in files:
                display_name = _wf_get(file, "display_name", None) or "unknown"
                is_pull = _wf_get(file, "external_path", None) is not None
                provisional_uid = _wf_document_uid(file)
                last_document_uid = provisional_uid
                last_filename = display_name
                await workflow.execute_activity(
                    "record_current_document",
                    args=[workflow_id, provisional_uid, display_name],
                    schedule_to_close_timeout=timedelta(hours=1),
                )
                if is_pull:
                    workflow.logger.info("[SCHEDULER] Processing pull file: %s", display_name)
                    metadata = await workflow.execute_child_workflow(
                        CreatePullFileMetadata.run,
                        args=[file],
                        id=f"CreatePullFileMetadata-{display_name}",
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                    last_document_uid = _wf_get(metadata, "document_uid")
                    await workflow.execute_activity(
                        "record_current_document",
                        args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
                        schedule_to_close_timeout=timedelta(hours=1),
                    )
                    local_file_path = await workflow.execute_child_workflow(
                        LoadPullFile.run,
                        args=[file, metadata],
                        id=f"LoadPullFile-{display_name}",
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                else:
                    workflow.logger.info("[SCHEDULER] Processing push file: %s", display_name)
                    metadata = await workflow.execute_child_workflow(
                        GetPushFileMetadata.run,
                        args=[file],
                        id=f"GetPushFileMetadata-{display_name}",
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )
                    last_document_uid = _wf_get(metadata, "document_uid")
                    await workflow.execute_activity(
                        "record_current_document",
                        args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
                        schedule_to_close_timeout=timedelta(hours=1),
                    )
                    local_file_path = await workflow.execute_child_workflow(
                        LoadPushFile.run,
                        args=[file, metadata],
                        id=f"LoadPushFile-{display_name}",
                        retry_policy=RetryPolicy(maximum_attempts=2),
                    )

                metadata = await workflow.execute_child_workflow(
                    InputProcess.run,
                    args=[_wf_get(file, "processed_by"), local_file_path, metadata],
                    id=f"InputProcess-{display_name}",
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                await workflow.execute_child_workflow(
                    OutputProcess.run,
                    args=[file, metadata],
                    id=f"OutputProcess-{display_name}",
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )
                workflow.logger.info("[SCHEDULER] Completed file: %s", display_name)

            await workflow.execute_activity(
                "record_workflow_status",
                args=[workflow_id, "COMPLETED", None, last_document_uid, last_filename],
                schedule_to_close_timeout=timedelta(hours=1),
            )
            return "success"
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
            try:
                await workflow.execute_activity(
                    "record_workflow_status",
                    args=[workflow_id, "FAILED", error_message, last_document_uid, last_filename],
                    schedule_to_close_timeout=timedelta(hours=1),
                )
            except Exception:
                workflow.logger.exception("[SCHEDULER] Failed to record workflow failure", exc_info=True)
            raise
