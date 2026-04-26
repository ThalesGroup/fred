from __future__ import annotations

import logging

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
)

logger = logging.getLogger(__name__)


async def list_due_conversation_candidates(
    *,
    limit: int,
    deps: LifecycleActionDependencies,
) -> ConversationCandidateBatch:
    """
    List due conversation purge candidates from the queue store.

    Why this function exists:
    - lifecycle workflows need one typed batch of conversation candidates built
      from queued purge entries

    How to use it:
    - pass the maximum number of items to load
    - optionally pass explicit lifecycle-action dependencies for offline tests
      or in-memory execution

    Example:
    - `batch = await list_due_conversation_candidates(limit=100, deps=deps)`
    """
    queue_store = deps.get_purge_queue_store()
    due_items = await queue_store.list_due(limit=limit)
    candidates = [
        ConversationLifecycleEvent(
            conversation_id=item.session_id,
            team_id=item.team_id,
            trigger=LifecycleTrigger.MEMBER_REMOVED,
            created_at=item.created_at,
            last_activity_at=item.created_at,
        )
        for item in due_items
    ]
    return ConversationCandidateBatch(candidates=candidates)


async def delete_conversation_and_mark_done(
    *,
    event: ConversationLifecycleEvent,
    deps: LifecycleActionDependencies,
) -> ConversationActionResult:
    """
    Delete one conversation session and mark the queue entry as completed.

    Why this function exists:
    - lifecycle workflows must keep session deletion and purge-queue completion
      consistent across memory mode and Temporal execution

    How to use it:
    - pass the lifecycle event to process
    - optionally pass explicit lifecycle-action dependencies for tests or
      in-memory execution

    Example:
    - `result = await delete_conversation_and_mark_done(event=event, deps=deps)`
    """
    session_store = deps.get_session_store()
    queue_store = deps.get_purge_queue_store()

    session_id = event.conversation_id
    await session_store.delete(session_id)
    await queue_store.mark_done(session_id=session_id)
    return ConversationActionResult(
        conversation_id=session_id,
        action="deleted",
        ok=True,
    )
