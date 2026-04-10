from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME = "list_conversation_candidates"
DELETE_CONVERSATION_ACTIVITY_NAME = "delete_conversation"


def _activity_logger():
    """
    Temporal activities use `activity.logger`, but memory mode calls the same
    activity functions directly outside Temporal context.
    """
    try:
        return activity.logger
    except RuntimeError:
        return logger


@activity.defn(name=LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME)
async def list_conversation_candidates(
    input_data: ListConversationCandidatesInput,
) -> ConversationCandidateBatch:
    candidates = await list_due_conversation_candidates(limit=input_data.limit)

    _activity_logger().info(
        "[LIFECYCLE] list due candidates limit=%s returned=%s",
        input_data.limit,
        len(candidates.candidates),
    )
    return candidates


@activity.defn(name=DELETE_CONVERSATION_ACTIVITY_NAME)
async def delete_conversation(
    input_data: DeleteConversationInput,
) -> ConversationActionResult:
    session_id = input_data.event.conversation_id
    _activity_logger().info("[LIFECYCLE] delete conversation_id=%s", session_id)
    return await delete_conversation_and_mark_done(event=input_data.event)
