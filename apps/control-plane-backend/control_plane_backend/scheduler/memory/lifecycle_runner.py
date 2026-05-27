from __future__ import annotations

import logging
from functools import partial

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
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
    deps: LifecycleActionDependencies | None = None,
) -> LifecycleManagerResult:
    """
    Execute one lifecycle manager pass directly in-process.

    Why this function exists:
    - memory mode intentionally calls the same activity functions as Temporal
      so local tests exercise the same lifecycle behavior

    How to use it:
    - pass the lifecycle-manager input payload
    - optionally pass explicit lifecycle-action dependencies for tests or
      DI-based callers

    Example:
    - `result = await run_lifecycle_manager_once_in_memory(input_data, deps=deps)`
    """
    list_candidates_executor = (
        partial(list_conversation_candidates, deps=deps)
        if deps is not None
        else list_conversation_candidates
    )
    delete_conversation_executor = (
        partial(delete_conversation, deps=deps)
        if deps is not None
        else delete_conversation
    )

    return await run_lifecycle_manager_once(
        input_data=input_data,
        list_candidates=list_candidates_executor,
        delete_conversation=delete_conversation_executor,
        logger=logger,
        log_prefix="[LIFECYCLE][IN_MEMORY]",
    )
