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

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class TeamCapabilitySettingsRow(Base):
    """ORM model for the ``team_capability_settings`` table (CAPAB-01 / #1980).

    The *configuration* half of per-team capability enablement (RFC §8.2). The
    *authorization* half (may this team use the capability?) lives entirely in
    OpenFGA — this row never carries an authorization signal. Write ordering is
    enforced by the enablement service: the row is written BEFORE the FGA
    ``enabled`` tuple, so a half-failure leaves the capability disabled but
    never enabled-without-settings; disable deletes the tuple and KEEPS the row
    (re-enable restores prior settings).
    """

    __tablename__ = "team_capability_settings"

    team_id: Mapped[str] = mapped_column(String, primary_key=True)
    capability_id: Mapped[str] = mapped_column(String, primary_key=True)
    settings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="JSON-serialized per-team enablement settings validated against "
        "the capability's TeamSettingsModel / team_settings_fields.",
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
