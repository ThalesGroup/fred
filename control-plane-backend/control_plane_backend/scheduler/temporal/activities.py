from __future__ import annotations

from temporalio import activity

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationLifecycleEvent,
    LifecycleTrigger,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
    DeleteConversationInput,
    ListConversationCandidatesInput,
)


@activity.defn(name="list_conversation_candidates")
async def list_conversation_candidates(
    input_data: ListConversationCandidatesInput,
) -> ConversationCandidateBatch:
    ctx = ApplicationContext.get_instance()
    queue_store = ctx.get_purge_queue_store()
    due_items = await queue_store.list_due(limit=input_data.limit)
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

    activity.logger.info(
        "[LIFECYCLE] list due candidates limit=%s returned=%s",
        input_data.limit,
        len(candidates),
    )
    return ConversationCandidateBatch(candidates=candidates)


@activity.defn(name="delete_conversation")
async def delete_conversation(
    input_data: DeleteConversationInput,
) -> ConversationActionResult:
    ctx = ApplicationContext.get_instance()
    session_store = ctx.get_session_store()
    queue_store = ctx.get_purge_queue_store()

    session_id = input_data.event.conversation_id
    activity.logger.info("[LIFECYCLE] delete conversation_id=%s", session_id)
    await session_store.delete(session_id)
    await queue_store.mark_done(session_id=session_id)
    return ConversationActionResult(
        conversation_id=session_id,
        action="deleted",
        ok=True,
    )
