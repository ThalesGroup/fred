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

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class UserPreferencesRow(Base):
    """One user's durable display choices, independent of browser storage."""

    __tablename__ = "users_preferences"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    ui_theme_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    theme_mode: Mapped[str] = mapped_column(String(6), nullable=False, default="system")
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    sidebar_collapsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    team_sort_mode: Mapped[str] = mapped_column(String(6), nullable=False, default="recent")
    agent_sort: Mapped[str] = mapped_column(String(20), nullable=False, default="name")
    trace_expanded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pane_widths: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
