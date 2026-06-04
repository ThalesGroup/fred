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

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Awaitable, Callable, Literal, Union

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


class MigrationDetail(BaseModel):
    step_id: str
    processed: int
    total: int
    failed: int


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


# ── shared base (never used directly as an API type) ─────────────────────────


class _TaskEventBase(BaseModel):
    task_id: str
    state: TaskState
    seq: int
    timestamp: datetime
    progress: float | None = None
    step: str | None = None
    error: str | None = None


# ── per-kind task event variants ─────────────────────────────────────────────


class MigrationTaskEvent(_TaskEventBase):
    kind: Literal["migration"] = "migration"
    detail: MigrationDetail | None = None


class IngestionTaskEvent(_TaskEventBase):
    kind: Literal["ingestion"] = "ingestion"
    detail: IngestionDetail | None = None


class TaskLogEvent(_TaskEventBase):
    kind: Literal["log"] = "log"
    detail: TaskLogDetail


TaskEvent = Annotated[
    Union[MigrationTaskEvent, IngestionTaskEvent, TaskLogEvent],
    Field(discriminator="kind"),
]


# ── per-kind request models ───────────────────────────────────────────────────


class StartMigrationParams(BaseModel):
    step_id: Literal[
        "preflight",
        "copy_tables",
        "personal_teams",
        "migrate_agents",
        "validate",
    ]
    dry_run: bool = False


class StartIngestionParams(BaseModel):
    resource_ids: list[str]
    profile: IngestionProcessingProfile = IngestionProcessingProfile.medium


class StartMigrationRequest(BaseModel):
    kind: Literal["migration"] = "migration"
    params: StartMigrationParams


class StartIngestionRequest(BaseModel):
    kind: Literal["ingestion"] = "ingestion"
    params: StartIngestionParams


StartTaskRequest = Annotated[
    Union[StartMigrationRequest, StartIngestionRequest],
    Field(discriminator="kind"),
]


class StartTaskResponse(BaseModel):
    task_id: str


# ── activity context ──────────────────────────────────────────────────────────


@dataclass
class ActivityContext:
    task_id: str
    emit: Callable[[TaskEvent], Awaitable[None]]
    heartbeat: Callable[[], None]
