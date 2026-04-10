from __future__ import annotations

import logging

from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
)

logger = logging.getLogger(__name__)


async def list_due_conversation_candidates(*, limit: int) -> ConversationCandidateBatch:
    """
    List due conversation purge candidates from the purge queue.
    """
    from control_plane_backend.application_context import ApplicationContext

    ctx = ApplicationContext.get_instance()
    queue_store = ctx.get_purge_queue_store()
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
) -> ConversationActionResult:
    """
    Delete one conversation session and mark its purge queue entry as done.
    """
    from control_plane_backend.application_context import ApplicationContext

    ctx = ApplicationContext.get_instance()
    session_store = ctx.get_session_store()
    queue_store = ctx.get_purge_queue_store()

    session_id = event.conversation_id
    await session_store.delete(session_id)
    await queue_store.mark_done(session_id=session_id)
    return ConversationActionResult(
        conversation_id=session_id,
        action="deleted",
        ok=True,
    )
