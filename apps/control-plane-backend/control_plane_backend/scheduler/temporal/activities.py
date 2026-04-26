from __future__ import annotations

import logging

from temporalio import activity

from control_plane_backend.scheduler.dependencies import LifecycleActionDependencies
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


async def list_conversation_candidates(
    input_data: ListConversationCandidatesInput,
    deps: LifecycleActionDependencies | None = None,
) -> ConversationCandidateBatch:
    """
    List lifecycle purge candidates through the shared activity code path.

    Why this function exists:
    - memory mode and Temporal execution intentionally share the same activity
      implementation so lifecycle behavior stays aligned

    How to use it:
    - Temporal calls it with `input_data` only
    - in-memory code may optionally pass explicit lifecycle dependencies

    Example:
    - `batch = await list_conversation_candidates(input_data, deps=deps)`
    """
    if deps is None:
        raise RuntimeError(
            "LifecycleActionDependencies are required for listing conversation candidates."
        )
    candidates = await list_due_conversation_candidates(
        limit=input_data.limit,
        deps=deps,
    )

    _activity_logger().info(
        "[LIFECYCLE] list due candidates limit=%s returned=%s",
        input_data.limit,
        len(candidates.candidates),
    )
    return candidates


async def delete_conversation(
    input_data: DeleteConversationInput,
    deps: LifecycleActionDependencies | None = None,
) -> ConversationActionResult:
    """
    Delete one conversation through the shared lifecycle activity path.

    Why this function exists:
    - memory mode and Temporal execution should reuse the same deletion logic
      and logging behavior

    How to use it:
    - Temporal calls it with `input_data` only
    - in-memory code may optionally pass explicit lifecycle dependencies

    Example:
    - `result = await delete_conversation(input_data, deps=deps)`
    """
    if deps is None:
        raise RuntimeError(
            "LifecycleActionDependencies are required for deleting conversations."
        )
    session_id = input_data.event.conversation_id
    _activity_logger().info("[LIFECYCLE] delete conversation_id=%s", session_id)
    return await delete_conversation_and_mark_done(
        event=input_data.event,
        deps=deps,
    )


class LifecycleActivities:
    """
    Bind lifecycle Temporal activities to one explicit dependency bundle.

    Why this class exists:
    - Slice 5 removes the old global context fallback, so Temporal activities
      need one explicit way to reach queue/session stores at worker startup

    How to use it:
    - build one instance in worker bootstrap with `LifecycleActionDependencies`
    - register its bound methods in the Temporal worker

    Example:
    - `activities = LifecycleActivities(deps)`
    """

    def __init__(self, deps: LifecycleActionDependencies) -> None:
        """
        Store the lifecycle-action dependencies used by bound Temporal activities.

        Why this function exists:
        - Temporal workers should resolve their stores once during startup, not
          through hidden globals while activities execute

        How to use it:
        - pass the worker-scoped lifecycle dependency bundle
        - keep the resulting instance alive for the worker lifetime

        Example:
        - `activities = LifecycleActivities(deps)`
        """
        self._deps = deps

    @activity.defn(name=LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME)
    async def list_conversation_candidates(
        self,
        input_data: ListConversationCandidatesInput,
    ) -> ConversationCandidateBatch:
        """
        Run the list-candidates activity with the bound dependency bundle.

        Why this function exists:
        - worker registration needs an activity definition that already knows
          which stores to use, without relying on any global singleton

        How to use it:
        - register the bound method on a `LifecycleActivities` instance
        - Temporal passes `input_data` at execution time

        Example:
        - `activities=[activities.list_conversation_candidates]`
        """
        return await list_conversation_candidates(input_data, deps=self._deps)

    @activity.defn(name=DELETE_CONVERSATION_ACTIVITY_NAME)
    async def delete_conversation(
        self,
        input_data: DeleteConversationInput,
    ) -> ConversationActionResult:
        """
        Run the delete-conversation activity with the bound dependency bundle.

        Why this function exists:
        - worker registration needs deletion logic that reuses the same
          explicit lifecycle dependencies as the list-candidates activity

        How to use it:
        - register the bound method on a `LifecycleActivities` instance
        - Temporal passes `input_data` at execution time

        Example:
        - `activities=[activities.delete_conversation]`
        """
        return await delete_conversation(input_data, deps=self._deps)
