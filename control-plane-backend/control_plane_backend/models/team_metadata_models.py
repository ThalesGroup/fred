from __future__ import annotations

from fred_core.sql.mixin import TimestampMixin
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base


class TeamMetadataRow(Base, TimestampMixin):
    """ORM model for the ``teammetadata`` table."""

    __tablename__ = "teammetadata"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    banner_object_storage_key: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
