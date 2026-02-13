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

from __future__ import annotations

import logging
import time
from tempfile import NamedTemporaryFile
from typing import List, Optional

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.processors.output.base_library_output_processor import LibraryDocumentInput, LibraryOutputProcessor
from knowledge_flow_backend.features.scheduler.activities import (
    output_process,
)
from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.pull_files_activities import (
    create_pull_file_metadata,
    pull_input_process,
)
from knowledge_flow_backend.features.scheduler.push_files_activities import (
    get_push_file_metadata,
    push_input_process,
)
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    PipelineDefinition,
)
from knowledge_flow_backend.features.scheduler.workflow_status import (
    WORKFLOW_STATUS_COMPLETED,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_RUNNING,
)

logger = logging.getLogger(__name__)


def _split_file_kinds(definition: PipelineDefinition) -> tuple[bool, bool]:
    has_pull = any(file.is_pull() for file in definition.files)
    has_push = any(file.is_push() for file in definition.files)
    return has_pull, has_push


async def _run_push_ingestion_pipeline(definition: PipelineDefinition) -> str:
    simulated_delay_seconds = 0
    logger.info(
        "Starting local PUSH ingestion pipeline for %d file(s) with simulated delay of %d seconds per file",
        len(definition.files),
        simulated_delay_seconds,
    )

    for file in definition.files:
        logger.info("[SCHEDULER][IN_MEMORY] Processing push file %s via local ingestion pipeline", file.display_name)
        if simulated_delay_seconds > 0:
            time.sleep(simulated_delay_seconds)

        metadata = await get_push_file_metadata(file)
        metadata = await push_input_process(user=file.processed_by, metadata=metadata, input_file="")
        _ = await output_process(file=file, metadata=metadata, accept_memory_storage=True)

    return "success"


async def _run_pull_ingestion_pipeline(definition: PipelineDefinition) -> str:
    simulated_delay_seconds = 0
    logger.info(
        "Starting local PULL ingestion pipeline for %d file(s) with simulated delay of %d seconds per file",
        len(definition.files),
        simulated_delay_seconds,
    )

    for file in definition.files:
        logger.info("[SCHEDULER][IN_MEMORY] Processing pull file %s via local ingestion pipeline", file.external_path)
        if simulated_delay_seconds > 0:
            time.sleep(simulated_delay_seconds)

        metadata = await create_pull_file_metadata(file)
        metadata = await pull_input_process(user=file.processed_by, metadata=metadata)
        _ = await output_process(file=file, metadata=metadata, accept_memory_storage=True)

    return "success"


async def _run_ingestion_pipeline(definition: PipelineDefinition) -> str:
    """
    Local, in-process ingestion pipeline used when Temporal is disabled.

    This mirrors the behavior of the Temporal workflow but executes synchronously
    in a background thread managed by FastAPI's BackgroundTasks.
    """
    has_pull, has_push = _split_file_kinds(definition)
    if has_pull and has_push:
        raise ValueError("Mixed push and pull files are not supported in a single workflow submission.")
    if has_pull:
        return await _run_pull_ingestion_pipeline(definition)
    return await _run_push_ingestion_pipeline(definition)


