# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="SetDocumentRetrievable")
class SetDocumentRetrievable:
    @workflow.run
    async def run(self, command: dict) -> None:
        applied = await workflow.execute_activity("set_document_retrievable", command, start_to_close_timeout=timedelta(minutes=9), retry_policy=RetryPolicy(maximum_attempts=1))
        if applied:
            await workflow.execute_activity("record_retrievable_applied", command, start_to_close_timeout=timedelta(minutes=1), retry_policy=RetryPolicy())
        await workflow.execute_activity("confirm_document_retrievable", command, start_to_close_timeout=timedelta(minutes=3), retry_policy=RetryPolicy(maximum_attempts=5))
