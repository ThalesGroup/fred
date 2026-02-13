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

TIMEOUT_METADATA = timedelta(minutes=10)
TIMEOUT_IO = timedelta(minutes=30)
TIMEOUT_CPU = timedelta(hours=1)
TIMEOUT_RECORD = timedelta(minutes=5)
TIMEOUT_FAST_DELETE = timedelta(minutes=5)

RETRY_POLICY_METADATA = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
)
RETRY_POLICY_IO = RetryPolicy(
    maximum_attempts=4,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
)
RETRY_POLICY_CPU = RetryPolicy(
    maximum_attempts=2,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=20),
)
RETRY_POLICY_RECORD = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=5),
)


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


def _wf_child_id(prefix: str, file: Any, file_index: int) -> str:
    """
    Build a deterministic, collision-resistant child workflow id.
    """
    display_name = _wf_get(file, "display_name", None) or "unknown"
    doc_uid = _wf_document_uid(file) or f"idx-{file_index}"
    raw = f"{prefix}|{file_index}|{display_name}|{doc_uid}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{prefix}-{file_index}-{digest}"


def _wf_format_error(exc: BaseException, stage: str) -> str:
    message = str(exc).strip() or f"{type(exc).__name__}: No error message"
    return f"{stage} failed: {message}"


def _wf_activity_options(timeout: timedelta, retry_policy: RetryPolicy) -> dict[str, Any]:
    return {
        "schedule_to_close_timeout": timeout,
        "retry_policy": retry_policy,
    }


def _wf_workflow_task_queue(definition: Any) -> str | None:
    return _wf_get(definition, "workflow_task_queue", None)


def _wf_io_task_queue(definition: Any) -> str | None:
    return _wf_get(definition, "io_task_queue", None) or _wf_workflow_task_queue(definition)


def _wf_cpu_task_queue(definition: Any) -> str | None:
    return _wf_get(definition, "cpu_task_queue", None) or _wf_workflow_task_queue(definition)


def _wf_log(stage: str, message: str, **fields: Any) -> None:
    info = workflow.info()
    merged = {
        "workflow_id": getattr(info, "workflow_id", "unknown"),
        "run_id": getattr(info, "run_id", "unknown"),
        "task_queue": getattr(info, "task_queue", "unknown"),
        "attempt": getattr(info, "attempt", "unknown"),
    }
    merged.update(fields)
    attrs = " ".join(f"{key}={value}" for key, value in merged.items() if value is not None)
    workflow.logger.info("[SCHEDULER][%s] %s | %s", stage, message, attrs)


@workflow.defn
class CreatePullFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        display_name = _wf_get(file, "display_name", "unknown")
        _wf_log("CreatePullFileMetadata", "Running", filename=display_name)
        return await workflow.execute_activity(
            "create_pull_file_metadata",
            args=[file],
            **_wf_activity_options(TIMEOUT_METADATA, RETRY_POLICY_METADATA),
        )


@workflow.defn
class GetPushFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        display_name = _wf_get(file, "display_name", "unknown")
        _wf_log("GetPushFileMetadata", "Running", filename=display_name)
        return await workflow.execute_activity(
            "get_push_file_metadata",
            args=[file],
            **_wf_activity_options(TIMEOUT_METADATA, RETRY_POLICY_METADATA),
        )


@workflow.defn
class LoadPullFile:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> str:
        display_name = _wf_get(file, "display_name", "unknown")
        _wf_log("LoadPullFile", "Running", filename=display_name)
        return await workflow.execute_activity(
            "load_pull_file",
            args=[file, metadata],
            **_wf_activity_options(TIMEOUT_IO, RETRY_POLICY_IO),
        )


@workflow.defn
class LoadPushFile:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> str:
        display_name = _wf_get(file, "display_name", "unknown")
        _wf_log("LoadPushFile", "Running", filename=display_name)
        return await workflow.execute_activity(
            "load_push_file",
            args=[file, metadata],
            **_wf_activity_options(TIMEOUT_IO, RETRY_POLICY_IO),
        )


@workflow.defn
class InputProcess:
    @workflow.run
    async def run(self, user: Any, input_file: str, metadata: Any) -> Any:
        _wf_log("InputProcess", "Running", input_file=input_file)
        return await workflow.execute_activity(
            "input_process",
            args=[user, input_file, metadata],
            **_wf_activity_options(TIMEOUT_CPU, RETRY_POLICY_CPU),
        )


@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> None:
        display_name = _wf_get(file, "display_name", "unknown")
        _wf_log("OutputProcess", "Running", filename=display_name)
        await workflow.execute_activity(
            "output_process",
            args=[file, metadata, False],
            **_wf_activity_options(TIMEOUT_CPU, RETRY_POLICY_CPU),
        )


@workflow.defn
class FastStoreVectors:
    @workflow.run
    async def run(self, payload):
        _wf_log("FastStoreVectors", "Running")
        return await workflow.execute_activity(
            "fast_store_vectors",
            args=[payload],
            **_wf_activity_options(TIMEOUT_CPU, RETRY_POLICY_CPU),
        )


@workflow.defn
class FastDeleteVectors:
    @workflow.run
    async def run(self, payload):
        _wf_log("FastDeleteVectors", "Running")
        return await workflow.execute_activity(
            "fast_delete_vectors",
            args=[payload],
            **_wf_activity_options(TIMEOUT_FAST_DELETE, RETRY_POLICY_IO),
        )


