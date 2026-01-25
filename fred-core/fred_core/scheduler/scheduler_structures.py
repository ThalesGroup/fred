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

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from temporalio.common import WorkflowIDReusePolicy


class TemporalSchedulerConfig(BaseModel):
    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "default"
    workflow_id_prefix: str = "task"
    connect_timeout_seconds: Optional[int] = 5


class WorkflowHandle(BaseModel):
    workflow_id: str
    run_id: Optional[str] = None


class SchedulerTask(BaseModel):
    task_id: str
    workflow_type: str
    task_queue: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_id_reuse_policy: WorkflowIDReusePolicy | None = None
    progress_query_name: str = "get_progress"
    payload: Any | None = None
    memo: Dict[str, Any] = Field(default_factory=dict)
    search_attributes: Dict[str, Any] = Field(default_factory=dict)

    def get_workflow_input(self) -> Any | None:
        return self.payload


class AgentCallTask(SchedulerTask):
    caller_actor: str = Field(validation_alias="caller_agent")
    target_agent: str
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)

    def get_workflow_input(self) -> Dict[str, Any]:
        return {
            "caller_actor": self.caller_actor,
            "target_agent": self.target_agent,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "payload": self.payload,
            "context": self.context,
        }


class SchedulerEventType(str, Enum):
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SchedulerTaskProgress(BaseModel):
    state: str
    percent: float = Field(0, ge=0, le=100)
    message: Optional[str] = None


class SchedulerTaskEvent(BaseModel):
    task_id: str
    workflow_id: Optional[str] = None
    run_id: Optional[str] = None
    event_type: SchedulerEventType
    message: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.event_type in {SchedulerEventType.COMPLETED, SchedulerEventType.FAILED}


class SchedulerTaskProgressEvent(SchedulerTaskEvent):
    event_type: SchedulerEventType = SchedulerEventType.PROGRESS
    progress: Optional[float] = None
    step: Optional[str] = None


class SchedulerTaskCompletedEvent(SchedulerTaskEvent):
    event_type: SchedulerEventType = SchedulerEventType.COMPLETED
    result: Any | None = None


class SchedulerTaskFailedEvent(SchedulerTaskEvent):
    event_type: SchedulerEventType = SchedulerEventType.FAILED
    error: Optional[str] = None
