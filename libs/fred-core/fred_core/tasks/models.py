# Copyright Thales 2026
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
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TaskState(StrEnum):
    pending = "pending"
    running = "running"
    cancelling = "cancelling"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskState.succeeded, TaskState.failed, TaskState.cancelled)


class IngestionProcessingProfile(StrEnum):
    fast = "fast"
    medium = "medium"
    rich = "rich"


# ── per-kind detail models ────────────────────────────────────────────────────


class IngestionDetail(BaseModel):
    processed: int
    total: int
    failed: int
    preview: int
    vectorized: int
    sql_indexed: int


class TaskLogDetail(BaseModel):
    level: Literal["info", "warn", "error"]
    message: str


class EvaluationDetail(BaseModel):
    """Compact campaign-level counters. Never carries inputs/outputs/explanations."""

    campaign_id: str
    completed: int
    total: int
    passed: int
    failed: int
    execution_errors: int
    scoring_errors: int


# ── target descriptor (which object the task is working on) ──────────────────


class TaskTarget(BaseModel):
    """The object a task is operating on (document, user, database, …)."""

    type: str  # "document" | "user" | "database" | ...
    id: str  # object's unique identifier
    label: str  # human-readable label shown in the UI


# ── shared base (never used directly as an API type) ─────────────────────────


class _TaskEventBase(BaseModel):
    task_id: str
    state: TaskState
    seq: int
    timestamp: datetime
    progress: float | None = None
    step: str | None = None
    error: str | None = None
    target: TaskTarget | None = None
    owner: str | None = None  # user uid who launched the task


# ── per-kind task event variants ─────────────────────────────────────────────


class IngestionTaskEvent(_TaskEventBase):
    kind: Literal["ingestion"] = "ingestion"
    detail: IngestionDetail | None = None


class EvaluationTaskEvent(_TaskEventBase):
    kind: Literal["evaluation"] = "evaluation"
    detail: EvaluationDetail | None = None


class TaskLogEvent(_TaskEventBase):
    kind: Literal["log"] = "log"
    detail: TaskLogDetail


TaskEvent = Annotated[
    Union[IngestionTaskEvent, EvaluationTaskEvent, TaskLogEvent],
    Field(discriminator="kind"),
]


# ── per-kind request models ───────────────────────────────────────────────────


class StartIngestionParams(BaseModel):
    resource_ids: list[str]
    profile: IngestionProcessingProfile = IngestionProcessingProfile.medium


class StartIngestionRequest(BaseModel):
    kind: Literal["ingestion"] = "ingestion"
    params: StartIngestionParams


class StartEvaluationParams(BaseModel):
    campaign_id: str


class StartEvaluationRequest(BaseModel):
    kind: Literal["evaluation"] = "evaluation"
    params: StartEvaluationParams


StartTaskRequest = Annotated[
    Union[StartIngestionRequest, StartEvaluationRequest],
    Field(discriminator="kind"),
]


class StartTaskResponse(BaseModel):
    task_id: str


# ── list-endpoint response types ─────────────────────────────────────────────


class TaskSummary(BaseModel):
    """Lightweight current-state snapshot returned by GET /tasks."""

    task_id: str
    kind: str
    state: TaskState
    progress: float | None = None
    step: str | None = None
    error: str | None = None
    target: TaskTarget | None = None
    created_by: str | None = None
    team_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]
