# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deterministic Temporal wrapper around one preparation activity."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="CapabilityPreparationWorkflow")
class CapabilityPreparationWorkflow:
    @workflow.run
    async def run(self, preparation_id: str) -> None:
        await workflow.execute_activity(
            "prepare_capability",
            preparation_id,
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=RetryPolicy(maximum_attempts=10),
        )
