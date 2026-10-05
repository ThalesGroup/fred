# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


class PlatformAccessSettingsRow(Base):
    __tablename__ = "platform_access_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    filtering_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    t0_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlatformAccessUserRow(Base):
    __tablename__ = "platform_access_users"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_by: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
