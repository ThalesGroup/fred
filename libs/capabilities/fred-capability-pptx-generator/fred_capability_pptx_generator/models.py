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

"""Typed slide/tool models for the `pptx_generator` capability.

`GeneratePptxArgs` is the static `args_schema` of `generate_pptx`. Class
docstrings and field descriptions here reach the LLM's tool schema.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Validated eagerly so a malformed color is an error the agent can self-correct.
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _check_hex_color(value: str | None) -> str | None:
    if value is not None and not _HEX_COLOR_RE.match(value):
        raise ValueError(
            f"'{value}' is not a valid hex color — use the form '#RRGGBB' "
            "(e.g. '#1565C0')."
        )
    return value


# Each entry maps to a python-pptx MSO_SHAPE member (MSO_CONNECTOR for "line")
# in `deck_builder.py`; no freeform/curved shapes.
ShapeType = Literal[
    "rectangle",
    "rounded_rectangle",
    "oval",
    "triangle",
    "diamond",
    "arrow_right",
    "arrow_left",
    "arrow_up",
    "arrow_down",
    "line",
    "star",
    "pentagon",
    "hexagon",
    "chevron",
    "cloud",
]

# Native (editable in PowerPoint) vs. matplotlib image fallback kinds; the
# agent only picks a `chart_type`, `deck_builder.py` decides the rendering.
NATIVE_CHART_TYPES = frozenset(
    {"bar", "column", "line", "pie", "doughnut", "area", "radar", "scatter", "bubble"}
)
IMAGE_FALLBACK_CHART_TYPES = frozenset({"heatmap", "waterfall", "funnel", "gantt"})

ChartType = Literal[
    "bar",
    "column",
    "line",
    "pie",
    "doughnut",
    "area",
    "radar",
    "scatter",
    "bubble",
    "heatmap",
    "waterfall",
    "funnel",
    "gantt",
]

SlideKind = Literal[
    "title",
    "bullets",
    "image",
    "table",
    "chart",
    "section_header",
    "two_content",
    "columns",
]


class BulletItem(BaseModel):
    """One bullet line. `level` is the indentation depth (0 = top level)."""

    text: str
    level: int = Field(default=0, ge=0, le=8)


class ColumnSpec(BaseModel):
    """One column of a `columns` slide: an optional heading, its bullets and
    an optional small icon (`icon_ref`, a document-library document_uid)."""

    heading: str | None = None
    bullets: list[BulletItem] | None = None
    icon_ref: str | None = None


class TableSpec(BaseModel):
    """A table's header row plus its data rows (all cells rendered as text)."""

    headers: list[str]
    rows: list[list[str]] = Field(default_factory=list)


class ChartSeries(BaseModel):
    """One named data series.

    `values` holds the Y values for a category chart (bar/column/line/pie/
    doughnut/area/radar), or for the matplotlib fallbacks that consume a
    single series (waterfall/funnel: stage sizes; heatmap: one row of the
    matrix, `name` becomes the row label). `x_values`/`sizes` are used only
    for scatter (`x_values`) and bubble (`x_values` + `sizes`) charts.
    """

    name: str
    values: list[float] = Field(default_factory=list)
    x_values: list[float] | None = None
    sizes: list[float] | None = None
    # Honored for bar/column/line/area/radar only: pie/doughnut color per
    # point, which `deck_builder.py` does not implement. Ignored elsewhere.
    color: str | None = None

    _check_color = field_validator("color")(_check_hex_color)


class TextStyle(BaseModel):
    """Font/color/alignment overlay applied to the runs a slide's title or
    body text is written with. Every field is optional and left
    at the layout's inherited default when unset."""

    font: str | None = None
    size_pt: float | None = Field(default=None, gt=0)
    color: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    align: Literal["left", "center", "right"] | None = None

    _check_color = field_validator("color")(_check_hex_color)


PatternType = Literal["soft_circles", "diagonal_bands", "dot_grid"]


