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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Opaque theme ids: the frontend owns the catalog, the backend only bounds the shape.
UI_THEME_ID_PATTERN = r"^[a-z][a-z0-9-]{0,31}$"
MAX_HIDDEN_THEMES = 32

UiThemeId = Annotated[str, StringConstraints(pattern=UI_THEME_ID_PATTERN)]


class PlatformUiSettings(BaseModel):
    """Platform UI theme settings as the admin surface reports them."""

    model_config = ConfigDict(extra="forbid")

    default_theme: str | None = Field(
        default=None,
        description="Theme new users get, or null to use the frontend's own default.",
    )
    hidden_themes: list[str] = Field(
        default_factory=list,
        description="Theme ids withdrawn from the users' choice.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = Field(
        default=None, description="Null when the settings were never saved."
    )


class SetPlatformUiSettingsRequest(BaseModel):
    """Replaces both settings at once."""

    model_config = ConfigDict(extra="forbid")

    default_theme: UiThemeId | None = None
    hidden_themes: list[UiThemeId] = Field(
        default_factory=list, max_length=MAX_HIDDEN_THEMES
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> SetPlatformUiSettingsRequest:
        if len(set(self.hidden_themes)) != len(self.hidden_themes):
            raise ValueError("hidden_themes must not repeat an id")
        if self.default_theme is not None and self.default_theme in self.hidden_themes:
            raise ValueError("default_theme must not be hidden")
        return self
