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

import asyncio
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
    create_pull_file_metadata,
    get_push_file_metadata,
    input_process,
    load_pull_file,
    load_push_file,
    output_process,
)
from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import (
    PipelineDefinition,
)

logger = logging.getLogger(__name__)


async def _run_ingestion_pipeline(definition: PipelineDefinition) -> str:
    """
    Local, in-process ingestion pipeline used when Temporal is disabled.

    This mirrors the behavior of the Temporal workflow but executes synchronously
    in a background thread managed by FastAPI's BackgroundTasks.
    """
    # Simulate slower per-file processing so that UI progress indicators remain
    # visible during local development/demo.
    simulated_delay_seconds = 0
    logger.info(
        "Starting local ingestion pipeline for %d file(s) with simulated delay of %d seconds per file",
        len(definition.files),
        simulated_delay_seconds,
    )

    for file in definition.files:
        logger.info("[SCHEDULER][IN_MEMORY] Processing file %s (pull=%s) via local ingestion pipeline", file.external_path, file.is_pull())

        if simulated_delay_seconds > 0:
            time.sleep(simulated_delay_seconds)

        if file.is_pull():
            metadata = await create_pull_file_metadata(file)
            local_file_path = await load_pull_file(file, metadata)
        else:
            metadata = await get_push_file_metadata(file)
            local_file_path = await load_push_file(file, metadata)

        metadata = await input_process(user=file.processed_by, input_file=local_file_path, metadata=metadata)
        _ = await output_process(file=file, metadata=metadata, accept_memory_storage=True)

    return "success"


def _log_pipeline_task_result(task: asyncio.Task[str]) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.warning("[SCHEDULER][IN_MEMORY] Pipeline task was cancelled")
        return
    if exc is not None:
        logger.exception("[SCHEDULER][IN_MEMORY] Pipeline task failed: %s", exc)


class InMemoryScheduler(BaseScheduler):
    """
    In-memory implementation of the ingestion workflow client.

    - Registers a workflow_id and associated document_uids.
    - Executes the ingestion pipeline locally via BackgroundTasks.
    """

    async def start_document_processing(
        self,
        user: KeycloakUser,
        definition: PipelineDefinition,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> WorkflowHandle:
        handle = self._register_workflow(user, definition)

        # IMPORTANT: do not rely on FastAPI BackgroundTasks here.
        # For streaming responses, BackgroundTasks run only after response completion,
        # which can deadlock progress polling.
        if background_tasks is not None:
            task = asyncio.create_task(_run_ingestion_pipeline(definition))
            task.add_done_callback(_log_pipeline_task_result)
        else:
            # Fallback for non-HTTP contexts; this will block the caller.
            logger.warning("[SCHEDULER][IN_MEMORY] BackgroundTasks not provided, running ingestion pipeline synchronously")
            await _run_ingestion_pipeline(definition)

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
