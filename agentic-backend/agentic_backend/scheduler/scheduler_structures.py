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

from typing import Any, Dict, Optional

from fred_core.scheduler import AgentConversationPayload, SchedulerTaskProgress
from pydantic import BaseModel, Field


class AgentTaskInput(BaseModel):
    caller_actor: Optional[str] = None
    target_agent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    conversation: AgentConversationPayload | None = None


class RunAgentTaskRequest(BaseModel):
    task_id: Optional[str] = None
    workflow_type: str = "AgentWorkflow"
    task_queue: Optional[str] = None
    target_agent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    conversation: AgentConversationPayload | None = None


class RunAgentTaskResponse(BaseModel):
    status: str
    task_id: str
    workflow_id: str
    run_id: Optional[str] = None


class AgentTaskProgressRequest(BaseModel):
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    run_id: Optional[str] = None


class AgentTaskProgressResponse(BaseModel):
    task_id: Optional[str]
    workflow_id: Optional[str]
    run_id: Optional[str]
    progress: SchedulerTaskProgress
