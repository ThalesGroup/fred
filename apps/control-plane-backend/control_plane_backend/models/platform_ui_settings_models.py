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

from sqlalchemy import JSON, CheckConstraint, DateTime, String
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
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
