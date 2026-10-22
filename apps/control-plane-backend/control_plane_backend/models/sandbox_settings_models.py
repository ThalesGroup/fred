# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Persist the narrow platform sandbox policy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class SandboxSettingsRow(Base):
    __tablename__ = "sandbox_settings"
    __table_args__ = (
        CheckConstraint("id = 'default'", name="ck_sandbox_settings_singleton"),
        CheckConstraint("idle_minutes BETWEEN 1 AND 120", name="ck_sandbox_idle"),
        CheckConstraint(
            "max_active_sessions BETWEEN 1 AND 1000", name="ck_sandbox_active"
        ),
        CheckConstraint("warm_capacity BETWEEN 0 AND 1000", name="ck_sandbox_warm"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    idle_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_active_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    warm_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
