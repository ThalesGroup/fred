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

import logging
from typing import Any, Dict

from temporalio import activity

from agentic_backend.scheduler.scheduler_structures import AgentTaskInput
from agentic_backend.scheduler.temporal.runner import get_runner

logger = logging.getLogger(__name__)


@activity.defn
async def run_agent_task(task_input: Dict[str, Any]) -> Dict[str, Any]:
    task = AgentTaskInput.model_validate(task_input)
    runner = await get_runner()
    logger.info("[SCHEDULER][ACTIVITY] Running agent task target=%s", task.target_agent)
    return await runner.run_task(task)
