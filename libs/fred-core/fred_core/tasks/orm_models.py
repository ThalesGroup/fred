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

"""Per-service task persistence schema (TASK-EVENT-STREAM-RFC §2.6).

This module deliberately exposes **no mapped class**. Every backend that
records tasks declares its own concrete pair on its own declarative ``Base``,
under its own table prefix — `control_plane_backend.models.task_models`
(``cp_``) and `knowledge_flow_backend.models.task_models` (``kf_``):

    class CpTaskRunRow(TaskRunColumns, Base):
        __tablename__ = "cp_task_run"
        __table_args__ = task_run_table_args("cp_task_run")

Why not one shared mapped class (#2170): control-plane and knowledge-flow run
their Alembic trees against the *same* `fred` database. A single `task_run`
registered on the shared `CoreBase` therefore gave both backends one physical
table — so each backend's `GET /tasks` returned the other's rows and the
Activity page showed every task twice. Distinct table names per owner fix that
without a second database, and take these two tables out of the shared-`CoreBase`
ownership ambiguity tracked in #2314: each pair now lives in exactly one
backend's metadata, which is what `make_alembic_env`'s `include_name` filter
reads to decide what a tree owns.

The columns themselves stay here, once: the two tables are the same schema with
two owners, not two schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite import INTEGER as SQLITE_INTEGER
from sqlalchemy.orm import Mapped, mapped_column

# BigInteger PK that autorements correctly on SQLite (INTEGER rowid alias).
_PK_BIG = BigInteger().with_variant(SQLITE_INTEGER(), "sqlite")
_JSONB = JSONB().with_variant(JSON(), "sqlite")

_NON_TERMINAL_MIGRATION = (
    "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskRunColumns:
    """Current-state summary for a task. One row per task, updated in place.

    A declarative mixin, not a mapped class — SQLAlchemy copies these columns
    into each concrete subclass, so `cp_task_run` and `kf_task_run` cannot
    drift apart. Single-column indexes (`index=True`) are named after the
    concrete table by SQLAlchemy itself (`ix_cp_task_run_kind`, …); the
    composite and partial ones need `task_run_table_args` below.
    """

    if TYPE_CHECKING:
        # A mixin is not itself mapped, so type checkers only see
        # `object.__init__` and reject the keyword construction `TaskStore` does.
        # The concrete subclass really does get SQLAlchemy's kwargs constructor —
        # declaring it outside `TYPE_CHECKING` would shadow it at runtime.
        def __init__(self, **kw: Any) -> None: ...

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    step: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    # The Temporal workflow id that backs this task, written by the submitter. It is
    # the durable link used to reconcile a still-pending task against the workflow's
    # real status even when the worker that should advance it is down.
    execution_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    team_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # When a scheduled task is due to act (CTRLP-12 erasure at retention expiry).
    # Set once at creation, never touched by event recording, so it stays stable
    # across state transitions. None for run-now tasks. Indexed so the admin
    # schedule view can order/filter the pipeline by date.
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    # Persisted acknowledgement (OBSERV-02 v3 / TASK-EVENT-STREAM-RFC.md rev. 3
    # §2.10) — both NULL means "not acknowledged", the only state for every
    # task recorded before this column existed. Never cleared once set except
    # by a later terminal event superseding it (see TaskService.acknowledge's
    # "needs attention" predicate, re-evaluated against the CURRENT run, not
    # this column, on every read).
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class TaskEventLogColumns:
    """Append-only event journal. Source of truth for SSE replay."""

    if TYPE_CHECKING:
        # See `TaskRunColumns.__init__`.
        def __init__(self, **kw: Any) -> None: ...

    id: Mapped[int] = mapped_column(_PK_BIG, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    step: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


def single_active_migration_index_name(table: str) -> str:
    """Name of the partial unique index built by `task_run_table_args`.

    Exported so `import_export/api.py` can recognise the constraint in an
    `IntegrityError` string without restating the naming rule — the two used to
    be kept in sync by a "must match" comment.
    """
    return f"uq_{table}_single_active_migration"


def task_run_table_args(table: str) -> tuple[Index, ...]:
    """`__table_args__` for a concrete `<prefix>task_run`.

    Index names are derived from *table* because Postgres scopes index names
    per schema: `cp_task_run` and `kf_task_run` live side by side in the same
    database and cannot both own an index called `ix_task_run_state_updated`.
    """
    return (
        # Index for the reconciliation sweeper, which scans non-terminal tasks by age.
        Index(f"ix_{table}_state_updated", "state", "updated_at"),
        # Atomic exclusion for concurrent migration-task launches (import/reset/
        # reset-full, `import_export/api.py`, all created with kind="migration").
        # Every row this partial index covers already has kind='migration' (the
        # predicate says so) — a unique index on `kind` among only those rows
        # therefore enforces "at most one non-terminal migration-kind row can
        # exist at any time", without constraining any other task kind
        # (ingestion/evaluation/erasure/log never appear in the filtered set).
        # This replaces a check-then-act race (list active tasks, then insert)
        # with a real DB-level guarantee: two concurrent inserts can't both
        # succeed, the loser gets an IntegrityError translated to a 409
        # (`import_export/api.py::_is_concurrent_migration_violation`).
        Index(
            single_active_migration_index_name(table),
            "kind",
            unique=True,
            sqlite_where=text(_NON_TERMINAL_MIGRATION),
            postgresql_where=text(_NON_TERMINAL_MIGRATION),
        ),
    )


def task_event_log_table_args(table: str) -> tuple[UniqueConstraint, ...]:
    """`__table_args__` for a concrete `<prefix>task_event_log`. Same
    per-database uniqueness reason as `task_run_table_args`."""
    return (UniqueConstraint("task_id", "seq", name=f"uq_{table}_task_seq"),)


@dataclass(frozen=True)
class TaskTables:
    """The concrete pair a backend owns, handed to `TaskStore`/`TaskService.build`
    so fred-core's persistence code stays table-name agnostic."""

    run: type[TaskRunColumns]
    event_log: type[TaskEventLogColumns]
