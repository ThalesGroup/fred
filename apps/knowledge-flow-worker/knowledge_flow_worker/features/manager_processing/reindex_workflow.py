# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="ReindexCorpus")
class ReindexCorpus:
    @workflow.run
    async def run(self, execution: dict[str, str]) -> None:
        # Each activity checkpoints one document. Renew the history even when
        # Temporal has not yet suggested it, for very large corpora.
        for _ in range(100):
            more = await workflow.execute_activity(
                "reindex_next_document",
                execution,
                start_to_close_timeout=timedelta(minutes=10),
                schedule_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), maximum_interval=timedelta(seconds=30)),
            )
            if not more:
                return
        workflow.continue_as_new(execution)
