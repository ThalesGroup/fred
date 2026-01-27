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

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agentic_backend.scheduler.agent_contracts import AgentContextRefsV1


class AgentTaskStatus(str, Enum):
    """The lifecycle status of the task in the database."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class AgentTaskRecordV1(BaseModel):
    """The 'Source of Truth' record stored in Postgres."""

    task_id: str
    user_id: str
    target_agent: str
    status: AgentTaskStatus = AgentTaskStatus.QUEUED

    # Input snapshot
    request_text: str
    context: AgentContextRefsV1 = Field(default_factory=AgentContextRefsV1)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    # Temporal correlation
    workflow_id: str
    run_id: Optional[str] = None

    # Live Progress / Output
    last_message: Optional[str] = None
    percent_complete: float = 0.0
    artifacts: List[str] = Field(default_factory=list)

    # Error or Blocked Details
    error_details: Optional[Dict[str, Any]] = None
    blocked_details: Optional[Dict[str, Any]] = None

    created_at: datetime
    updated_at: datetime


# -----------------------------
# API Request/Response Models
# -----------------------------


class SubmitAgentTaskRequest(BaseModel):
    target_agent: str
    request_text: str
    context: AgentContextRefsV1 = Field(default_factory=AgentContextRefsV1)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    task_id: Optional[str] = None


class SubmitAgentTaskResponse(BaseModel):
    task_id: str
    status: AgentTaskStatus
    workflow_id: str
    run_id: Optional[str] = None


class ListAgentTasksResponse(BaseModel):
    items: List[AgentTaskRecordV1]


# -----------------------------
# Exceptions
# -----------------------------


class AgentTaskError(Exception): ...


class AgentTaskNotFoundError(AgentTaskError): ...


class AgentTaskForbiddenError(AgentTaskError): ...
