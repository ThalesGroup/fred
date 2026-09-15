from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from control_plane_backend.scheduler.lifecycle_runner import (
    run_lifecycle_manager_once,
    run_wiki_proposal_lifecycle_once,
)
from control_plane_backend.scheduler.temporal.activities import (
    DELETE_CONVERSATION_ACTIVITY_NAME,
    LIST_CONVERSATION_CANDIDATES_ACTIVITY_NAME,
    LIST_WIKI_PROPOSAL_CANDIDATES_ACTIVITY_NAME,
    REJECT_WIKI_PROPOSAL_ACTIVITY_NAME,
)
from control_plane_backend.scheduler.temporal.structures import (
    ConversationActionResult,
    ConversationCandidateBatch,
    DeleteConversationInput,
    LifecycleManagerInput,
    LifecycleManagerResult,
    ListConversationCandidatesInput,
    ListWikiProposalCandidatesInput,
    RejectWikiProposalInput,
    WikiProposalActionResult,
    WikiProposalCandidateBatch,
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

        result = await run_lifecycle_manager_once(
            input_data=input_data,
            list_candidates=_list_candidates,
            delete_conversation=_delete_conversation,
            logger=workflow.logger,
            log_prefix="[LIFECYCLE]",
        )

        async def _list_wiki_candidates(
            list_input: ListWikiProposalCandidatesInput,
        ) -> WikiProposalCandidateBatch:
            return await workflow.execute_activity(
                LIST_WIKI_PROPOSAL_CANDIDATES_ACTIVITY_NAME,
                list_input,
                result_type=WikiProposalCandidateBatch,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=retry_policy,
            )

        async def _reject_wiki_proposal(
            reject_input: RejectWikiProposalInput,
        ) -> WikiProposalActionResult:
            return await workflow.execute_activity(
                REJECT_WIKI_PROPOSAL_ACTIVITY_NAME,
                reject_input,
                result_type=WikiProposalActionResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

        # Same tick, same Schedule, same worker as the conversation sweep
        # above — a second scheduled workflow was deliberately avoided
        # (WIKI-05, CONTROL-PLANE-PRODUCT-CONTRACT.md §49).
        result.wiki_proposals = await run_wiki_proposal_lifecycle_once(
            input_data=input_data,
            list_candidates=_list_wiki_candidates,
            reject_proposal=_reject_wiki_proposal,
            logger=workflow.logger,
            log_prefix="[LIFECYCLE]",
        )
        return result
