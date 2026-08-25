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

"""Repair a document's surface when its ingestion ends outside the worker.

Two cases share this module:
  - executor-issued failure (GitHub #2279): drive the stuck `in_progress`
    stages to `failed` so the UI stops reading "processing" forever;
  - user-requested cancellation (GitHub #2315): erase the half-built document
    entirely (content, vectors, tabular artifacts, metadata row, quota).

Why this exists:
    A processing stage is persisted `in_progress` *before* the work starts
    (`activities.py::output_process`), and the only code that can move it to
    `failed` is that same activity's `except`. When Temporal is the one ending
    the execution -- a `TIMED_OUT` verdict because the worker pods are saturated
    and nothing was ever scheduled -- no worker code runs at all, so the stage
    stays `in_progress` forever and the UI reads "processing" indefinitely
    (`deriveDocStatus.ts` maps any `in_progress` stage to that badge).

    This module is the single write that closes the gap, shared by the only two
    callers that can observe such a failure:
      - `TaskService` reconciliation, which runs in the API process and holds
        Temporal's verdict even when the whole worker fleet is down;
      - `emit_ingestion_task_event`, the parent workflow's compensation, which
        is faster but only runs when a worker is actually available.

Both are best-effort: a metadata write must never be the reason a failure goes
unrecorded, so callers swallow errors and log rather than propagate.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fred_core.documents.document_structures import ProcessingStatus
from fred_core.tasks.models import TaskState

if TYPE_CHECKING:
    from fred_core.documents.document_store import BaseDocumentMetadataStore
    from fred_core.tasks.orm_models import TaskRunColumns

logger = logging.getLogger(__name__)


def _resolve_store() -> "BaseDocumentMetadataStore":
    """Late-bound store lookup — also the seam tests patch.

    Imported inside the call because `ApplicationContext` pulls in the whole app
    graph, and this module is reached from both the API process (reconciliation)
    and the Temporal worker (compensation).
    """
    from knowledge_flow_backend.application_context import ApplicationContext

    return ApplicationContext.get_instance().get_metadata_store()


async def mark_in_progress_stages_failed(document_uid: str, error_message: str) -> bool:
    """Mark every still-`in_progress` stage of ``document_uid`` as `failed`.

    Returns True when the document was actually updated -- a document with no
    `in_progress` stage is left untouched, which is both the common case (the
    activity already recorded its own, more precise error) and what makes this
    safe to run from the worker and the API for the same task.

    Never raises: the caller is always on a failure path already.
    """
    try:
        store = _resolve_store()
        metadata = await store.get_metadata_by_uid(document_uid)
    except Exception:
        logger.warning(
            "[DOC-FAILURE] could not load metadata for document_uid=%s",
            document_uid,
            exc_info=True,
        )
        return False

    if metadata is None:
        logger.debug("[DOC-FAILURE] no metadata for document_uid=%s", document_uid)
        return False

    stuck = [stage for stage, status in metadata.processing.stages.items() if status == ProcessingStatus.IN_PROGRESS]
    if not stuck:
        return False

    for stage in stuck:
        metadata.mark_stage_error(stage, error_message)

    try:
        await store.save_metadata(metadata)
    except Exception:
        logger.warning(
            "[DOC-FAILURE] could not persist failed stages for document_uid=%s",
            document_uid,
            exc_info=True,
        )
        return False

    logger.info(
        "[DOC-FAILURE] document_uid=%s stages %s -> failed (%s)",
        document_uid,
        [stage.value for stage in stuck],
        error_message,
    )
    return True


async def delete_cancelled_document(document_uid: str, created_by: str | None) -> None:
    """Erase every trace of a deliberately cancelled ingestion (GitHub #2315).

    A cancelled first ingestion leaves a half-built document behind: raw bytes
    in the content store, possibly vectors or tabular artifacts, and a metadata
    row whose stages read `in_progress`. "Stop" means "as if it was never
    uploaded", so this reuses the one strong-delete path, which also releases
    the storage quota and removes the ReBAC parent links.

    Trusted: authorization happened at the cancel endpoint, and by now the
    uploader's ReBAC state may have moved on — that must not strand the
    document. `created_by` is passed for quota attribution only.

    Racing writers are handled, not tolerated: the metadata row is deleted
    first, so an activity whose (unkillable) thread finishes afterwards sees
    its conditional update fail, cannot re-create the document, and discards
    the artifacts it wrote (`IngestionService.persist_progress`). The corpus
    audit stays the backstop for whatever that discard could not reach.

    Never raises. On failure it degrades to marking the stuck stages `failed`,
    so the document reads "failed" rather than processing forever.
    """
    from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService

    try:
        await MetadataService().delete_document_and_artifacts_trusted(created_by or "internal-admin", document_uid)
        logger.info("[DOC-CANCEL] document_uid=%s fully deleted after cancelled ingestion", document_uid)
    except MetadataNotFound:
        # Cancelled before registration finished — nothing was built to clean.
        logger.info("[DOC-CANCEL] document_uid=%s has no metadata; nothing to clean", document_uid)
    except Exception:
        logger.warning(
            "[DOC-CANCEL] full cleanup failed for document_uid=%s — marking stages failed instead",
            document_uid,
            exc_info=True,
        )
        await mark_in_progress_stages_failed(document_uid, "Ingestion cancelled; automatic cleanup failed")


async def repair_document_after_terminal(document_uid: str, state: TaskState, message: str, *, created_by: str | None) -> None:
    """Bring a document back in line with its task's terminal state.

    The one policy, shared by the two paths that can observe a terminal task —
    the workflow's own compensation activity (fast, needs a live worker) and
    API-side reconciliation (slower, works with no worker at all). Both call
    here so the two can never drift apart.

    - `failed`: keep the document, drive its stuck stages to `failed` so the UI
      stops reading "processing" forever (#2279).
    - `cancelled`: erase it — content, vectors, metadata, quota (#2315).
    - `succeeded`: nothing to repair.

    Idempotent, since both paths may well run: failing stages no-ops once none
    is `in_progress`, and the delete no-ops once the document is gone.
    """
    if state == TaskState.failed:
        await mark_in_progress_stages_failed(document_uid, message)
    elif state == TaskState.cancelled:
        await delete_cancelled_document(document_uid, created_by)


async def on_reconciled_terminal(run: "TaskRunColumns", state: TaskState, message: str) -> None:
    """`TaskService.on_reconciled_terminal` hook — the reconciliation-side entry
    into `repair_document_after_terminal`; unwraps the run's document target."""
    target = run.target or {}
    if target.get("type") != "document":
        return
    document_uid = target.get("id")
    if not document_uid:
        return
    await repair_document_after_terminal(document_uid, state, message, created_by=run.created_by)