@workflow.defn
class ProcessFile:
    @workflow.run
    async def run(
        self,
        workflow_id: str,
        file: Any,
        file_index: int,
        io_task_queue: str | None = None,
        cpu_task_queue: str | None = None,
    ) -> dict:
        display_name = _wf_get(file, "display_name", None) or "unknown"
        is_pull = _wf_get(file, "external_path", None) is not None
        provisional_uid = _wf_document_uid(file)
        _wf_log(
            "ProcessFile",
            "Processing started",
            filename=display_name,
            file_index=file_index,
            io_task_queue=io_task_queue,
            cpu_task_queue=cpu_task_queue,
        )

        await workflow.execute_activity(
            "record_current_document",
            args=[workflow_id, provisional_uid, display_name],
            **_wf_activity_options(TIMEOUT_RECORD, RETRY_POLICY_RECORD),
        )

        if is_pull:
            metadata = await workflow.execute_child_workflow(
                CreatePullFileMetadata.run,
                args=[file],
                id=_wf_child_id("CreatePullFileMetadata", file, file_index),
                task_queue=io_task_queue,
            )
            await workflow.execute_activity(
                "record_current_document",
                args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
                **_wf_activity_options(TIMEOUT_RECORD, RETRY_POLICY_RECORD),
            )
            local_file_path = await workflow.execute_child_workflow(
                LoadPullFile.run,
                args=[file, metadata],
                id=_wf_child_id("LoadPullFile", file, file_index),
                task_queue=io_task_queue,
            )
        else:
            metadata = await workflow.execute_child_workflow(
                GetPushFileMetadata.run,
                args=[file],
                id=_wf_child_id("GetPushFileMetadata", file, file_index),
                task_queue=io_task_queue,
            )
            await workflow.execute_activity(
                "record_current_document",
                args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
                **_wf_activity_options(TIMEOUT_RECORD, RETRY_POLICY_RECORD),
            )
            local_file_path = await workflow.execute_child_workflow(
                LoadPushFile.run,
                args=[file, metadata],
                id=_wf_child_id("LoadPushFile", file, file_index),
                task_queue=io_task_queue,
            )

        metadata = await workflow.execute_child_workflow(
            InputProcess.run,
            args=[_wf_get(file, "processed_by"), local_file_path, metadata],
            id=_wf_child_id("InputProcess", file, file_index),
            task_queue=cpu_task_queue,
        )
        await workflow.execute_child_workflow(
            OutputProcess.run,
            args=[file, metadata],
            id=_wf_child_id("OutputProcess", file, file_index),
            task_queue=cpu_task_queue,
        )
        _wf_log("ProcessFile", "Processing completed", filename=display_name, file_index=file_index)
        return {"document_uid": _wf_get(metadata, "document_uid"), "filename": display_name}


@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: Any) -> str:
        pipeline_name = _wf_get(definition, "name", "unknown")
        files = _wf_get(definition, "files", []) or []
        max_parallelism = max(1, int(_wf_get(definition, "max_parallelism", 1) or 1))
        workflow_task_queue = _wf_workflow_task_queue(definition)
        io_task_queue = _wf_io_task_queue(definition)
        cpu_task_queue = _wf_cpu_task_queue(definition)
        workflow_id = workflow.info().workflow_id
        last_document_uid: str | None = None
        last_filename: str | None = None

        _wf_log(
            "Process",
            "Pipeline started",
            pipeline_name=pipeline_name,
            max_parallelism=max_parallelism,
            files=len(files),
            workflow_task_queue=workflow_task_queue,
            io_task_queue=io_task_queue,
            cpu_task_queue=cpu_task_queue,
        )

        try:
            for batch_start in range(0, len(files), max_parallelism):
                batch = files[batch_start : batch_start + max_parallelism]
                handles = []
                for offset, file in enumerate(batch):
                    file_index = batch_start + offset
                    handle = await workflow.start_child_workflow(
                        ProcessFile.run,
                        args=[workflow_id, file, file_index, io_task_queue, cpu_task_queue],
                        id=_wf_child_id("ProcessFile", file, file_index),
                        task_queue=workflow_task_queue,
                    )
                    handles.append(handle)

                for handle in handles:
                    result = await handle
                    if isinstance(result, dict):
                        doc_uid = result.get("document_uid")
                        filename = result.get("filename")
                        if isinstance(doc_uid, str) and doc_uid:
                            last_document_uid = doc_uid
                        if isinstance(filename, str) and filename:
                            last_filename = filename

            await workflow.execute_activity(
                "record_workflow_status",
                args=[workflow_id, "COMPLETED", None, last_document_uid, last_filename],
                **_wf_activity_options(TIMEOUT_RECORD, RETRY_POLICY_RECORD),
            )
            _wf_log("Process", "Pipeline completed", pipeline_name=pipeline_name)
            return "success"
        except Exception as exc:
            error_message = _wf_format_error(exc, "Pipeline processing")
            try:
                await workflow.execute_activity(
                    "record_workflow_status",
                    args=[workflow_id, "FAILED", error_message, last_document_uid, last_filename],
                    **_wf_activity_options(TIMEOUT_RECORD, RETRY_POLICY_RECORD),
                )
            except Exception:
                workflow.logger.exception("[SCHEDULER][Process] Failed to record workflow failure")
            raise
