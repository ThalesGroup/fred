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

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class TeamAdminCharterAcceptanceRow(Base):
    """One user's acceptance of one team administrator charter version.

    `user_id` is the Keycloak uid, the same subject as in OpenFGA. A new
    version adds a row, so past acceptances stay on record.
    """

    __tablename__ = "team_admin_charter_acceptances"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TeamAdminCharterStateRow(Base):
    """The charter version team admin relations were last reconciled against.

    A single row (`id` 1); `applied_version` is "" when the charter was off.
    """

    __tablename__ = "team_admin_charter_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    applied_version: Mapped[str] = mapped_column(String, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