class InMemoryScheduler(BaseScheduler):
    """
    In-memory implementation of the ingestion workflow client.

    - Registers a workflow_id and associated document_uids.
    - Executes the ingestion pipeline locally via BackgroundTasks.
    """

    def __init__(self, metadata_service):
        super().__init__(metadata_service)
        self._workflow_status_by_id: dict[str, str] = {}
        self._workflow_last_error_by_id: dict[str, str | None] = {}

    @staticmethod
    def _format_exception_message(exc: BaseException) -> str:
        return f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"

    def _set_workflow_state(
        self,
        *,
        workflow_id: str,
        status: str,
        last_error: str | None,
    ) -> None:
        with self._lock:
            self._workflow_status_by_id[workflow_id] = status
            self._workflow_last_error_by_id[workflow_id] = last_error

    async def _run_pipeline_with_status_tracking(self, workflow_id: str, definition: PipelineDefinition) -> None:
        try:
            await _run_ingestion_pipeline(definition)
        except Exception as exc:
            error_message = self._format_exception_message(exc)
            logger.error(
                "[SCHEDULER][IN_MEMORY] Pipeline workflow_id=%s failed: %s",
                workflow_id,
                error_message,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            self._set_workflow_state(
                workflow_id=workflow_id,
                status=WORKFLOW_STATUS_FAILED,
                last_error=error_message,
            )
            return

        self._set_workflow_state(
            workflow_id=workflow_id,
            status=WORKFLOW_STATUS_COMPLETED,
            last_error=None,
        )

    async def start_document_processing(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        handle = self._register_workflow(user, definition)
        workflow_id = handle.workflow_id
        self._set_workflow_state(
            workflow_id=workflow_id,
            status=WORKFLOW_STATUS_RUNNING,
            last_error=None,
        )

        # In request/response endpoints we prefer FastAPI/Starlette BackgroundTasks.
        # In streaming endpoints, callers can pass background_tasks=None to run inline.
        if background_tasks is not None:
            background_tasks.add_task(self._run_pipeline_with_status_tracking, workflow_id, definition)
        else:
            # Fallback for non-HTTP contexts; this will block the caller.
            logger.warning("[SCHEDULER][IN_MEMORY] BackgroundTasks not provided, running ingestion pipeline synchronously")
            await self._run_pipeline_with_status_tracking(workflow_id, definition)

        return handle

    async def start_library_processing(
        self,
        user: KeycloakUser,
        library_tag: str,
        processor_path: str,
        document_uids: Optional[List[str]] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        """
        Local, in-process library processor runner.
        """
        # Collect metadata for the library tag
        docs = await self._metadata_service.get_document_metadata_in_tag(user, library_tag)
        if document_uids:
            doc_uid_set = set(document_uids)
            docs = [d for d in docs if d.document_uid in doc_uid_set]

        handle = self._register_workflow_for_uids(user, [d.document_uid for d in docs])

        if background_tasks is not None:
            background_tasks.add_task(self._run_library_processor, processor_path, library_tag, docs)
        else:
            logger.warning("[SCHEDULER][IN_MEMORY] BackgroundTasks not provided, running library processor synchronously")
            self._run_library_processor(processor_path, library_tag, docs)

        return handle

    def _run_library_processor(self, processor_path: str, library_tag: str, docs: List[DocumentMetadata]) -> None:
        logger.info(
            "[SCHEDULER][IN_MEMORY] Running library processor %s for library %s (%d docs)",
            processor_path,
            library_tag,
            len(docs),
        )

        processor_cls = self._dynamic_import_processor(processor_path)
        if not issubclass(processor_cls, LibraryOutputProcessor):
            raise TypeError(f"{processor_path} is not a LibraryOutputProcessor")

        processor: LibraryOutputProcessor = processor_cls()
        context = ApplicationContext.get_instance()
        content_store = context.get_content_store()

        inputs: List[LibraryDocumentInput] = []
        for meta in docs:
            tmp_path = None
            # Try to fetch markdown preview; fall back to CSV table.
            for candidate in (f"{meta.document_uid}/output/output.md", f"{meta.document_uid}/output/table.csv"):
                try:
                    data = content_store.get_preview_bytes(candidate)
                    suffix = ".md" if candidate.endswith(".md") else ".csv"
                    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(data)
                        tmp_path = tmp.name
                    break
                except FileNotFoundError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to fetch preview %s for %s: %s", candidate, meta.document_uid, exc)
                    continue

            if not tmp_path:
                logger.info("No preview/table found for %s; skipping", meta.document_uid)
                continue

            inputs.append(LibraryDocumentInput(file_path=tmp_path, metadata=meta))

        if not inputs:
            logger.info("[SCHEDULER][IN_MEMORY] No inputs available for library %s; skipping processor", library_tag)
            return

        try:
            updated_metadatas = processor.process_library(documents=inputs, library_tag=library_tag)
            for md in updated_metadatas:
                try:
                    self._metadata_service.metadata_store.save_metadata(md)  # type: ignore[attr-defined]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to persist metadata for %s: %s", md.document_uid, exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[SCHEDULER][IN_MEMORY] Library processor %s failed: %s", processor_path, exc)

    def _dynamic_import_processor(self, class_path: str):
        module_name, class_name = class_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)

    async def store_fast_vectors(self, payload: dict) -> dict:
        docs_payload = payload.get("documents") or []
        if not isinstance(docs_payload, list):
            raise ValueError("payload.documents must be a list")

        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        vector_store = context.get_create_vector_store(embedder)

        docs: list[Document] = []
        for item in docs_payload:
            if not isinstance(item, dict):
                continue
            page_content = str(item.get("page_content") or "")
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            docs.append(Document(page_content=page_content, metadata=metadata))

        if not docs:
            return {"chunks": 0}

        ids = vector_store.add_documents(docs)
        chunks = len(ids) if isinstance(ids, (list, tuple, set)) else len(docs)
        return {"chunks": chunks}

    async def delete_fast_vectors(self, payload: dict) -> dict:
        document_uid = payload.get("document_uid")
        if not document_uid:
            raise ValueError("payload.document_uid is required")

        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        vector_store = context.get_create_vector_store(embedder)
        vector_store.delete_vectors_for_document(document_uid=document_uid)
        return {"status": "ok", "document_uid": document_uid}

    async def get_workflow_execution_status(self, workflow_id: str) -> Optional[str]:
        with self._lock:
            return self._workflow_status_by_id.get(workflow_id)

    async def get_workflow_last_error(self, workflow_id: str) -> Optional[str]:
        with self._lock:
            return self._workflow_last_error_by_id.get(workflow_id)
