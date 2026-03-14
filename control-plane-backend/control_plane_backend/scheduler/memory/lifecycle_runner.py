from __future__ import annotations

import logging

from control_plane_backend.scheduler.lifecycle_actions import (
    delete_conversation_and_mark_done,
    list_due_conversation_candidates,
)
from control_plane_backend.scheduler.temporal.structures import (
    LifecycleManagerInput,
    LifecycleManagerResult,
)

logger = logging.getLogger(__name__)


async def run_lifecycle_manager_once_in_memory(
    input_data: LifecycleManagerInput,
) -> LifecycleManagerResult:
    """
    Execute one lifecycle manager pass directly in-process.

    This mirrors the Temporal workflow logic and allows purge testing without
    a Temporal server or dedicated worker process.
    """
    scanned = 0
    deleted = 0
    dry_run_actions = 0

    batch = await list_due_conversation_candidates(limit=input_data.batch_size)
    if not batch.candidates:
        logger.info("[LIFECYCLE][IN_MEMORY] no due candidates")
        return LifecycleManagerResult()

    logger.info(
        "[LIFECYCLE][IN_MEMORY] processing due candidates size=%s",
        len(batch.candidates),
    )

    for event in batch.candidates:
        scanned += 1
        if input_data.dry_run:
            dry_run_actions += 1
            logger.info(
                "[LIFECYCLE][IN_MEMORY][DRY_RUN] conversation_id=%s",
                event.conversation_id,
            )
            continue

        deletion = await delete_conversation_and_mark_done(event=event)
        if deletion.ok:
            deleted += 1

    logger.info(
        "[LIFECYCLE][IN_MEMORY] completed scanned=%s deleted=%s dry_run_actions=%s",
        scanned,
        deleted,
        dry_run_actions,
    )

    return LifecycleManagerResult(
        scanned=scanned,
        deleted=deleted,
        dry_run_actions=dry_run_actions,
    )
