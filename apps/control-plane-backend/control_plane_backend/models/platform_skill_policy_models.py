# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Global packaged-skill activation exceptions, independent of team permissions."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class PlatformSkillPolicyRow(Base):
    """One skill's global state; an absent row means enabled."""

    __tablename__ = "platform_skill_policy"

    skill_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
