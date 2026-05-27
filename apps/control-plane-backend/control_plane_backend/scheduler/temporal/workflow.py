from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from control_plane_backend.scheduler.lifecycle_runner import run_lifecycle_manager_once
from control_plane_backend.scheduler.temporal.activities import (
    DELETE_CONVERSATION_ACTIVITY_NAME,
    LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
    DeleteConversationInput,
    LifecycleManagerInput,
    LifecycleManagerResult,
    ListConversationCandidatesInput,
)


@workflow.defn(name="LifecycleManagerWorkflow")
class LifecycleManagerWorkflow:
    @workflow.run
    async def run(self, input_data: LifecycleManagerInput) -> LifecycleManagerResult:
        retry_policy = RetryPolicy(maximum_attempts=3)

        async def _list_candidates(
            list_input: ListConversationCandidatesInput,
        ) -> ConversationCandidateBatch:
            return await workflow.execute_activity(
                LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME,
                list_input,
                result_type=ConversationCandidateBatch,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=retry_policy,
            )

        async def _delete_conversation(
            delete_input: DeleteConversationInput,
        ) -> ConversationActionResult:
            return await workflow.execute_activity(
                DELETE_CONVERSATION_ACTIVITY_NAME,
                delete_input,
                result_type=ConversationActionResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

        return await run_lifecycle_manager_once(
            input_data=input_data,
            list_candidates=_list_candidates,
            delete_conversation=_delete_conversation,
            logger=workflow.logger,
            log_prefix="[LIFECYCLE]",
        )
