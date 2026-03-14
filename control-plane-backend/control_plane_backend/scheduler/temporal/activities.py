from __future__ import annotations

from temporalio import activity

from control_plane_backend.scheduler.lifecycle_actions import (
    delete_conversation_and_mark_done,
    list_due_conversation_candidates,
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
    candidates = await list_due_conversation_candidates(limit=input_data.limit)

    activity.logger.info(
        "[LIFECYCLE] list due candidates limit=%s returned=%s",
        input_data.limit,
        len(candidates.candidates),
    )
    return candidates


@activity.defn(name="delete_conversation")
async def delete_conversation(
    input_data: DeleteConversationInput,
) -> ConversationActionResult:
    session_id = input_data.event.conversation_id
    activity.logger.info("[LIFECYCLE] delete conversation_id=%s", session_id)
    return await delete_conversation_and_mark_done(event=input_data.event)
