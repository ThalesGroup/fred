from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base, JsonColumn, TimestampColumn


class TagRow(Base):
    """ORM model for the ``tag`` table — shared between knowledge-flow and the importer."""

    __tablename__ = "tag"

    tag_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn, index=True, nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    path: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    doc: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
