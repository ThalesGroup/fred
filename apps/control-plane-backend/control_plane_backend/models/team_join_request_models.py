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

"""Requests to join an `on_request` team, kept only while they matter."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

#: Longest message a requester may attach.
JOIN_REQUEST_MESSAGE_MAX_LENGTH = 280


class TeamJoinRequestRow(Base):
    """ORM model for the ``team_join_requests`` table.

    One row per team and requester. Accepted and cancelled requests are
    deleted; a refused one stays until ``expires_at`` so admins can still
    accept it.
    """

    __tablename__ = "team_join_requests"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "requester_id", name="uq_team_join_requests_team_requester"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False)
    requester_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    requester_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Display snapshot taken when asking."
    )
    message: Mapped[str | None] = mapped_column(
        String(JOIN_REQUEST_MESSAGE_MAX_LENGTH), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="30 days after asking while pending, 7 days after a refusal.",
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
