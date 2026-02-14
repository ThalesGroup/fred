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


def _wf_is_pull(file: Any) -> bool:
    return _wf_get(file, "external_path", None) is not None


def _wf_child_id(prefix: str, file: Any, file_index: int) -> str:
    """
    Build a deterministic, collision-resistant child workflow id.
    """
    display_name = _wf_get(file, "display_name", None) or "unknown"
    doc_uid = _wf_document_uid(file) or f"idx-{file_index}"
    raw = f"{prefix}|{file_index}|{display_name}|{doc_uid}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{prefix}-{file_index}-{digest}"


def _wf_file_kind_summary(files: list[Any]) -> tuple[bool, bool]:
    has_pull = any(_wf_is_pull(file) for file in files)
    has_push = any(not _wf_is_pull(file) for file in files)
    return has_pull, has_push


def _wf_profile_value(file: Any) -> str | None:
    raw = _wf_get(file, "profile", None)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    value = getattr(raw, "value", None)
    if isinstance(value, str):
        return value
    if isinstance(raw, (list, tuple)) and raw and all(isinstance(item, str) and len(item) == 1 for item in raw):
        return "".join(raw)
    return str(raw)


async def _wf_run_parent_pipeline(
    *,
    definition: Any,
    child_workflow_run,
    child_prefix: str,
) -> str:
    pipeline_name = _wf_get(definition, "name", "unknown")
    files = _wf_get(definition, "files", []) or []
    max_parallelism = max(1, int(_wf_get(definition, "max_parallelism", 1) or 1))
    workflow.logger.info("[SCHEDULER] Ingesting pipeline: %s", pipeline_name)
    workflow_id = workflow.info().workflow_id
    last_document_uid: str | None = None
    last_filename: str | None = None

    try:
        for batch_start in range(0, len(files), max_parallelism):
            batch = files[batch_start : batch_start + max_parallelism]
            handles = []
            for offset, file in enumerate(batch):
                file_index = batch_start + offset
                handle = await workflow.start_child_workflow(
                    child_workflow_run,
                    args=[workflow_id, file, file_index],
                    id=_wf_child_id(child_prefix, file, file_index),
                    retry_policy=RetryPolicy(maximum_attempts=1),
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
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return "success"
    except Exception as exc:
        error_message = str(exc).strip() or "No error message"
        try:
            await workflow.execute_activity(
                "record_workflow_status",
                args=[workflow_id, "FAILED", error_message, last_document_uid, last_filename],
                schedule_to_close_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception:
            workflow.logger.exception("[SCHEDULER] Failed to record workflow failure", exc_info=True)
        raise


@workflow.defn
class CreatePullFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        workflow.logger.info("[SCHEDULER] CreatePullFileMetadata: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity("create_pull_file_metadata", args=[file], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1))


@workflow.defn
class GetPushFileMetadata:
    @workflow.run
    async def run(self, file: Any) -> Any:
        workflow.logger.info("[SCHEDULER] GetPushFileMetadata: %s", _wf_get(file, "display_name", "unknown"))
        return await workflow.execute_activity("get_push_file_metadata", args=[file], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1))


@workflow.defn
class PullInputProcess:
    @workflow.run
    async def run(self, user: Any, metadata: Any, profile: Any = None) -> Any:
        workflow.logger.info("[SCHEDULER] PullInputProcess")
        return await workflow.execute_activity(
            "pull_input_process",
            args=[user, metadata, profile],
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


@workflow.defn
class PushInputProcess:
    @workflow.run
    async def run(self, user: Any, input_file: str, metadata: Any, profile: Any = None) -> Any:
        workflow.logger.info("[SCHEDULER] PushInputProcess: %s", input_file or "<resolve-on-worker>")
        return await workflow.execute_activity(
            "push_input_process",
            args=[user, metadata, input_file, profile],
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


@workflow.defn
class OutputProcess:
    @workflow.run
    async def run(self, file: Any, metadata: Any) -> None:
        workflow.logger.info("[SCHEDULER] OutputProcess: %s", _wf_get(file, "display_name", "unknown"))
        await workflow.execute_activity("output_process", args=[file, metadata, False], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1))


@workflow.defn
class FastStoreVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity("fast_store_vectors", args=[payload], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1))


@workflow.defn
class FastDeleteVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity("fast_delete_vectors", args=[payload], schedule_to_close_timeout=timedelta(minutes=1), retry_policy=RetryPolicy(maximum_attempts=1))


@workflow.defn
class ProcessPullFile:
    @workflow.run
    async def run(self, workflow_id: str, file: Any, file_index: int) -> dict:
        display_name = _wf_get(file, "display_name", None) or "unknown"
        if not _wf_is_pull(file):
            raise ValueError(f"ProcessPullFile received a push file: {display_name}")

        provisional_uid = _wf_document_uid(file)

        await workflow.execute_activity(
            "record_current_document", args=[workflow_id, provisional_uid, display_name], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1)
        )

        workflow.logger.info("[SCHEDULER] Processing pull file: %s", display_name)
        metadata = await workflow.execute_child_workflow(
            CreatePullFileMetadata.run,
            args=[file],
            id=_wf_child_id("CreatePullFileMetadata", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.execute_activity(
            "record_current_document",
            args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        metadata = await workflow.execute_child_workflow(
            PullInputProcess.run,
            args=[_wf_get(file, "processed_by"), metadata, _wf_profile_value(file)],
            id=_wf_child_id("PullInputProcess", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.execute_child_workflow(
            OutputProcess.run,
            args=[file, metadata],
            id=_wf_child_id("OutputProcess", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        workflow.logger.info("[SCHEDULER] Completed file: %s", display_name)
        return {"document_uid": _wf_get(metadata, "document_uid"), "filename": display_name}


@workflow.defn
class ProcessPushFile:
    @workflow.run
    async def run(self, workflow_id: str, file: Any, file_index: int) -> dict:
        display_name = _wf_get(file, "display_name", None) or "unknown"
        if _wf_is_pull(file):
            raise ValueError(f"ProcessPushFile received a pull file: {display_name}")

        provisional_uid = _wf_document_uid(file)

        await workflow.execute_activity(
            "record_current_document", args=[workflow_id, provisional_uid, display_name], schedule_to_close_timeout=timedelta(hours=1), retry_policy=RetryPolicy(maximum_attempts=1)
        )

        workflow.logger.info("[SCHEDULER] Processing push file: %s", display_name)
        metadata = await workflow.execute_child_workflow(
            GetPushFileMetadata.run,
            args=[file],
            id=_wf_child_id("GetPushFileMetadata", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.execute_activity(
            "record_current_document",
            args=[workflow_id, _wf_get(metadata, "document_uid"), display_name],
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        metadata = await workflow.execute_child_workflow(
            PushInputProcess.run,
            args=[_wf_get(file, "processed_by"), "", metadata, _wf_profile_value(file)],
            id=_wf_child_id("PushInputProcess", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.execute_child_workflow(
            OutputProcess.run,
            args=[file, metadata],
            id=_wf_child_id("OutputProcess", file, file_index),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        workflow.logger.info("[SCHEDULER] Completed file: %s", display_name)
        return {"document_uid": _wf_get(metadata, "document_uid"), "filename": display_name}


@workflow.defn
class ProcessPush:
    @workflow.run
    async def run(self, definition: Any) -> str:
        files = _wf_get(definition, "files", []) or []
        has_pull, has_push = _wf_file_kind_summary(files)
        if has_pull:
            raise ValueError("ProcessPush received at least one pull file. Submit push and pull in separate workflow requests.")
        if not has_push and files:
            raise ValueError("ProcessPush received files but none are recognized as push.")
        return await _wf_run_parent_pipeline(
            definition=definition,
            child_workflow_run=ProcessPushFile.run,
            child_prefix="ProcessPushFile",
        )


@workflow.defn
class ProcessPull:
    @workflow.run
    async def run(self, definition: Any) -> str:
        files = _wf_get(definition, "files", []) or []
        has_pull, has_push = _wf_file_kind_summary(files)
        if has_push:
            raise ValueError("ProcessPull received at least one push file. Submit push and pull in separate workflow requests.")
        if not has_pull and files:
            raise ValueError("ProcessPull received files but none are recognized as pull.")
        return await _wf_run_parent_pipeline(
            definition=definition,
            child_workflow_run=ProcessPullFile.run,
            child_prefix="ProcessPullFile",
        )
