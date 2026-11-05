# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Only the preparation identity enters Temporal history."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="PrepareCapability")
class PrepareCapability:
    @workflow.run
    async def run(self, preparation_id: str) -> None:
        await workflow.execute_activity(
            "prepare_capability",
            preparation_id,
            start_to_close_timeout=timedelta(minutes=25),
            schedule_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=95),
                maximum_interval=timedelta(minutes=2),
                maximum_attempts=3,
            ),
        )
