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

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite import INTEGER as SQLITE_INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base

# BigInteger PK that autorements correctly on SQLite (INTEGER rowid alias).
_PK_BIG = BigInteger().with_variant(SQLITE_INTEGER(), "sqlite")
_JSONB = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskRunRow(Base):
    """Current-state summary for a task. One row per task, updated in place."""

    __tablename__ = "task_run"
    __table_args__ = (
        # Index for the reconciliation sweeper, which scans non-terminal tasks by age.
        Index("ix_task_run_state_updated", "state", "updated_at"),
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
            "uq_task_run_single_active_migration",
            "kind",
            unique=True,
            sqlite_where=text(
                "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
            ),
            postgresql_where=text(
                "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
            ),
        ),
    )

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


class TaskEventLogRow(Base):
    """Append-only event journal. Source of truth for SSE replay."""

    __tablename__ = "task_event_log"
    __table_args__ = (
        UniqueConstraint("task_id", "seq", name="uq_task_event_log_task_seq"),
    )

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


# ── canonical ownership of the task tables ────────────────────────────────────
#
# The single answer to "which tables does fred_core.tasks own?". Consumers must not
# re-enumerate the classes: a backend that persists tasks in a database of its own
# (knowledge-flow, OPS-04 / issue #2170) has to partition its schema on exactly this
# set — once to decide which tables its Alembic chain migrates, and again to decide
# which tables its boot-time `create_all` puts in which database. Two hand-written
# enumerations drift the moment a third task table is added here: the new table gets
# created in the shared database and migrated in the dedicated one, silently
# reintroducing the split this ownership boundary exists to prevent.
# Private: the two public entry points below (`TASK_TABLE_NAMES`, `task_metadata()`) are
# what consumers need. Exporting the ORM classes as a tuple as well would be a third way
# to ask the same question, with no caller.
_TASK_TABLES: tuple[type[Base], ...] = (TaskRunRow, TaskEventLogRow)

TASK_TABLE_NAMES: frozenset[str] = frozenset(m.__tablename__ for m in _TASK_TABLES)


def task_metadata() -> MetaData:
    """A `MetaData` holding only the task tables, for an Alembic chain that owns them.

    Why this exists: `fred_core`'s declarative `Base` is one registry shared by every
    backend, so passing `Base.metadata` to Alembic makes a chain claim tables it does
    not own. Alembic applies its name filters only to the *connection* side and builds
    the metadata side from `sorted_tables` unfiltered, so an unwanted table left in the
    MetaData is still emitted as a create — `include_name` cannot substitute for this.

    Usage, in an `alembic/env.py`::

        run_migrations_offline, run_migrations_online = make_alembic_env(
            target_metadata=task_metadata(),
            get_postgres_config=...,
            version_table="alembic_version_<backend>_tasks",
        )
    """
    scoped = MetaData()
    for name in sorted(TASK_TABLE_NAMES):
        # Via the registry rather than `Model.__table__`: declarative types the latter as
        # FromClause, which has no `to_metadata`.
        Base.metadata.tables[name].to_metadata(scoped)
    return scoped
