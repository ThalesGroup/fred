from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class SessionMetadataRow(Base):
    """ORM model for the ``session_metadata`` table.

    Stores control-plane-owned session metadata records.
    Runtime message history stays in fred-runtime (session_history table).
    session_id is frontend-generated; control-plane never mints it.
    """

    __tablename__ = "session_metadata"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_prompt_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
