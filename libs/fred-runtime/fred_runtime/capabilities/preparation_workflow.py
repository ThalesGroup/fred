# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deterministic Temporal orchestration for capability preparation."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="CapabilityPreparationWorkflow")
class CapabilityPreparationWorkflow:
    @workflow.run
    async def run(self, preparation_id: str, worker_token: str) -> None:
        parallel, asset_count, max_attempts = await workflow.execute_activity(
            "plan_capability_preparation",
            args=[preparation_id, worker_token],
            start_to_close_timeout=timedelta(seconds=30),
        )
        if asset_count == 0:
            return
        if parallel:
            await self._prepare_assets(
                preparation_id, worker_token, asset_count, max_attempts
            )
            return
        await workflow.execute_activity(
            "prepare_capability",
            args=[preparation_id, worker_token],
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=10),
        )

    async def _prepare_assets(
        self,
        preparation_id: str,
        worker_token: str,
        asset_count: int,
        max_attempts: int,
    ) -> None:
        for attempt in range(1, max_attempts + 1):
            ready = await workflow.execute_activity(
                "begin_parallel_preparation",
                args=[preparation_id, attempt, worker_token],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if not ready:
                return
            try:
                references = []
                for offset in range(0, asset_count, 4):
                    tasks = [
                        asyncio.ensure_future(
                            workflow.execute_activity(
                                "prepare_capability_asset",
                                args=[preparation_id, attempt, index, worker_token],
                                start_to_close_timeout=timedelta(hours=1),
                                heartbeat_timeout=timedelta(minutes=2),
                                retry_policy=RetryPolicy(maximum_attempts=1),
                            )
                        )
                        for index in range(offset, min(offset + 4, asset_count))
                    ]
                    try:
                        references.extend(await asyncio.gather(*tasks))
                    except Exception:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        raise
            except Exception:
                await workflow.execute_activity(
                    "cleanup_parallel_preparation",
                    args=[preparation_id, attempt],
                    start_to_close_timeout=timedelta(minutes=2),
                )
                if attempt == max_attempts:
                    await workflow.execute_activity(
                        "fail_parallel_preparation",
                        args=[preparation_id, attempt, worker_token],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
            else:
                await workflow.execute_activity(
                    "complete_parallel_preparation",
                    args=[preparation_id, attempt, references, worker_token],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                return
