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


class RepairVectorMetadataResult(BaseModel):
    """Structured outcome of the vector-metadata repair action (#2234, 3a).

    Populated only on the terminal `succeeded`/`failed` event of
    `RepairVectorMetadataWorkflow`, same convention as `MigrationResult` below --
    a typed report an operator reads directly off the task, not just a pass/fail.

    IMPORTANT scope limitation, by design (an urgent repair, not a full audit):
    `eligible_with_vectors_and_content`/`repaired` mean the document_uid had *at
    least one* real vector chunk in OpenSearch and *at least one* real object in
    the content store -- there is no reliable expected chunk/object count to
    compare against (it was never transported by the Kea restore), so this can
    never prove *every* chunk or object of a document survived. Never present
    this report, in UI text or logs, as having verified full completeness.

    `failed_or_running_excluded` counts documents left untouched because some
    processing stage reads `failed` or `in_progress` -- a stale `not_started`
    flag and a real failure/stuck stage are not the same problem, and this
    repair must never silently mark one `done` (clearing its error) just
    because it happens to already have vectors/content present.
    """

    source_tag: str
    metadata_documents: int = 0
    already_done: int = 0
    eligible_with_vectors_and_content: int = 0
    repaired: int = 0
    missing_vectors: int = 0
    missing_content: int = 0
    tabular_excluded: int = 0
    failed_or_running_excluded: int = 0
    errors: int = 0


class IngestionDetail(BaseModel):
    processed: int
    total: int
    failed: int
    preview: int
    vectorized: int
    sql_indexed: int
    # Populated only on the terminal event of the vector-metadata repair action
    # (#2234, 3a) -- every other ingestion-kind task leaves this None.
    result: RepairVectorMetadataResult | None = None


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
    # Persisted acknowledgement (OBSERV-02 v3 / rev. 3 §2.10). Both None means
    # "not acknowledged" — the caller must still re-check `needs_attention()`
    # against the CURRENT state before trusting this as "resolved": a task
    # acknowledged once and then failing again is acknowledged-but-needing-
    # attention again (see `needs_attention`'s docstring).
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]


def needs_attention(kind: str, state: TaskState, step: str | None) -> bool:
    """Whether a task is in a state an admin should notice and act on
    (OBSERV-02 v3, `TASK-EVENT-STREAM-RFC.md` rev. 3 §2.10) — the
    acknowledgement gate: a task that does NOT need attention cannot be
    acknowledged (`POST /tasks/{id}/ack` → 409).

    `failed`/`cancelled` cover every kind uniformly. `erasure` is the one
    exception: it deliberately never reaches `failed` (RGPD — an erasure is
    retried forever, never given up on, see `ErasureDetail.attempts`), so its
    attention signal is the `step == "stalled"` convention instead, set after
    `ERASURE_STALL_AFTER_ATTEMPTS` retries while the task is still `running`.

    This is a pure function of CURRENT state, never a stored flag — a task
    acknowledged once that later fails again has a newer failure than the old
    acknowledgement, and callers must compare `acknowledged_at` against the
    task's last-event timestamp (`updated_at`), not just check it is set, or a
    second failure on the same task id would stay silently hidden.
    """
    if state in (TaskState.failed, TaskState.cancelled):
        return True
    return kind == "erasure" and step == "stalled"


class AcknowledgeTaskResponse(BaseModel):
    task_id: str
    acknowledged_at: datetime
    acknowledged_by: str | None
