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
from typing import TypedDict

from fred_core.conversation_trace import (
    TRACE_DEFAULT_RETENTION_DAYS,
    TRACE_DEFAULT_SAMPLING,
    TRACE_DEFAULT_STORAGE_BYTES,
    TraceOutcome,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class ConversationTraceSettingsRow(Base):
    __tablename__ = "conversation_trace_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sampling_percent: Mapped[int] = mapped_column(
        Integer, server_default=str(TRACE_DEFAULT_SAMPLING)
    )
    retention_days: Mapped[int] = mapped_column(
        Integer, server_default=str(TRACE_DEFAULT_RETENTION_DAYS)
    )
    storage_cap_bytes: Mapped[int] = mapped_column(
        BigInteger, server_default=str(TRACE_DEFAULT_STORAGE_BYTES)
    )
    used_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    reclaim_target: Mapped[int] = mapped_column(BigInteger, server_default="0")
    degraded_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    degradation_reason: Mapped[str | None] = mapped_column(String(32))


class ConversationTraceStorageRow(Base):
    """Artifact bytes and cleanup leases survive deletion of the owning chat row."""

    __tablename__ = "conversation_trace_storage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    runtime_id: Mapped[str] = mapped_column(String(255))
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    capture_id: Mapped[str] = mapped_column(String(36), index=True)
    objects: Mapped[dict[str, int]] = mapped_column(JSON)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(24))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        Index("ix_trace_storage_due", "runtime_id", "due_at", "id"),
        Index("ix_trace_storage_state", "state", "session_id"),
    )


class ConversationTraceConsentRow(Base):
    __tablename__ = "conversation_trace_consent"

    grant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("session_metadata.session_id", ondelete="CASCADE")
    )
    actor_id: Mapped[str] = mapped_column(String(255))
    title_revision: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(32))
    source_note: Mapped[str | None] = mapped_column(Text, deferred=True)
    incident: Mapped[dict[str, object] | None] = mapped_column(
        JSON(none_as_null=True), deferred=True
    )
    diagnostic_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exchange_id: Mapped[str] = mapped_column(String(255))
    first_rank: Mapped[int] = mapped_column(Integer)
    last_rank: Mapped[int] = mapped_column(Integer)
    turn_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_conversation_trace_active_consent",
            "session_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("ix_conversation_trace_consent_session", "session_id"),
        Index("ix_conversation_trace_consent_catalog", "granted_at", "grant_id"),
        Index("ix_trace_consent_diagnostic_expiry", "diagnostic_at", "grant_id"),
    )


class ConversationTraceIncidentRow(Base):
    """Explicitly reported failures for the conversation's continuous active consent."""

    __tablename__ = "conversation_trace_incident"

    session_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("session_metadata.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    support_error_ref: Mapped[str] = mapped_column(String(32), primary_key=True)
    exchange_id: Mapped[str] = mapped_column(String(255))
    first_rank: Mapped[int] = mapped_column(Integer)
    last_rank: Mapped[int] = mapped_column(Integer)
    turn_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failure_category: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        Index("ix_trace_incident_ref", "support_error_ref", "session_id"),
        Index("ix_trace_incident_order", "session_id", "first_rank", "exchange_id"),
        Index("ix_trace_incident_latest", "session_id", "started_at"),
    )


class TraceSegmentReceipt(TypedDict):
    id: str
    offset_ms: int
    facts: bool
    published: bool
    discarded: bool


class ConversationTraceTurnRow(Base):
    __tablename__ = "conversation_trace_turn"

    capture_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("session_metadata.session_id", ondelete="CASCADE")
    )
    exchange_id: Mapped[str] = mapped_column(String(255))
    runtime_id: Mapped[str] = mapped_column(String(255))
    agent_display_name: Mapped[str] = mapped_column(String(255))
    history_rank: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    turn_number: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32), default=TraceOutcome.UNKNOWN.value)
    checkpoint_status: Mapped[str | None] = mapped_column(String(32))
    failure_category: Mapped[str | None] = mapped_column(String(32))
    support_error_ref: Mapped[str | None] = mapped_column(String(32), index=True)
    call_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    http_attempts: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    http_availability: Mapped[str | None] = mapped_column(String(32))
    sse_segments: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    model_calls: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    tool_calls: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
    segment_receipts: Mapped[list[TraceSegmentReceipt] | None] = mapped_column(
        JSON(none_as_null=True)
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "exchange_id", name="uq_conversation_trace_turn_exchange"
        ),
        Index(
            "ix_conversation_trace_turn_order",
            "session_id",
            "history_rank",
            "capture_id",
        ),
        Index("ix_conversation_trace_turn_catalog", "started_at", "capture_id"),
        Index(
            "ix_conversation_trace_turn_outcome_catalog",
            "outcome",
            "started_at",
            "capture_id",
        ),
    )
