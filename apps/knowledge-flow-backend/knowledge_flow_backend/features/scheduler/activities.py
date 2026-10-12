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

import asyncio
import logging
import pathlib
import tempfile
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from temporalio import activity, exceptions

from knowledge_flow_backend.features.scheduler.activity_utils import raise_if_document_deleted, to_thread_with_heartbeat
from knowledge_flow_backend.features.scheduler.kpi_utils import (
    emit_temporal_activity_result_kpis,
)
from knowledge_flow_backend.features.scheduler.logging_context import ingestion_activity
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


@activity.defn
@ingestion_activity
async def output_process(file: FileToProcess, metadata: DocumentMetadata, accept_memory_storage: bool = False) -> DocumentMetadata:
    """Normal per-document ingestion output stage — persists metadata through
    the permission-checked `save_metadata` (the calling user must hold
    `TagPermission.UPDATE` on every tag the document carries). Used by the
    ordinary `OutputProcess` workflow."""
    from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service

    ingestion_service = get_ingestion_service()
    return await _output_process_impl(
        file,
        metadata,
        accept_memory_storage,
        ingestion_service=ingestion_service,
        persist_progress=ingestion_service.persist_progress,
    )


async def _output_process_impl(
    file: FileToProcess,
    metadata: DocumentMetadata,
    accept_memory_storage: bool,
    *,
    ingestion_service: Any,
    persist_progress: Callable[..., Awaitable[bool]],
) -> DocumentMetadata:
    logger = activity.logger
    started_at = asyncio.get_running_loop().time()
    logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] Starting uid={metadata.document_uid}")

    from knowledge_flow_backend.application_context import ApplicationContext

    output_stage: ProcessingStage | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"doc-{metadata.document_uid}-") as tmpdir:
            working_dir = pathlib.Path(tmpdir)
            output_dir = working_dir / "output"
            document_name = metadata.document_name

            # For both push and pull, restore what was saved (input/output).
            # to_thread_with_heartbeat, not bare to_thread, here and for
            # process_output below — and not only for progress reporting: the
            # heartbeat responses are ALSO the channel Temporal uses to tell a
            # running activity it was cancelled. A bare to_thread never
            # heartbeats, so this activity sailed through a user's cancel and
            # vectorized 4038 chunks for a document already deleted (#2315).
            # The wrapper additionally scopes a cancellation signal the worker
            # thread checks between batches (`common/cancellation.py`).
            await to_thread_with_heartbeat(
                ingestion_service.get_local_copy,
                file.processed_by,
                metadata,
                working_dir,
                heartbeat_details={"stage": "output_restore", "document_uid": metadata.document_uid},
            )
            output_dir.mkdir(parents=True, exist_ok=True)

            app_context = ApplicationContext.get_instance()
            is_tabular_document = app_context.is_tabular_file(document_name)
            is_spreadsheet_document = app_context.is_spreadsheet_file(document_name)
            if is_tabular_document:
                output_stage = ProcessingStage.SQL_INDEXED
                file_name_for_processing = document_name
            elif is_spreadsheet_document:
                # Spreadsheets already produced their markdown preview at input
                # time; the output stage only registers the per-table Parquet
                # artifacts listed in the sidecar next to output.md. Keeping the
                # original document name routes the pipeline to the spreadsheet
                # output processors (the pipeline itself resolves output.md).
                output_stage = ProcessingStage.SQL_INDEXED
                file_name_for_processing = document_name
            else:
                preview_file = await asyncio.to_thread(ingestion_service.get_preview_file, file.processed_by, metadata, output_dir)
                output_stage = ProcessingStage.VECTORIZED
                file_name_for_processing = preview_file.name

            metadata.set_stage_status(output_stage, ProcessingStatus.IN_PROGRESS)
            raise_if_document_deleted(await persist_progress(file.processed_by, metadata=metadata), metadata.document_uid)

            if output_stage == ProcessingStage.VECTORIZED:
                from knowledge_flow_backend.common.structures import InMemoryVectorStorage

                vector_store = ApplicationContext.get_instance().get_config().storage.vector_store
                if isinstance(vector_store, InMemoryVectorStorage) and not accept_memory_storage:
                    raise exceptions.ApplicationError(
                        "❌ Vectorization from temporal activity is not allowed with an in-memory vector store. Please configure a persistent vector store like OpenSearch.",
                        non_retryable=True,
                    )

            from knowledge_flow_backend.features.scheduler.fault_injection import inject_ingestion_fault

            await inject_ingestion_fault(stage="indexing", document_name=metadata.document_name, document_uid=metadata.document_uid)

            # Proceed with the output processing (vectorization / SQL indexing —
            # the longest-running, most expensive stage; see the comment above).
            metadata = await to_thread_with_heartbeat(
                ingestion_service.process_output,
                file.processed_by,
                file_name_for_processing,
                output_dir,
                metadata,
                file.profile,
                heartbeat_details={"stage": "output_process", "document_uid": metadata.document_uid},
                # The vectorization loop checks cancellation checkpoints, so on
                # cancel the activity waits (bounded) for the thread's last
                # write before letting the workflow purge — without this the
                # purge raced the still-writing thread (#2315).
                drain_on_cancel=True,
            )

            # Save the updated metadata
            await persist_progress(file.processed_by, metadata=metadata)

        logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] completed uid={metadata.document_uid}")
        emit_temporal_activity_result_kpis(
            phase="output",
            started_at_monotonic=started_at,
            metadata=metadata,
            file=file,
            status="success",
        )
        return metadata
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
        stage = output_stage or ProcessingStage.PREVIEW_READY
        metadata.mark_stage_error(stage, error_message)
        try:
            await persist_progress(file.processed_by, metadata=metadata)
        except Exception:
            logger.exception(
                "[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] failed to persist error state uid=%s",
                metadata.document_uid,
                exc_info=True,
            )
        logger.exception(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] failed uid={metadata.document_uid}", exc_info=True)
        emit_temporal_activity_result_kpis(
            phase="output",
            started_at_monotonic=started_at,
            metadata=metadata,
            file=file,
            status="error",
            exc=exc,
        )
        raise


