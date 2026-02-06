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


from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class SchedulerInputArgsV1(BaseModel):
    """
    Minimal envelope used by Schedulers including Temporal workflows (agentic or third-party apps).

    """

    task_id: str  # unique identifier for the scheduled task
    target_ref: str  # the workflow/agent/app unique identifier to invoke
    target_kind: Literal["agent", "app"] = "agent"
    parameters: Dict[str, Any] = Field(default_factory=dict)
