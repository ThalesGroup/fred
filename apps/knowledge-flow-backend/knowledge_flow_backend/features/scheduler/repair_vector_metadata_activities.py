# Copyright Thales 2026
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

"""
Activities for the vector-metadata repair action ("3a — Réparer uniquement", #2234).

Kea-restored documents can have real vectors in OpenSearch and real content in the
content store while Postgres still reads `processing.stages.vector = not_started`
(the import deliberately resets it, since embeddings aren't transported by the
bundle). 3a repairs exactly that mismatch: a document is only ever flagged `done`
here after both its vectors and its content have been positively confirmed to
exist -- never a re-embed, never a delete, never a content read.

Structural safety guarantee: nothing in this module imports or calls
`delete_vectors`, `prepare_revectorize_file`, `output_process`/`output_process_trusted`,
`get_embedder`, `get_create_vector_store`, `OpenSearchVectorStoreAdapter` (whose
`__init__` calls `ensure_ready()`, which calls the embedder and can create/update
the index, mapping, or ingest pipeline), or any embedder `.embed_*` method. The
only OpenSearch call this module makes is a `search` on the already-configured
index via `ApplicationContext.get_opensearch_client()` (a plain client, built
without any embedder) and the pure `scan_document_uids_composite` helper. The
only write is `bulk_mark_vector_done`, which touches exactly
`processing.stages.vector` and `processing.errors.vector`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fred_core.documents.document_structures import ProcessingStage, ProcessingStatus
from temporalio import activity

logger = logging.getLogger(__name__)

_TABULAR_FILE_TYPES = {"csv", "xlsx"}


@activity.defn
async def list_repair_candidates_for_source_tag(source_tag: str) -> list[dict]:
    """
    Resolve every metadata document under `source_tag` via one real SQL
    `WHERE source_tag = ...` query (`list_by_source_tag`) -- never a full-table
    scan filtered in Python client-side (`get_all_metadata` does that; the
    corpus-manager route for 3a deliberately does not use it).

    Returns compact plain-data records rather than full `DocumentMetadata`
    blobs, keeping the Temporal payload small at repair scale (~10k docs):
    `document_uid`, whether the document is tabular (CSV/XLSX -- excluded from
    this vector-only repair and reported separately, `sql` reconciliation is
    out of scope here), and whether `vector` already reads `done`.
    """
    from knowledge_flow_backend.application_context import ApplicationContext

    metadata_store = ApplicationContext.get_instance().get_metadata_store()
    docs = await metadata_store.list_by_source_tag(source_tag)
    records = []
    for doc in docs:
        file_type = doc.file.file_type.value if doc.file and doc.file.file_type else None
        vector_done = doc.processing.stages.get(ProcessingStage.VECTORIZED) == ProcessingStatus.DONE
        records.append(
            {
                "document_uid": doc.document_uid,
                "is_tabular": file_type in _TABULAR_FILE_TYPES,
                "vector_done": vector_done,
            }
        )
    activity.logger.info(
        "[SCHEDULER][ACTIVITY][REPAIR_VECTOR_METADATA] resolved %d metadata document(s) for source_tag=%s",
        len(records),
        source_tag,
    )
    return records


@activity.defn
async def list_strict_vector_document_uids() -> list[str]:
    """
    Return every document_uid with at least one real vector chunk in
    OpenSearch, scanned strictly: any failure -- on any composite-aggregation
    page -- raises instead of silently returning an incomplete or empty list
    (`scan_document_uids_composite(strict=True)`), so this activity's Temporal
    retry policy actually retries a transient failure instead of the workflow
    mistaking it for "0 vectors".

    Proves only that *at least one* chunk exists for the document_uid. There is
    no reliable "expected chunk count" to compare against (Kea's original chunk
    counts were never transported), so this can never prove every chunk of a
    multi-chunk document survived the manual OpenSearch restore -- only that the
    document is not entirely empty. That is a deliberate, documented limitation
    of this urgent repair (#2234), not an oversight: see
    `RepairVectorMetadataResult`'s docstring, which callers (the report, the
    frontend) must not contradict by implying full completeness was verified.

    Deliberately never constructs an `OpenSearchVectorStoreAdapter`: its
    `__init__` unconditionally calls `ensure_ready()`, which calls the
    embedder (`_get_embedding_dimension`) and can create or update the index,
    its mapping, or the hybrid-search ingest pipeline -- every one of those is
    forbidden for a metadata-only repair. This activity calls neither
    `get_embedder()` nor `get_create_vector_store()`: it uses only
    `ApplicationContext.get_opensearch_client()` (a plain, already-configured
    `OpenSearch` client the embedder never touches) plus the configured index
    name, and the pure `scan_document_uids_composite` helper --
    `OpenSearchVectorStoreAdapter.list_document_uids` itself delegates to the
    same helper, so there is exactly one paging implementation and no
    vector-store instance is ever built here.
    """
    from knowledge_flow_backend.application_context import ApplicationContext
    from knowledge_flow_backend.common.structures import OpenSearchVectorIndexConfig
    from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import scan_document_uids_composite

    context = ApplicationContext.get_instance()
    store_config = context.get_config().storage.vector_store
    if not isinstance(store_config, OpenSearchVectorIndexConfig):
        raise RuntimeError(f"repair-vector-metadata requires the OpenSearch vector store backend, got {type(store_config).__name__}")
    client = context.get_opensearch_client()
    # Blocking, synchronous OpenSearch call -- same thread-offload reasoning as
    # get_chunk_count/delete_vectors elsewhere in this feature.
    return await asyncio.to_thread(scan_document_uids_composite, client, store_config.index, strict=True)


@activity.defn
async def list_strict_content_document_uids() -> list[str]:
    """
    Return every document_uid with at least one object in the content store,
    scanned strictly: any listing failure raises instead of silently returning
    an empty list (see `BaseContentStore.list_document_uids(strict=True)`).

    Proves only that *at least one* object exists under the document_uid's
    prefix -- not that every expected object (all pages/attachments) survived
    the restore. Same documented limitation as `list_strict_vector_document_uids`
    above; see `RepairVectorMetadataResult`'s docstring.
    """
    from knowledge_flow_backend.application_context import ApplicationContext

    content_store = ApplicationContext.get_instance().get_content_store()
    return await asyncio.to_thread(content_store.list_document_uids, strict=True)


@activity.defn
async def bulk_repair_vector_metadata(source_tag: str, document_uids: list[str]) -> list[str]:
    """
    The only write this action performs: atomically set
    `processing.stages.vector = done` and clear `processing.errors.vector` for
    exactly the given document_uids, scoped to `source_tag`
    (`PostgresDocumentMetadataStore.bulk_mark_vector_done`) -- one Postgres
    transaction, no other JSON field touched.

    `source_tag` re-scopes the `WHERE` clause at write time (not just at the
    earlier scan time): if a document's `source_tag` changed between the scan
    and this write, it is excluded rather than silently repaired outside the
    scope the operator actually authorized.

    Re-running with the same arguments converges to the same end state
    (semantically idempotent) -- not a guaranteed physical no-op, since
    PostgreSQL may still rewrite the row even when the JSON value it computes
    is unchanged.
    """
    from knowledge_flow_backend.application_context import ApplicationContext

    metadata_store = ApplicationContext.get_instance().get_metadata_store()
    if not hasattr(metadata_store, "bulk_mark_vector_done"):
        raise RuntimeError(f"repair-vector-metadata requires a metadata store with bulk_mark_vector_done, got {type(metadata_store).__name__}")
    updated = await metadata_store.bulk_mark_vector_done(source_tag, document_uids)  # type: ignore[attr-defined]
    activity.logger.info("[SCHEDULER][ACTIVITY][REPAIR_VECTOR_METADATA] repaired %d document(s) for source_tag=%s", len(updated), source_tag)
    return updated


@activity.defn
async def emit_repair_vector_metadata_task_event(task_id: str, state: str, error: str | None, result: dict | None) -> None:
    """
    Emit a TaskEvent for a repair-vector-metadata task run (kind stays
    "ingestion" -- this is a knowledge-flow task, changing it to "migration"
    would misroute its SSE subscription to control-plane).

    On the terminal event, `result` carries the structured
    `RepairVectorMetadataResult` report (#2234) so the operator sees real
    counts directly on the task -- on `/admin/tasks` -- never folded into the
    generic `error` string of a `succeeded` task.
    """
    from fred_core.tasks.models import IngestionDetail, IngestionTaskEvent, RepairVectorMetadataResult, TaskState

    from knowledge_flow_backend.application_context import ApplicationContext

    report = RepairVectorMetadataResult(**result) if result is not None else None
    detail = IngestionDetail(
        processed=report.repaired if report else 0,
        total=report.metadata_documents if report else 0,
        failed=report.errors if report else 0,
        preview=0,
        vectorized=report.repaired if report else 0,
        sql_indexed=0,
        result=report,
    )
    event = IngestionTaskEvent(
        task_id=task_id,
        state=TaskState(state),
        seq=0,  # auto-incremented by TaskStore.record_event
        timestamp=datetime.now(tz=timezone.utc),
        step="done",
        progress=1.0 if report else None,
        error=error,
        detail=detail,
        target=None,  # initial target/label was already set at task creation
    )
    task_service = ApplicationContext.get_instance().get_task_service()
    await task_service.record(event)
