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

"""In-app notifications: one row per recipient, rendered by the frontend from
`type` and `payload`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

NOTIFICATION_OPEN_GROUP_INDEX = "uq_notifications_open_group"


class NotificationRow(Base):
    """ORM model for the ``notifications`` table.

    Text is never stored: ``payload`` holds ids plus a display snapshot taken at
    creation. Every caller-facing query filters ``recipient_id`` and
    ``expires_at``.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        # The list, newest first (a btree scans backwards for DESC).
        Index("ix_notifications_recipient_created", "recipient_id", "created_at", "id"),
        # The badge: one count over the recipient's unseen rows.
        Index(
            "ix_notifications_recipient_unseen",
            "recipient_id",
            postgresql_where=text("seen_at IS NULL"),
            sqlite_where=text("seen_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    recipient_id: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    group_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Shared by every row about the same subject: dedupe and resolve.",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handled_by: Mapped[str | None] = mapped_column(String, nullable=True)
    handled_by_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Display snapshot of who handled the group, as in payload.",
    )
    handled_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)


# One open row per recipient and subject. Leading on group_key so resolving a
# group, which only touches open rows, uses it too.
Index(
    NOTIFICATION_OPEN_GROUP_INDEX,
    NotificationRow.group_key,
    NotificationRow.recipient_id,
    unique=True,
    postgresql_where=text("handled_at IS NULL"),
    sqlite_where=text("handled_at IS NULL"),
)
