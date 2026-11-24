# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

# Single-row table, same CHECK-constraint shape as `platform_prompt`.
PLATFORM_UI_SETTINGS_SINGLETON_ID = "default"


class PlatformUiSettingsRow(Base):
    """ORM model for the ``platform_ui_settings`` table (platform UI theme settings).

    Holds the platform default UI theme and the theme ids hidden from users.
    Theme ids are opaque here: the frontend owns the theme catalog and ignores
    ids it does not ship. An absent row means "never set".
    """

    __tablename__ = "platform_ui_settings"
    __table_args__ = (
        CheckConstraint(
            f"id = '{PLATFORM_UI_SETTINGS_SINGLETON_ID}'",
            name="ck_platform_ui_settings_singleton",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=PLATFORM_UI_SETTINGS_SINGLETON_ID
    )
    default_theme: Mapped[str | None] = mapped_column(String, nullable=True)
    hidden_themes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Off: the guided tutorial no longer starts on its own; the profile menu still offers it.
    onboarding_tour_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    # Opaque mode id: the frontend falls back to "classic" for one it does not ship.
    home_layout: Mapped[str] = mapped_column(
        String(32), nullable=False, default="classic", server_default="classic"
    )
    # Agent the advanced home's question field talks to; none hides the field.
    home_ask_agent_instance_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("agent_instance.agent_instance_id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class PlatformHomeFeaturedAgentRow(Base):
    """One agent of the home "featured" carousel, chosen and ordered by a platform admin.

    Deleting the agent removes its row; a disabled or suspended one stays and is
    only skipped when read.
    """

    __tablename__ = "platform_home_featured_agent"

    agent_instance_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_instance.agent_instance_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    badge: Mapped[str | None] = mapped_column(String(20), nullable=True)
    highlights: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
