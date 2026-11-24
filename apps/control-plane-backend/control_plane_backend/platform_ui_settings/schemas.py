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
from typing import Annotated, Literal

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
    onboarding_tour_enabled: bool = Field(
        default=True,
        description="Whether users are offered the guided tutorial.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = Field(
        default=None, description="Null when the settings were never saved."
    )


class SetPlatformUiSettingsRequest(BaseModel):
    """Replaces every setting at once."""

    model_config = ConfigDict(extra="forbid")

    default_theme: UiThemeId | None = None
    hidden_themes: list[UiThemeId] = Field(
        default_factory=list, max_length=MAX_HIDDEN_THEMES
    )
    onboarding_tour_enabled: bool = True

    @model_validator(mode="after")
    def _check_consistency(self) -> SetPlatformUiSettingsRequest:
        if len(set(self.hidden_themes)) != len(self.hidden_themes):
            raise ValueError("hidden_themes must not repeat an id")
        if self.default_theme is not None and self.default_theme in self.hidden_themes:
            raise ValueError("default_theme must not be hidden")
        return self


# --- Home page mode and featured agents -------------------------------------

HomeLayout = Literal["classic", "advanced"]
MAX_FEATURED_AGENTS = 10
MAX_BADGE_LENGTH = 20
MAX_HIGHLIGHTS = 4
MAX_HIGHLIGHT_LENGTH = 80

Badge = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BADGE_LENGTH),
]
Highlight = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_HIGHLIGHT_LENGTH
    ),
]


class UnknownFeaturedAgentError(ValueError):
    """A featured or question agent id that matches no agent instance."""

    def __init__(self, agent_instance_id: str) -> None:
        super().__init__(f"Unknown agent instance: {agent_instance_id}")
        self.agent_instance_id = agent_instance_id


class FeaturedAgentEntry(BaseModel):
    """One carousel agent as the admin saves it; list order is display order."""

    model_config = ConfigDict(extra="forbid")

    agent_instance_id: str = Field(min_length=1)
    badge: Badge | None = None
    highlights: list[Highlight] = Field(default_factory=list, max_length=MAX_HIGHLIGHTS)


class SetPlatformHomeRequest(BaseModel):
    """Replaces the home mode, the whole featured list and the question agent at once."""

    model_config = ConfigDict(extra="forbid")

    layout: HomeLayout = "classic"
    featured: list[FeaturedAgentEntry] = Field(
        default_factory=list, max_length=MAX_FEATURED_AGENTS
    )
    ask_agent_instance_id: str | None = Field(
        default=None,
        min_length=1,
        description="Agent of the advanced home question field; none hides the field.",
    )

    @model_validator(mode="after")
    def _check_unique(self) -> SetPlatformHomeRequest:
        ids = [entry.agent_instance_id for entry in self.featured]
        if len(set(ids)) != len(ids):
            raise ValueError("featured must not repeat an agent")
        return self


class HomeAgentChoice(BaseModel):
    """An agent as the admin sees it in the home settings."""

    agent_instance_id: str
    display_name: str
    team_id: str
    team_name: str | None = None


class AdminHomeAgent(HomeAgentChoice):
    """A saved home agent; `available` is false when users cannot see it."""

    available: bool = Field(
        description="False when disabled, suspended or outside the default teams: hidden from users."
    )


class AdminFeaturedAgent(AdminHomeAgent):
    """A saved carousel agent with its admin-written extras."""

    badge: str | None = None
    highlights: list[str] = Field(default_factory=list)


class PlatformHomeSettings(BaseModel):
    """Home page settings for the platform admin page."""

    layout: HomeLayout = "classic"
    featured: list[AdminFeaturedAgent] = Field(default_factory=list)
    ask_agent: AdminHomeAgent | None = None
    candidates: list[HomeAgentChoice] = Field(
        default_factory=list,
        description="Enabled agents of the default teams, the only ones an admin can add.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = None
