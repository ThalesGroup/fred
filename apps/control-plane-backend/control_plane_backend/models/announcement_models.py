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
from typing import Any

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

#: Most patch notes one announcement may freeze: past this the users' dialog
#: stops being something anyone reads to the end.
MAX_PATCH_NOTES_PER_ANNOUNCEMENT = 10

#: Most ids a patch-note id list may carry; far above any real working list.
MAX_PATCH_NOTE_IDS = 1000


class AnnouncementRow(Base):
    """ORM model for the ``platform_announcement`` table.

    One platform-admin-authored announcement, delivered to every authenticated
    user while ``enabled``. Platform-wide: teams have no dimension here. A
    banner's dismissal lives in the user's browser.

    ``kind`` is ``banner`` or ``patch_note``. A patch note keeps its markdown
    body in ``description_long``; ``enabled`` includes it in the
    next announcement, in ``position`` order. Users never read this row: they
    read the package an announcement froze (``AnnouncementExposureRow``).

    Deliberately NOT a ReBAC resource, same reasoning as ``platform_prompt``:
    this is a platform-wide assertion with no subject, written by the org-admin
    authority. Read access is not a permission surface either — every
    authenticated user on the deployment is meant to see it.

    ``content_version`` keys a banner's browser-side dismissal; when it moves
    is the service's job (``announcements/service.py``), not a column default.
    Nothing reads it on a patch note.
    """

    __tablename__ = "platform_announcement"
    __table_args__ = (
        # The delivery route reads exactly this: the enabled ones, ordered.
        Index("ix_platform_announcement_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="banner",
        server_default="banner",
        comment="banner | patch_note. A patch note stores its markdown body in "
        "description_long and its plain-text title in title; "
        "description_short stays empty.",
    )
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
    position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Patch note only: its place in the administrator's order, 1 "
        "at the top. Null for a banner.",
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


class AnnouncementSeenRow(Base):
    """The last patch-note announcement one user has seen, for every device.

    ``announcement_id`` names an exposure row holding a package. One row per
    user, removed with the user.
    """

    __tablename__ = "platform_announcement_seen"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    announcement_id: Mapped[str] = mapped_column(String, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AnnouncementExposureRow(Base):
    """One period during which users saw something: a banner on air, or an
    announced package of patch notes. Each row is one line of the admin history.

    No foreign key on ``announcement_id`` so a line outlives its announcement;
    ``label`` snapshots its title when the exposure started.
    """

    __tablename__ = "platform_announcement_exposure"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    announcement_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="The banner; for a package, its first patch note.",
    )
    label: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Locale → title when the exposure started.",
    )
    severity: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="Banner severity when the exposure started; null for patch notes.",
    )
    actor_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Null while users still see it.",
    )
    note_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Patch notes in the package; null when the row keeps none.",
    )
    package: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
        deferred=True,
        comment="The announced patch notes, frozen: [{id, title, description_long}].",
    )
    opens_dialog: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="False only for the package the upgrade created: readable, "
        "pending for nobody.",
    )
