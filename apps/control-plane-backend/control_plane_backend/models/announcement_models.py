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

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
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


#: Predicate of the partial unique index: at most one enabled patch note.
_ACTIVE_PATCH_NOTE = "enabled AND kind = 'patch_note'"


class AnnouncementRow(Base):
    """ORM model for the ``platform_announcement`` table.

    One platform-admin-authored announcement, delivered to every authenticated
    user while ``enabled``. Platform-wide: teams have no dimension here. A
    banner's dismissal lives in the user's browser; a patch note's lives in
    ``platform_announcement_dismissal``.

    ``kind`` is ``banner`` or ``patch_note``. A patch note keeps its markdown
    body in ``description_long`` and is shown once per user as a dialog; the
    partial unique index keeps at most one of them enabled.

    Deliberately NOT a ReBAC resource, same reasoning as ``platform_prompt``:
    this is a platform-wide assertion with no subject, written by the org-admin
    authority. Read access is not a permission surface either — every
    authenticated user on the deployment is meant to see it.

    ``content_version`` keys the browser-side close (a banner's dismissal, a
    patch note's "closed this sign-in"); when it moves is the service's job (``announcements/service.py``), not a
    column default, and the rule differs per kind (see the service).
    """

    __tablename__ = "platform_announcement"
    __table_args__ = (
        # The delivery route reads exactly this: the enabled ones, ordered.
        Index("ix_platform_announcement_enabled", "enabled"),
        Index(
            "uq_platform_announcement_active_patch_note",
            "kind",
            unique=True,
            postgresql_where=text(_ACTIVE_PATCH_NOTE),
            sqlite_where=text(_ACTIVE_PATCH_NOTE),
        ),
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


class AnnouncementDismissalRow(Base):
    """One user's "don't show again" on one patch note, for every device.

    A row present means hidden for that user. Removed when the note is
    re-enabled, with the announcement and with the user.
    """

    __tablename__ = "platform_announcement_dismissal"

    announcement_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("platform_announcement.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AnnouncementActivationEventRow(Base):
    """Append-only record of one announcement going on or off air.

    No foreign key on ``announcement_id`` so the history outlives the
    announcement; ``label`` snapshots its title at event time.
    """

    __tablename__ = "platform_announcement_activation_event"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    announcement_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Locale → title at event time.",
    )
    action: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="activated | deactivated"
    )
    severity: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="Banner severity at event time; null for a patch note.",
    )
    actor_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
