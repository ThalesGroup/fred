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

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


def utc_now():
    return datetime.now(timezone.utc)


# -----------------------------
# Shared References
# -----------------------------


class AgentContextRefsV1(BaseModel):
    """Stable references to external entities to avoid huge payloads."""

    session_id: Optional[str] = None
    profile_id: Optional[str] = None
    project_id: Optional[str] = None
    tag_ids: List[str] = Field(default_factory=list)
    document_uids: List[str] = Field(default_factory=list)


class SchedulerInputArgsV1(BaseModel):
    """
    Minimal envelope used by schedulers (kept local to avoid heavy imports during Temporal workflow validation).
    """

    task_id: str  # unique identifier for the scheduled task
    target_ref: str  # the workflow/agent/app unique identifier to invoke
    target_kind: Literal["agent", "app"] = "agent"
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentInputArgsV1(SchedulerInputArgsV1):
    """
    The complete context needed for an agent to perform a task.

    This is a specialization of SchedulerInputArgsV1 with agent-specific fields.
    """

    target_kind: Literal["agent"] = "agent"
    user_id: Optional[str] = None
    request_text: str
    context: AgentContextRefsV1 = Field(default_factory=AgentContextRefsV1)

    # HITL / Resumption
    checkpoint_ref: Optional[str] = None
    human_input: Optional[Dict[str, Any]] = None


# -----------------------------
# Events (Activity -> Workflow)
# -----------------------------


class AgentEventBaseV1(BaseModel):
    ts: datetime = Field(default_factory=utc_now)
    extras: Dict[str, Any] = Field(default_factory=dict)


class ProgressEventV1(AgentEventBaseV1):
    type: Literal["progress"] = "progress"
    label: str
    phase: Optional[str] = None
    percent: Optional[float] = None


class LogEventV1(AgentEventBaseV1):
    type: Literal["log"] = "log"
    level: Literal["debug", "info", "warn", "error"] = "info"
    message: str


class ArtifactEventV1(AgentEventBaseV1):
    type: Literal["artifact"] = "artifact"
    artifact_kind: str  # e.g., "pdf_report"
    ref: str  # e.g., "s3://bucket/key"
    title: Optional[str] = None


class HumanInputRequestEventV1(AgentEventBaseV1):
    type: Literal["hitl_request"] = "hitl_request"
    interaction_id: str
    prompt: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)


AgentEventV1 = Annotated[
    Union[ProgressEventV1, LogEventV1, ArtifactEventV1, HumanInputRequestEventV1],
    Field(discriminator="type"),
]

# -----------------------------
# Results & Snapshots
# -----------------------------


class AgentResultStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"  # Waiting for user input


class AgentResultV1(BaseModel):
    """The final package returned by an Activity execution."""

    status: AgentResultStatus
    final_summary: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)
    checkpoint_ref: Optional[str] = None
    events: List[AgentEventV1] = Field(default_factory=list)
