from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from fred_core.tasks.agent_run import (
        AgentRunWorkflowInputV1,
        ScheduledAgentRunInputV1,
        ScheduledAgentRunOccurrence,
        ScheduledAgentRunOccurrenceRequest,
    )


@workflow.defn(name="fred.agent_run.v1")
class AgentRunWorkflow:
    @workflow.run
    async def run(self, value: AgentRunWorkflowInputV1) -> None:
        await workflow.execute_activity(
            "fred.execute_background_agent_run.v1",
            value,
            start_to_close_timeout=timedelta(
                seconds=value.record.budget.wall_clock_seconds + 60
            ),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=1),
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )


@workflow.defn(name="fred.scheduled_agent_run.v1")
class ScheduledAgentRunWorkflow:
    @workflow.run
    async def run(self, value: ScheduledAgentRunInputV1) -> None:
        request = ScheduledAgentRunOccurrenceRequest(
            workflow_id=workflow.info().workflow_id,
            run_id=str(workflow.uuid4()),
        )
        occurrence = await workflow.execute_activity(
            "fred.create_scheduled_agent_run_occurrence.v1",
            (value, request),
            result_type=ScheduledAgentRunOccurrence,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        await workflow.execute_child_workflow(
            AgentRunWorkflow.run,
            AgentRunWorkflowInputV1(
                task_id=occurrence.task_id,
                workflow_id=occurrence.workflow_id,
                record=occurrence.record,
            ),
            id=occurrence.workflow_id,
            cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
            parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
        )
