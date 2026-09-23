from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class AgentRunAdmissionRow(Base):
    __tablename__ = "agent_run_admissions"

    task_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("cp_task_run.task_id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    occurrence_key: Mapped[str | None] = mapped_column(
        String(256), unique=True, nullable=True
    )
    person_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    runtime_client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    runtime_subject: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AgentRunScheduleRow(Base):
    __tablename__ = "agent_run_schedules"

    schedule_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    agent_instance_id: Mapped[str] = mapped_column(String(256), nullable=False)
    runtime_id: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[str] = mapped_column(String(256), nullable=False)
    template_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
