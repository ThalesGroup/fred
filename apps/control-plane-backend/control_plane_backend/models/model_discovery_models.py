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

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class ModelDiscoverySourceStateRow(Base):
    __tablename__ = "model_discovery_source_state"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    yaml_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    override_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    active_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    inventory_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    removed_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    new_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)


class PlatformModelFallbackRow(Base):
    __tablename__ = "platform_model_fallback"
    __table_args__ = (
        CheckConstraint(
            "model_capability = 'chat'", name="ck_platform_model_fallback_chat_only"
        ),
    )

    model_capability: Mapped[str] = mapped_column(
        String, primary_key=True, default="chat"
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
