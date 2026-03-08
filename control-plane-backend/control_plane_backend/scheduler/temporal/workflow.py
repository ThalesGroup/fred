from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

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

        scanned = 0
        deleted = 0
        dry_run_actions = 0

        batch = await workflow.execute_activity(
            "list_conversation_candidates",
            ListConversationCandidatesInput(limit=input_data.batch_size),
            result_type=ConversationCandidateBatch,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry_policy,
        )

        if not batch.candidates:
            workflow.logger.info("[LIFECYCLE] no due candidates")
            return LifecycleManagerResult()

        workflow.logger.info(
            "[LIFECYCLE] processing due candidates size=%s",
            len(batch.candidates),
        )

        for event in batch.candidates:
            scanned += 1
            if input_data.dry_run:
                dry_run_actions += 1
                workflow.logger.info(
                    "[LIFECYCLE][DRY_RUN] conversation_id=%s",
                    event.conversation_id,
                )
                continue
            deletion = await workflow.execute_activity(
                "delete_conversation",
                DeleteConversationInput(event=event),
                result_type=ConversationActionResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            if deletion.ok:
                deleted += 1

        workflow.logger.info(
            "[LIFECYCLE] completed scanned=%s deleted=%s dry_run_actions=%s",
            scanned,
            deleted,
            dry_run_actions,
        )

        return LifecycleManagerResult(
            scanned=scanned,
            deleted=deleted,
            dry_run_actions=dry_run_actions,
        )
