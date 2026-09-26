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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
            "Locale → markdown map rendered in the more-info dialog. Empty for "
            "every locale means the banner offers no more-info action."
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
            "Changes only when reader-visible content changes, never on an "
            "enabled/disabled toggle. The frontend keys each user's dismissal "
            "on it, so a bump makes the banner reappear for everyone who had "
            "closed the previous wording."
        )
    )
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class AnnouncementWriteRequest(BaseModel):
    """Admin create/update payload. Replaces every content field wholesale."""

    model_config = ConfigDict(extra="forbid")

    severity: AnnouncementSeverity
    title: dict[str, str] = Field(
        description="Locale → title map. At least one locale must be non-empty."
    )
    description_short: dict[str, str] = Field(
        description=(
            "Locale → markdown map shown in the banner. At least one locale "
            "must be non-empty."
        )
    )
    description_long: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Locale → markdown map for the more-info dialog. Optional: leaving "
            "it empty is what removes the more-info action from the banner."
        ),
    )
    enabled: bool = Field(
        default=False,
        description="Create disabled by default so an admin can draft in peace.",
    )
    dismissible: bool = Field(default=True)

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: dict[str, str]) -> dict[str, str]:
        return _require_one_locale(_clean(value, MAX_TITLE_CHARS, "title"), "title")

    @field_validator("description_short")
    @classmethod
    def _check_short(cls, value: dict[str, str]) -> dict[str, str]:
        return _require_one_locale(
            _clean(value, MAX_DESCRIPTION_SHORT_CHARS, "description_short"),
            "description_short",
        )

    @field_validator("description_long")
    @classmethod
    def _check_long(cls, value: dict[str, str]) -> dict[str, str]:
        return _clean(value, MAX_DESCRIPTION_LONG_CHARS, "description_long")


def _require_one_locale(cleaned: dict[str, str], field: str) -> dict[str, str]:
    if not cleaned:
        raise ValueError(f"{field} must carry non-empty text in at least one locale")
    return cleaned


class SetAnnouncementEnabledRequest(BaseModel):
    """Toggle delivery without resubmitting the content."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
