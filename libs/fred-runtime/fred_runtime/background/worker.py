from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from fred_runtime.background.activities import AgentRunActivities
from fred_runtime.background.workflow import AgentRunWorkflow, ScheduledAgentRunWorkflow


def build_background_worker(
    *, client: Client, task_queue: str, activities: AgentRunActivities
) -> Worker:
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[AgentRunWorkflow, ScheduledAgentRunWorkflow],
        activities=[activities.execute, activities.create_occurrence],
    )