@activity.defn
async def emit_ingestion_task_event(
    task_id: str,
    state: str,
    step: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    processed: int = 0,
    total: int = 1,
    failed: int = 0,
    document_uid: str | None = None,
    display_name: str | None = None,
) -> None:
    """Emit a TaskEvent for an ingestion task_run row (OPS-04)."""
    from fred_core.tasks.models import IngestionDetail, IngestionTaskEvent, TaskState, TaskTarget

    from knowledge_flow_backend.application_context import ApplicationContext

    detail = IngestionDetail(
        processed=processed,
        total=total,
        failed=failed,
        preview=0,
        vectorized=0,
        sql_indexed=0,
    )
    target: TaskTarget | None = None
    if document_uid:
        target = TaskTarget(type="document", id=document_uid, label=display_name or document_uid)
    event = IngestionTaskEvent(
        task_id=task_id,
        state=TaskState(state),
        seq=0,  # auto-incremented by TaskStore.record_event
        timestamp=datetime.now(tz=timezone.utc),
        step=step,
        progress=progress,
        error=error,
        detail=detail,
        target=target,
    )
    task_service = ApplicationContext.get_instance().get_task_service()
    await task_service.record(event)

    # The task row is not what the library renders -- the document's processing
    # stages are, and a terminal task leaves them stale: `in_progress` forever
    # after an executor-side failure (#2279), or pointing at a document the user
    # asked to stop building (#2315). Repair the document through the one policy
    # both this compensation and API-side reconciliation share. Running it here
    # too is what makes the list update within seconds; reconciliation is the
    # backstop for when no worker is around to run this at all. Best-effort by
    # contract -- it must never mask the state being reported.
    if TaskState(state).is_terminal and document_uid:
        from knowledge_flow_backend.features.scheduler.document_failure import repair_document_after_terminal

        run = await task_service.get_run(task_id)
        if run is not None and run.state != state:
            return  # A different terminal outcome was already persisted.
        await repair_document_after_terminal(
            document_uid,
            TaskState(state),
            error or "Processing failed",
            created_by=run.created_by if run is not None else None,
        )


@activity.defn
async def fast_store_vectors(payload: dict) -> dict:
    """
    Store fast-ingest chunks into the configured vector store.
    Payload shape:
      {
        "documents": [{"page_content": str, "metadata": dict}, ...]
      }
    """
    logger = activity.logger
    docs_payload = payload.get("documents") or []
    if not isinstance(docs_payload, list):
        raise ValueError("payload.documents must be a list")

    from langchain_core.documents import Document

    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)

    docs = []
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
    logger.info("[SCHEDULER][ACTIVITY][FAST_STORE_VECTORS] Stored %d chunks", chunks)
    return {"chunks": chunks}


@activity.defn
async def fast_delete_vectors(payload: dict) -> dict:
    """
    Delete all vectors for a fast-ingested document.
    Payload: {"document_uid": "<uid>"}
    """
    document_uid = payload.get("document_uid")
    if not document_uid:
        raise ValueError("payload.document_uid is required")

    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)
    vector_store.delete_vectors_for_document(document_uid=document_uid)
    activity.logger.info("[SCHEDULER][ACTIVITY][FAST_DELETE_VECTORS] Deleted vectors for %s", document_uid)
    return {"status": "ok", "document_uid": document_uid}
