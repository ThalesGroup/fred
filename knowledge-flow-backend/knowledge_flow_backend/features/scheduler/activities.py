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

from temporalio import activity, exceptions

from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


@activity.defn
async def output_process(file: FileToProcess, metadata: DocumentMetadata, accept_memory_storage: bool = False) -> DocumentMetadata:
    logger = activity.logger
    logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] Starting uid={metadata.document_uid}")

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.ingestion.ingestion_service import IngestionService

    ingestion_service = IngestionService()

    output_stage: ProcessingStage | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"doc-{metadata.document_uid}-") as tmpdir:
            working_dir = pathlib.Path(tmpdir)
            output_dir = working_dir / "output"

            # For both push and pull, restore what was saved (input/output)
            await asyncio.to_thread(ingestion_service.get_local_copy, file.processed_by, metadata, working_dir)

            # Locate preview file
            preview_file = await asyncio.to_thread(ingestion_service.get_preview_file, file.processed_by, metadata, output_dir)
            if ApplicationContext.get_instance().is_tabular_file(preview_file.name):
                output_stage = ProcessingStage.SQL_INDEXED
            else:
                output_stage = ProcessingStage.VECTORIZED

            metadata.set_stage_status(output_stage, ProcessingStatus.IN_PROGRESS)
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

            if not ApplicationContext.get_instance().is_tabular_file(preview_file.name):
                from knowledge_flow_backend.common.structures import InMemoryVectorStorage

                vector_store = ApplicationContext.get_instance().get_config().storage.vector_store
                if isinstance(vector_store, InMemoryVectorStorage) and not accept_memory_storage:
                    raise exceptions.ApplicationError(
                        "❌ Vectorization from temporal activity is not allowed with an in-memory vector store. Please configure a persistent vector store like OpenSearch.",
                        non_retryable=True,
                    )

            # Proceed with the output processing
            metadata = await asyncio.to_thread(
                ingestion_service.process_output,
                file.processed_by,
                preview_file.name,
                output_dir,
                metadata,
            )

            # Save the updated metadata
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

        logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] completed uid={metadata.document_uid}")
        return metadata
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc).strip() or 'No error message'}"
        stage = output_stage or ProcessingStage.PREVIEW_READY
        metadata.mark_stage_error(stage, error_message)
        try:
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)
        except Exception:
            logger.exception(
                "[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] failed to persist error state uid=%s",
                metadata.document_uid,
                exc_info=True,
            )
        logger.exception(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] failed uid={metadata.document_uid}", exc_info=True)
        raise


@activity.defn
async def record_current_document(
    workflow_id: str,
    document_uid: str | None,
    filename: str | None,
) -> None:
    logger = activity.logger
    logger.info(
        "[SCHEDULER][ACTIVITY][RECORD_CURRENT_DOCUMENT] workflow_id=%s document_uid=%s",
        workflow_id,
        document_uid,
    )
    from knowledge_flow_backend.application_context import ApplicationContext

    store = ApplicationContext.get_instance().get_task_store()
    await store.upsert_current_document(
        workflow_id=workflow_id,
        document_uid=document_uid,
        filename=filename,
    )


@activity.defn
async def record_workflow_status(
    workflow_id: str,
    status: str,
    error: str | None = None,
    document_uid: str | None = None,
    filename: str | None = None,
) -> None:
    logger = activity.logger
    logger.info(
        "[SCHEDULER][ACTIVITY][RECORD_WORKFLOW_STATUS] workflow_id=%s status=%s",
        workflow_id,
        status,
    )
    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.scheduler.store.task_structures import WorkflowTaskStatus

    parsed_status = status if isinstance(status, WorkflowTaskStatus) else WorkflowTaskStatus(status)
    store = ApplicationContext.get_instance().get_task_store()
    if document_uid or filename:
        await store.upsert_current_document(
            workflow_id=workflow_id,
            document_uid=document_uid,
            filename=filename,
        )
    await store.update_status(
        workflow_id=workflow_id,
        status=parsed_status,
        last_error=error,
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
