from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base


class AgentInstanceRow(Base):
    """ORM model for the ``agent_instance`` table.

    Stores DB-backed managed agent instance enrollment records.
    Never populated from deployment YAML — enrollment is operational data.
    """

    __tablename__ = "agent_instance"

    agent_instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String, nullable=False)
    source_runtime_id: Mapped[str] = mapped_column(String, nullable=False)
    source_agent_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    tuning_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON-serialized ManagedAgentTuning payload",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
