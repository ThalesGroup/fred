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

from fred_core.conversation_trace import TraceOutcome
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class ConversationTraceSettingsRow(Base):
    __tablename__ = "conversation_trace_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ConversationTraceConsentRow(Base):
    __tablename__ = "conversation_trace_consent"

    grant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("session_metadata.session_id", ondelete="CASCADE")
    )
    actor_id: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(32))
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
    )


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
    call_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    http_attempts: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    http_availability: Mapped[str | None] = mapped_column(String(32))
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))

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
