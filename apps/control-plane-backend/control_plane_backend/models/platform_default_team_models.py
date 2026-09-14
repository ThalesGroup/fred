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

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

# The one and only row id, CHECK-enforced like `platform_prompt`.
PLATFORM_DEFAULT_TEAM_SINGLETON_ID = "default"


class PlatformDefaultTeamRow(Base):
    """The team every new user joins on first GCU acceptance, platform-wide.

    No row means no default team. `team_id` carries no foreign key:
    `teammetadata` belongs to the fred-core metadata, so a deleted team is
    treated as unset when read. Full rationale: CONTROL-PLANE-PRODUCT-CONTRACT.md §52.
    """

    __tablename__ = "platform_default_team"
    __table_args__ = (
        CheckConstraint(
            f"id = '{PLATFORM_DEFAULT_TEAM_SINGLETON_ID}'",
            name="ck_platform_default_team_singleton",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=PLATFORM_DEFAULT_TEAM_SINGLETON_ID
    )
    team_id: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
