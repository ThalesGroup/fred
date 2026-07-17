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


class MigrationResult(BaseModel):
    """Structured outcome of a platform import (AUTHZ-07 Step 3).

    A typed public projection of `import_export/importer.py::MigrationReport`
    (control-plane-internal) — converted via `importer.py::to_migration_result`,
    never re-derived — so the terminal `succeeded` event and `GET /tasks` can
    both carry it. A non-empty `warnings` list is what makes a partial
    reconciliation distinguishable from full success; the state stays
    `succeeded` either way (RFC TASK-EVENT-STREAM-RFC.md — no new TaskState).
    """

    import_id: str
    source_platform: str
    identities_created: int = 0
    users_processed: int = 0
    users_skipped: list[str] = Field(default_factory=list)
    teams_imported: int = 0
    teams_skipped: int = 0
    teams_provisioned: int = 0
    team_roles_granted: int = 0
    team_roles_skipped: int = 0
    platform_roles_granted: int = 0
    agents_imported: int = 0
    agents_skipped: int = 0
    agents_gap: int = 0
    tags_imported: int = 0
    tags_skipped: int = 0
    docs_imported: int = 0
    docs_skipped: int = 0
    warnings: list[str] = Field(default_factory=list)


class MigrationDetail(BaseModel):
    step_id: str
    processed: int
    total: int
    failed: int
    # Populated only on the terminal `succeeded` event (AUTHZ-07 Step 3).
    result: MigrationResult | None = None


class MigrationTaskEvent(_TaskEventBase):
    kind: Literal["migration"] = "migration"
    detail: MigrationDetail | None = None


class ErasureReason(StrEnum):
    """Why a conversation is being erased (CTRLP-12). Not the content — the trigger."""

    user_deleted = "user_deleted"
    member_removed = "member_removed"
    idle_expired = "idle_expired"


class ErasureDetail(BaseModel):
    """Compact per-conversation erasure progress. Never carries conversation content.

    Surfaces the governance view a platform/team admin needs: why the conversation
    is being erased and how far the fan-out has got (`stores_ok`/`stores_total`).
    The *when* lives on the task's ``scheduled_for`` (see ``TaskSummary``).
    """

    # Set on the scheduling event (the creator knows why); the worker's
    # running/done events carry only the store counts, so reason is optional.
    reason: ErasureReason | None = None
    stores_ok: int = 0
    stores_total: int = 0
    # How many erase attempts have run for this conversation. An erasure is retried
    # every scheduler tick until fully ok and NEVER auto-fails (RGPD: we do not give
    # up erasing) — so this counter is the only signal that a fan-out is wedged.
    # Past ERASURE_STALL_AFTER_ATTEMPTS the task is flagged ``stalled`` (step) while
    # still running, so an admin can intervene instead of it retrying invisibly
    # forever (CTRLP-12).
    attempts: int = 0


class ErasureTaskEvent(_TaskEventBase):
    kind: Literal["erasure"] = "erasure"
    detail: ErasureDetail | None = None


TaskEvent = Annotated[
    Union[
        IngestionTaskEvent,
        EvaluationTaskEvent,
        TaskLogEvent,
        MigrationTaskEvent,
        ErasureTaskEvent,
    ],
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


class StartMigrationRequest(BaseModel):
    kind: Literal["migration"] = "migration"


class StartErasureRequest(BaseModel):
    kind: Literal["erasure"] = "erasure"
    reason: ErasureReason


StartTaskRequest = Annotated[
    Union[
        StartIngestionRequest,
        StartEvaluationRequest,
        StartMigrationRequest,
        StartErasureRequest,
    ],
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
    # When the task is due to act, for work scheduled ahead of time (CTRLP-12
    # erasure at retention expiry). None for run-now tasks. This is what lets an
    # admin see the *schedule* — the pipeline of upcoming erasures with dates —
    # not just what is running right now.
    scheduled_for: datetime | None = None
    # The last persisted per-kind detail (AUTHZ-07 Step 3) — so a result does not
    # vanish on reload. Typed per `kind` (a sibling field callers already narrow
    # on, same pattern as `TaskEvent`); None for a kind with no detail model
    # (`log`) or an older task recorded before this field existed.
    detail: (
        IngestionDetail
        | EvaluationDetail
        | TaskLogDetail
        | MigrationDetail
        | ErasureDetail
        | None
    ) = None


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]
