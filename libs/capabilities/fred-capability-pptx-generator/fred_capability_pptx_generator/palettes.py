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

"""Curated theme-preset catalog for `ThemeSpec.preset`.

Hand-picked, contrast-checked color/font pairings the agent selects by name
instead of inventing hex values.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from fred_capability_pptx_generator.models import BackgroundSpec, _check_hex_color


class ThemePresetDef(BaseModel):
    """One curated preset: fonts, a 'strong' treatment for `title`/
    `section_header` slides, and a 'soft' background tint + accent color for
    every other slide kind."""

    heading_font: str
    body_font: str
    strong_background: BackgroundSpec
    strong_text_color: str
    soft_background_color: str
    accent_color: str

    _check_strong_text_color = field_validator("strong_text_color")(_check_hex_color)
    _check_soft_background_color = field_validator("soft_background_color")(
        _check_hex_color
    )
    _check_accent_color = field_validator("accent_color")(_check_hex_color)


THEME_PRESETS: dict[str, ThemePresetDef] = {
    "corporate_navy": ThemePresetDef(
        heading_font="Georgia",
        body_font="Calibri",
        strong_background=BackgroundSpec(kind="solid", color="#0B2545"),
        strong_text_color="#FFFFFF",
        soft_background_color="#EAF0F7",
        accent_color="#1565C0",
    ),
    "startup_electric": ThemePresetDef(
        heading_font="Poppins",
        body_font="Open Sans",
        strong_background=BackgroundSpec(
            kind="pattern",
            pattern="soft_circles",
            color="#1A0B3D",
            accent_color="#8E2DE2",
        ),
        strong_text_color="#FFFFFF",
        soft_background_color="#F3EEFF",
        accent_color="#8E2DE2",
    ),
    "sustainability_green": ThemePresetDef(
        heading_font="Lato",
        body_font="Lato",
        strong_background=BackgroundSpec(kind="solid", color="#1B5E20"),
        strong_text_color="#FFFFFF",
        soft_background_color="#E8F5E9",
        accent_color="#43A047",
    ),
    "healthcare_calm": ThemePresetDef(
        heading_font="Calibri",
        body_font="Calibri",
        strong_background=BackgroundSpec(kind="solid", color="#0277BD"),
        strong_text_color="#FFFFFF",
        soft_background_color="#E1F5FE",
        accent_color="#00ACC1",
    ),
    "creative_bold": ThemePresetDef(
        heading_font="Poppins",
        body_font="Poppins",
        strong_background=BackgroundSpec(
            kind="pattern",
            pattern="diagonal_bands",
            color="#2B0B3F",
            accent_color="#FF6B00",
        ),
        strong_text_color="#FFFFFF",
        soft_background_color="#FFF3E0",
        accent_color="#FF6B00",
    ),
    "editorial_warm": ThemePresetDef(
        heading_font="Playfair Display",
        body_font="Georgia",
        strong_background=BackgroundSpec(kind="solid", color="#7B3F00"),
        strong_text_color="#FFF8F0",
        soft_background_color="#FBF3E7",
        accent_color="#C1440E",
    ),
    "minimal_mono": ThemePresetDef(
        heading_font="Helvetica",
        body_font="Arial",
        strong_background=BackgroundSpec(
            kind="pattern",
            pattern="dot_grid",
            color="#1A1A1A",
            accent_color="#4D4D4D",
        ),
        strong_text_color="#FFFFFF",
        soft_background_color="#F5F5F5",
        accent_color="#4D4D4D",
    ),
    "sunset_gradient": ThemePresetDef(
        heading_font="Montserrat",
        body_font="Lato",
        strong_background=BackgroundSpec(
            kind="gradient", gradient_colors=["#FF512F", "#F09819"]
        ),
        strong_text_color="#FFFFFF",
        soft_background_color="#FFF1E6",
        accent_color="#FF512F",
    ),
}
