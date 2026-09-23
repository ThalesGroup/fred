from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class AgentRunRow(Base):
    """Lifecycle metadata for one admitted agent run; never stores credentials."""

    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    team_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    agent_instance_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reporter_client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    reporter_subject: Mapped[str] = mapped_column(String(256), nullable=False)
    origin_caller: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    run_ceiling_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
