from __future__ import annotations

import logging

from control_plane_backend.scheduler.lifecycle_runner import run_lifecycle_manager_once
from control_plane_backend.scheduler.temporal.activities import (
    delete_conversation,
    list_conversation_candidates,
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

    Memory mode intentionally calls the same activity functions as Temporal.
    This keeps one activity code path and makes local memory tests exercise the
    same behavior as Temporal activity execution.
    """
    return await run_lifecycle_manager_once(
        input_data=input_data,
        list_candidates=list_conversation_candidates,
        delete_conversation=delete_conversation,
        logger=logger,
        log_prefix="[LIFECYCLE][IN_MEMORY]",
    )
