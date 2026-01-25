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

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from agentic_backend.scheduler.temporal.activities import run_agent_task


@workflow.defn(name="AgentWorkflow")
class AgentWorkflow:
    def __init__(self) -> None:
        self.progress: Dict[str, Any] = {
            "state": "starting",
            "percent": 0,
            "message": None,
        }

    @workflow.run
    async def run(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        self.progress.update(state="running", percent=10, message="starting agent task")
        result = await workflow.execute_activity(
            run_agent_task,
            task_input,
            start_to_close_timeout=timedelta(minutes=60),
        )
        self.progress.update(state="completed", percent=100, message="completed")
        return result

    @workflow.query
    def get_progress(self) -> Dict[str, Any]:
        return self.progress
