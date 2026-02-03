# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class FastStoreVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity(
            "fast_store_vectors",
            args=[payload],
            schedule_to_close_timeout=timedelta(seconds=60),
        )


@workflow.defn
class FastDeleteVectors:
    @workflow.run
    async def run(self, payload):
        return await workflow.execute_activity(
            "fast_delete_vectors",
            args=[payload],
            schedule_to_close_timeout=timedelta(seconds=30),
        )


@workflow.defn
class Process:
    @workflow.run
    async def run(self, definition: Any) -> str:
        pipeline_name = definition.get("name") if isinstance(definition, dict) else getattr(definition, "name", "unknown")
        files = definition.get("files", []) if isinstance(definition, dict) else getattr(definition, "files", [])
        workflow.logger.info(f"[SCHEDULER] Ingesting pipeline: {pipeline_name}")

        for file in files:
            display_name = file.get("display_name") if isinstance(file, dict) else getattr(file, "display_name", None)
            display_name = display_name or "unknown"
            workflow.logger.info("[SCHEDULER] Processing file: %s", display_name)
            await workflow.execute_activity(
                "process_file",
                args=[file, False],
                schedule_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            workflow.logger.info("[SCHEDULER] Completed file: %s", display_name)

        return "success"
