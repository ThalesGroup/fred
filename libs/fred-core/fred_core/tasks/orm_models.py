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
    String,
    Text,
    UniqueConstraint,
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
    # Index for the reconciliation sweeper, which scans non-terminal tasks by age.
    __table_args__ = (Index("ix_task_run_state_updated", "state", "updated_at"),)

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