class BackgroundSpec(BaseModel):
    """A slide or deck-wide background. `image_ref` reuses
    the same corpus `document_uid` / `document_content.fetch_raw()` path as
    `SlideSpec.image_ref`. `pattern` (+ `accent_color`) is a procedurally
    rendered, deterministic texture — `color` doubles as its base
    fill, the same field `kind="solid"` uses."""

    kind: Literal["solid", "gradient", "image", "pattern"]
    color: str | None = None
    gradient_colors: list[str] | None = None
    image_ref: str | None = None
    pattern: PatternType | None = None
    # Falls back to `theme.primary_color` at build time when unset.
    accent_color: str | None = None

    _check_color = field_validator("color")(_check_hex_color)
    _check_accent_color = field_validator("accent_color")(_check_hex_color)

    @field_validator("gradient_colors")
    @classmethod
    def _check_gradient_colors_hex(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for color in value:
                _check_hex_color(color)
        return value

    @model_validator(mode="after")
    def _check_required_fields_for_kind(self) -> BackgroundSpec:
        # A model_validator: a field_validator never runs for a field left at
        # its default, so it would miss an omitted `gradient_colors`/`pattern`.
        if self.kind == "gradient" and (
            self.gradient_colors is None or len(self.gradient_colors) != 2
        ):
            # A simple 2-stop diagonal gradient, no more, no fewer.
            raise ValueError(
                "a 'gradient' background needs exactly 2 'gradient_colors'."
            )
        if self.kind == "pattern" and self.pattern is None:
            raise ValueError(
                "a 'pattern' background needs a 'pattern' name "
                "('soft_circles', 'diagonal_bands', or 'dot_grid')."
            )
        return self


class ShapeSpec(BaseModel):
    """One decorative/diagram shape, additive on top of whatever
    the slide's `kind` already renders. `left`/`top`/`width`/`height` are
    FRACTIONS of the slide size (0.0-1.0), not inches, so a shape lands
    correctly whether the deck uses the default blank presentation or an
    uploaded brand template with different dimensions."""

    shape_type: ShapeType
    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    # >= 0, not > 0: a "line" shape is a connector between two points, so a
    # perfectly horizontal (height=0) or vertical (width=0) line is valid.
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)
    fill_color: str | None = None
    line_color: str | None = None
    line_width_pt: float | None = Field(default=None, gt=0)
    rotation: float | None = None
    text: str | None = None
    text_style: TextStyle | None = None

    _check_fill_color = field_validator("fill_color")(_check_hex_color)
    _check_line_color = field_validator("line_color")(_check_hex_color)


class ThemeSpec(BaseModel):
    """Deck-wide defaults, applied to every slide that doesn't
    set its own override."""

    heading_font: str | None = None
    body_font: str | None = None
    primary_color: str | None = None
    background: BackgroundSpec | None = None
    # A `palettes.THEME_PRESETS` key; explicit theme fields above always win,
    # the preset only fills what's left unset.
    preset: str | None = None

    _check_primary_color = field_validator("primary_color")(_check_hex_color)

    @field_validator("preset")
    @classmethod
    def _check_preset(cls, value: str | None) -> str | None:
        # Local import: palettes.py builds on `BackgroundSpec`, so a top-level
        # import would be circular.
        if value is None:
            return value
        from fred_capability_pptx_generator.palettes import THEME_PRESETS

        if value not in THEME_PRESETS:
            valid = ", ".join(sorted(THEME_PRESETS))
            raise ValueError(
                f"'{value}' is not a known theme preset — valid presets are: {valid}."
            )
        return value


class GanttTask(BaseModel):
    """One Gantt bar: `start`/`duration` are plain numeric offsets (e.g. day
    numbers) — the fallback renderer does not interpret calendar dates."""

    name: str
    start: float
    duration: float = Field(gt=0)


class ChartSpec(BaseModel):
    """A chart's data, independent of whether it renders native or as an
    embedded image (`deck_builder.py` decides using `chart_type` alone)."""

    chart_type: ChartType
    title: str | None = None
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    # Only used when `chart_type == "gantt"`; every other kind reads
    # `categories`/`series` instead.
    gantt_tasks: list[GanttTask] | None = None

    @model_validator(mode="after")
    def _check_has_required_data(self) -> ChartSpec:
        """Reject an empty chart at the schema boundary with an actionable
        error, instead of an opaque failure inside `deck_builder.build()`."""

        if self.chart_type == "gantt":
            if not self.gantt_tasks:
                raise ValueError("chart_type 'gantt' requires 'gantt_tasks'")
            return self
        if not self.series:
            raise ValueError(f"chart_type '{self.chart_type}' requires 'series'")
        if self.chart_type not in ("scatter", "bubble") and not self.categories:
            raise ValueError(f"chart_type '{self.chart_type}' requires 'categories'")
        return self


class SlideSpec(BaseModel):
    """One slide. Only the fields relevant to `kind` need to be set; unused
    fields are ignored by the builder.

    `two_content` puts `bullets` in the left content placeholder and
    whichever of `image_ref` / `table` / `chart` is set (checked in that
    order) in the right one — the shape is shared with every other slide
    kind rather than doubled into left/right variants.

    `columns` fills a multi-column layout left to right, one `ColumnSpec`
    per column; `subtitle` goes to the intro paragraph above the columns and
    `image_ref` to the main picture frame, when the layout has them.
    """

    kind: SlideKind
    title: str | None = None
    subtitle: str | None = None
    bullets: list[BulletItem] | None = None
    image_ref: str | None = None
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    columns: list[ColumnSpec] | None = None
    # `columns` only: short tag over the column group, when the template
    # slide has one (a label zone sharing a column's left edge above it).
    group_label: str | None = None
    speaker_notes: str | None = None
    # Visual styling, additive on top of the slide's `kind`.
    background: BackgroundSpec | None = None
    title_style: TextStyle | None = None
    body_style: TextStyle | None = None
    shapes: list[ShapeSpec] | None = None
    # Duplicate this brand-template slide instead of a generic layout; `kind`
    # still governs which fields are written into its placeholders.
    template_slide_index: int | None = Field(default=None, ge=0)


class GeneratePptxArgs(BaseModel):
    """The `generate_pptx` tool's static args schema."""

    title: str
    slides: list[SlideSpec]
    # Deck-wide font/color/background defaults.
    theme: ThemeSpec | None = None
