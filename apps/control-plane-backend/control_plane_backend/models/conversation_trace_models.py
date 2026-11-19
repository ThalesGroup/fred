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
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class ConversationTraceSettingsRow(Base):
    __tablename__ = "conversation_trace_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


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
