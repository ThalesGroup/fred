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

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID = "default"
DEFAULT_AGENTS_PUBLISHING_ENABLED = False
DEFAULT_AGENTS_PUBLISH_QUOTA = 5


class PlatformMarketplaceSettingsRow(Base):
    """ORM model for the ``platform_marketplace_settings`` table.

    The marketplace default every team follows unless a platform admin set an
    override on its ``teammetadata`` row. An absent row means the built-in
    defaults (switch off, quota 5).
    """

    __tablename__ = "platform_marketplace_settings"
    __table_args__ = (
        CheckConstraint(
            f"id = '{PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID}'",
            name="ck_platform_marketplace_settings_singleton",
        ),
        CheckConstraint(
            "agents_publish_quota >= 1",
            name="ck_platform_marketplace_settings_agents_publish_quota",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=PLATFORM_MARKETPLACE_SETTINGS_SINGLETON_ID
    )
    agents_publishing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=DEFAULT_AGENTS_PUBLISHING_ENABLED
    )
    agents_publish_quota: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_AGENTS_PUBLISH_QUOTA
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
