from __future__ import annotations

from datetime import datetime

from fred_core.sql.mixin import TimestampMixin
from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base


class PurgeQueueRow(Base, TimestampMixin):
    """ORM model for the ``session_purge_queue`` table."""

    __tablename__ = "session_purge_queue"
    __table_args__ = (
        Index("ix_session_purge_queue_created_at", "created_at"),
        Index("ix_session_purge_queue_updated_at", "updated_at"),
    )

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
