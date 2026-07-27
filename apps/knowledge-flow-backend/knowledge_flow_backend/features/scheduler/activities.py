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
from datetime import datetime, timezone

from fred_core.documents.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from pydantic import BaseModel
from temporalio import activity, exceptions

from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.scheduler.kpi_utils import (
    emit_temporal_activity_result_kpis,
)
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


@activity.defn
async def output_process(file: FileToProcess, metadata: DocumentMetadata, accept_memory_storage: bool = False) -> DocumentMetadata:
    logger = activity.logger
    started_at = asyncio.get_running_loop().time()
    logger.info(f"[SCHEDULER][ACTIVITY][OUTPUT_PROCESS] Starting uid={metadata.document_uid}")

    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service

    ingestion_service = get_ingestion_service()

    output_stage: ProcessingStage | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"doc-{metadata.document_uid}-") as tmpdir:
            working_dir = pathlib.Path(tmpdir)
            output_dir = working_dir / "output"
            document_name = metadata.document_name

            # For both push and pull, restore what was saved (input/output)
            await asyncio.to_thread(ingestion_service.get_local_copy, file.processed_by, metadata, working_dir)
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
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

            if output_stage == ProcessingStage.VECTORIZED:
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
                file_name_for_processing,
                output_dir,
                metadata,
                file.profile,
            )

            # Save the updated metadata
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)

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
            await ingestion_service.save_metadata(file.processed_by, metadata=metadata)
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


# ── MIGR-07: corpus re-vectorization ──────────────────────────────────────────
# Thin activities over the existing ingestion/vector-store building blocks
# (RFC docs/swift/rfc/CORPUS-REVECTORIZE-RFC.md §2-3). No new business logic:
# these only resolve scope, read chunk counts, delete vectors, and assemble the
# `FileToProcess`/`DocumentMetadata` pair that `output_process` already knows how
# to re-vectorize from stored content.


class RevectorizePreparedFile(BaseModel):
    """Bundle handed from `prepare_revectorize_file` to the `output_process` activity."""

    file: FileToProcess
    metadata: DocumentMetadata


@activity.defn
async def list_documents_in_scope(scope: dict) -> list[str]:
    """
    Resolve a `CorpusScopeV1`-shaped dict (as produced by `.model_dump()`) to the
    document_uids it covers.

    `document_uids` wins outright (already a concrete list). Otherwise resolves via
    `tag_ids` / `source_tag` against the raw metadata store — intentionally NOT via
    `MetadataService`'s per-user READ filtering: the scope was already authorized at
    the platform/team level in `corpus_manager_controller._authorize_scope`
    (CAN_MANAGE_PLATFORM for a `source_tag`-only scope, per-tag/per-document ReBAC
    checks otherwise), so re-filtering by the caller's individual grants here would
    incorrectly narrow a platform-wide scope back down to "documents I can read".
    """
    document_uids = list(scope.get("document_uids") or [])
    if document_uids:
        return list(dict.fromkeys(document_uids))

    filters: dict = {}
    tag_ids = scope.get("tag_ids") or []
    if tag_ids:
        filters["tag_ids"] = list(tag_ids)
    source_tag = scope.get("source_tag")
    if source_tag:
        filters["source_tag"] = source_tag

    if not filters:
        raise ValueError("Revectorize scope must resolve to document_uids, tag_ids, or source_tag.")

    from knowledge_flow_backend.application_context import ApplicationContext

    metadata_store = ApplicationContext.get_instance().get_metadata_store()
    docs = await metadata_store.get_all_metadata(filters)
    activity.logger.info("[SCHEDULER][ACTIVITY][LIST_DOCUMENTS_IN_SCOPE] resolved %d document(s) for filters=%s", len(docs), filters)
    return [d.document_uid for d in docs]


@activity.defn
async def get_chunk_count(document_uid: str) -> int:
    """Return the vector chunk count for one document (0 if the store can't report it)."""
    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)
    if not hasattr(vector_store, "get_document_chunk_count"):
        return 0
    try:
        return int(vector_store.get_document_chunk_count(document_uid=document_uid))  # type: ignore[attr-defined]
    except Exception:
        activity.logger.warning("[SCHEDULER][ACTIVITY][GET_CHUNK_COUNT] failed for %s", document_uid, exc_info=True)
        return 0


@activity.defn
async def delete_vectors(document_uid: str) -> None:
    """Delete all vector chunks for one document ahead of a full re-vectorize."""
    from knowledge_flow_backend.application_context import ApplicationContext

    context = ApplicationContext.get_instance()
    embedder = context.get_embedder()
    vector_store = context.get_create_vector_store(embedder)
    vector_store.delete_vectors_for_document(document_uid=document_uid)
    activity.logger.info("[SCHEDULER][ACTIVITY][DELETE_VECTORS] Deleted vectors for %s", document_uid)


@activity.defn
async def mark_document_vectorized(document_uid: str, user: dict) -> None:
    """Mark VECTORIZED done for a document whose vectors were left untouched.

    Companion to the revectorize workflow's incremental skip
    (`_wf_should_skip_revectorize`): skipping re-embedding never called
    `output_process`, so the metadata's `VECTORIZED` stage stayed whatever the
    kea-import stage reset (`_reset_transported_stages`) left it at —
    `NOT_STARTED`, even though `get_chunk_count` just proved vectors exist.
    Best-effort: a document that vanished between the count check and this
    call is not this activity's problem to raise about.
    """
    from fred_core import KeycloakUser

    from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service

    keycloak_user = KeycloakUser.model_validate(user)
    ingestion_service = get_ingestion_service()
    metadata = await ingestion_service.get_metadata(keycloak_user, document_uid)
    if metadata is None:
        activity.logger.warning("[SCHEDULER][ACTIVITY][MARK_DOCUMENT_VECTORIZED] %s not found, nothing to mark", document_uid)
        return
    metadata.mark_stage_done(ProcessingStage.VECTORIZED)
    await ingestion_service.save_metadata(keycloak_user, metadata=metadata)
    activity.logger.info("[SCHEDULER][ACTIVITY][MARK_DOCUMENT_VECTORIZED] %s marked VECTORIZED (vectors pre-existed)", document_uid)


@activity.defn
async def prepare_revectorize_file(document_uid: str, user: dict) -> RevectorizePreparedFile:
    """
    Assemble the `(FileToProcess, DocumentMetadata)` pair `output_process` needs,
    from a document_uid alone — pure assembly, no new business logic.

    The original ingestion profile isn't recorded on `DocumentMetadata`, so this
    defaults to `IngestionProcessingProfile.medium` (the platform default).
    """
    from fred_core import KeycloakUser

    from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service

    keycloak_user = KeycloakUser.model_validate(user)
    ingestion_service = get_ingestion_service()
    metadata = await ingestion_service.get_metadata(keycloak_user, document_uid)
    if metadata is None:
        raise exceptions.ApplicationError(
            f"Document '{document_uid}' not found for revectorize.",
            non_retryable=True,
        )
    if not metadata.source.source_tag:
        raise exceptions.ApplicationError(
            f"Document '{document_uid}' has no source_tag recorded; cannot re-vectorize.",
            non_retryable=True,
        )

    file = FileToProcess(
        source_tag=metadata.source.source_tag,
        document_uid=document_uid,
        display_name=metadata.document_name,
        profile=IngestionProcessingProfile.medium,
        processed_by=keycloak_user,
    )
    return RevectorizePreparedFile(file=file, metadata=metadata)
