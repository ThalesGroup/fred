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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from control_plane_backend.models.announcement_models import (
    MAX_DESCRIPTION_LONG_CHARS,
    MAX_DESCRIPTION_SHORT_CHARS,
    MAX_TITLE_CHARS,
)

# Same four values as `config.models.UploadWarning.severity`, deliberately:
# the two banners share a visual vocabulary, and a user who learns what a red
# strip means on one should not have to relearn it on the other. Each value
# fixes both the colour and the icon — neither is separately authorable.
AnnouncementSeverity = Literal["info", "warning", "error", "success"]

# A banner is a strip at the top of every page; a patch note is a markdown
# "what's new" note shown once per user at load, with at most one enabled.
AnnouncementKind = Literal["banner", "patch_note"]

#: Locale the frontend falls back to when the viewer's has no entry.
FALLBACK_LOCALE = "en"


def _clean(value: dict[str, str], limit: int, field: str) -> dict[str, str]:
    """Drop blank locales and bound what is left.

    Blank entries are dropped rather than kept, so "present but whitespace"
    cannot pass for authored text: an admin who clears the French tab but
    leaves a newline in it would otherwise ship a banner whose French title is
    a blank line.
    """

    cleaned = {locale: text for locale, text in value.items() if text.strip()}
    for locale, text in cleaned.items():
        if len(text) > limit:
            raise ValueError(
                f"{field}[{locale}] exceeds {limit} characters ({len(text)})"
            )
    return cleaned


class Announcement(BaseModel):
    """One announcement as the API reports it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AnnouncementKind = Field(
        description="`banner` or `patch_note`. Fixed at creation."
    )
    severity: AnnouncementSeverity
    title: dict[str, str] = Field(
        description=(
            "Locale → title map. The frontend resolves it against the viewer's "
            f"locale and falls back to '{FALLBACK_LOCALE}'."
        )
    )
    description_short: dict[str, str] = Field(
        description="Locale → markdown map rendered inside the banner itself."
    )
    description_long: dict[str, str] = Field(
        description=(
            "Locale → markdown map. For a banner, the more-info dialog (empty "
            "for every locale means no more-info action). For a patch note, "
            "its body."
        )
    )
    enabled: bool = Field(
        description="Whether the announcement is delivered to users right now."
    )
    dismissible: bool = Field(
        description=(
            "Whether a user may close the banner. A non-dismissible "
            "announcement stays until an admin disables it."
        )
    )
    content_version: int = Field(
        description=(
            "The edition the browser-side close is keyed on, so a bump shows "
            "the announcement again to everyone who had closed it. Both kinds "
            "bump when re-enabled; a banner also on a content edit."
        )
    )
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class AdminAnnouncement(Announcement):
    """An announcement as the admin list reports it."""

    dismissal_count: int | None = Field(
        default=None,
        description=(
            'Patch note only: how many users ticked "Don\'t show again" '
            "since it was last enabled. Null for a banner."
        ),
    )


class AnnouncementWriteRequest(BaseModel):
    """Admin create/update payload. Replaces every content field wholesale."""

    model_config = ConfigDict(extra="forbid")

    kind: AnnouncementKind = Field(
        default="banner",
        description="`banner` or `patch_note`. An update cannot change it.",
    )
    severity: AnnouncementSeverity = Field(
        description="Banner only; a patch note is stored as `info`."
    )
    title: dict[str, str] = Field(
        description=(
            "Locale → plain-text title map. Both kinds need at least one "
            "non-empty locale; a patch note needs a title in exactly the "
            "locales that have a body."
        ),
    )
    description_short: dict[str, str] = Field(
        description=(
            "Locale → markdown map shown in the banner. A banner needs at least "
            "one non-empty locale; a patch note has none."
        ),
    )
    description_long: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Locale → markdown map. For a banner, the optional more-info "
            "dialog. For a patch note, its body: at least one non-empty locale."
        ),
    )
    enabled: bool = Field(
        default=False,
        description="Create disabled by default so an admin can draft in peace.",
    )
    dismissible: bool = Field(
        default=True, description="Banner only; a patch note is always dismissible."
    )

    @model_validator(mode="after")
    def _apply_kind_rules(self) -> AnnouncementWriteRequest:
        self.description_long = _clean(
            self.description_long, MAX_DESCRIPTION_LONG_CHARS, "description_long"
        )
        self.title = _require_one_locale(
            _clean(self.title, MAX_TITLE_CHARS, "title"), "title"
        )
        if self.kind == "patch_note":
            _require_one_locale(self.description_long, "description_long")
            if set(self.title) != set(self.description_long):
                raise ValueError(
                    "a patch note needs a title and a body in the same locales"
                )
            # Nothing else is authorable on a patch note: normalize, never reject.
            self.severity = "info"
            self.dismissible = True
            self.description_short = {}
            return self
        self.description_short = _require_one_locale(
            _clean(
                self.description_short, MAX_DESCRIPTION_SHORT_CHARS, "description_short"
            ),
            "description_short",
        )
        return self


def _require_one_locale(cleaned: dict[str, str], field: str) -> dict[str, str]:
    if not cleaned:
        raise ValueError(f"{field} must carry non-empty text in at least one locale")
    return cleaned


class SetAnnouncementEnabledRequest(BaseModel):
    """Toggle delivery without resubmitting the content."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ActivePatchNote(BaseModel):
    """The enabled patch note, if any, and whether the caller dismissed it."""

    model_config = ConfigDict(extra="forbid")

    patch_note: Announcement | None = None
    dismissed: bool = Field(
        default=False,
        description=(
            'Whether the caller ticked "Don\'t show again" since it was last '
            "enabled: the client does not open it at load, only on request."
        ),
    )


AnnouncementActivationAction = Literal["activated", "deactivated"]


class AnnouncementActivationEvent(BaseModel):
    """One announcement going on or off air, as the admin history lists it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    announcement_id: str = Field(
        description="May name an announcement that has since been deleted."
    )
    kind: AnnouncementKind
    label: dict[str, str] = Field(
        description="Locale → title as it was when the event happened."
    )
    severity: AnnouncementSeverity | None = Field(
        default=None,
        description="The banner's severity when the event happened; null for a patch note.",
    )
    action: AnnouncementActivationAction
    actor_uid: str | None = Field(
        default=None, description="Uid of the administrator who made the change."
    )
    occurred_at: datetime
