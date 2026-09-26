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

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

#: Longest a short description may be, per locale. It renders inside a banner
#: strip next to a title and an actions toolbar; past this it stops fitting on
#: one narrow viewport and belongs in the long description.
MAX_DESCRIPTION_SHORT_CHARS = 500

#: Longest a long description may be, per locale. Rendered in a scrollable
#: dialog, so the limit is about keeping one announcement out of document
#: territory rather than about layout.
MAX_DESCRIPTION_LONG_CHARS = 20_000

#: Longest a title may be, per locale.
MAX_TITLE_CHARS = 200


class AnnouncementRow(Base):
    """ORM model for the ``platform_announcement`` table.

    One platform-admin-authored announcement, rendered as a banner at the top
    of every authenticated page while ``enabled``. Platform-wide: teams have no
    dimension here, and there is no per-user row — a dismissal lives in the
    user's browser, never in this table.

    Deliberately NOT a ReBAC resource, same reasoning as ``platform_prompt``:
    this is a platform-wide assertion with no subject, written by the org-admin
    authority. Read access is not a permission surface either — every
    authenticated user on the deployment is meant to see it.

    ``content_version`` is the contract with the frontend's dismissal storage:
    it changes only when a field the user actually reads changes, so an admin
    toggling ``enabled`` off and on does not resurrect a banner people have
    already dismissed, while fixing a typo does. The bump is the service's job
    (``announcements/service.py``), not a column default.
    """

    __tablename__ = "platform_announcement"
    __table_args__ = (
        # The delivery route reads exactly this: the enabled ones, ordered.
        Index("ix_platform_announcement_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # "info" | "warning" | "error" | "success" — validated by the Pydantic
    # Literal in `announcements/schemas.py`, not by a CHECK constraint: the
    # set is a presentation concern that may gain a variant, and a constraint
    # would make that a migration.
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Banner severity: info | warning | error | success. Fixes both "
        "the colour and the icon; neither is separately authorable.",
    )
    title: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Locale → title map (e.g. {'en': ..., 'fr': ...}), resolved "
        "against the viewer's locale with an 'en' fallback.",
    )
    description_short: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Locale → markdown map shown in the banner itself.",
    )
    description_long: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Locale → markdown map shown in the more-info dialog. Empty "
        "for every locale means the banner offers no more-info action.",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dismissible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    content_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Bumped only when reader-visible content changes, never on an "
        "enabled/disabled toggle. Keys the frontend's per-browser dismissal.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
