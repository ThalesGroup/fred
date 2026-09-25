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

"""The design system read from a template: the tokens everything composed is
drawn from, and the pure arithmetic over them.

Design layer (design.md D8): this module must never import ``pptx``. The
extraction that reads the file lives in ``analysis.py``; what it produces is
the models below, and from here on nothing knows the output is PowerPoint.

Colours come in pairs, never loose (D12): choosing a fill is choosing the ink
that goes on it. Geometry is per-mille like ``Box`` — x/w of the slide width,
y/h of its height — except the spacing scale, which is per-mille of the
SHORTER side so a horizontal and a vertical gap of the same step look equal.
"""

from __future__ import annotations

import colorsys
import re
from typing import List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

# `keep` is the author's "do not touch": the zone stays in the inventory (so it
# can be re-enabled) but the renderer never writes it.
ZoneRole = Literal[
    "title",
    "subtitle",
    "heading",
    "body",
    "caption",
    "number",
    "label",
    "image",
    "keep",
]

TEXT_ROLES: frozenset[str] = frozenset(
    {"title", "subtitle", "heading", "body", "caption", "number", "label"}
)


class Box(BaseModel):
    """Per-mille geometry on the slide."""

    x: int
    y: int
    w: int
    h: int

    @property
    def surface(self) -> int:
        return max(0, self.w) * max(0, self.h)

    def overlaps(self, other: "Box") -> bool:
        return (
            self.x < other.x + other.w
            and other.x < self.x + self.w
            and self.y < other.y + other.h
            and other.y < self.y + self.h
        )


#: Below this share of the usable area, trimming round the template's fixtures
#: has taken more than a slide needs to breathe.
MIN_FREE_SHARE = 0.45


def free_area(area: Box, reserved: Sequence[Box]) -> Box:
    """`area` with the template's own fixtures trimmed off its edges.

    A logo, a band or a footer sits at an edge, so the trim that leaves the
    most room is the one the designer intended. A fixture in the middle cannot
    be trimmed away without splitting the area in two, and is left to the
    renderer's overlap check instead.
    """
    current = area
    for box in sorted(reserved, key=lambda b: b.surface, reverse=True):
        if not current.overlaps(box):
            continue
        right, bottom = current.x + current.w, current.y + current.h
        sides = [
            Box(x=box.x + box.w, y=current.y, w=right - (box.x + box.w), h=current.h),
            Box(x=current.x, y=current.y, w=box.x - current.x, h=current.h),
            Box(x=current.x, y=box.y + box.h, w=current.w, h=bottom - (box.y + box.h)),
            Box(x=current.x, y=current.y, w=current.w, h=box.y - current.y),
        ]
        current = max(sides, key=lambda side: side.surface)
    return current


# WCAG AA for body text. Large text may pass at 3.0, but a pair is chosen once
# and used at every size, so the stricter bound is the safe one.
MIN_CONTRAST = 4.5

#: Theme colour slots, in the order a template usually means them.
THEME_SLOTS: tuple[str, ...] = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
)

#: A bare quantity: "62%", "1 200", "4.2M€", "2024". Used both to classify a
#: slide's content and to recognise a figure on the template's own slides.
FIGURE_TEXT = re.compile(r"^[^\w]*[\d][\d\s.,]*\s*(?:%|k|K|M|Md|bn|€|\$|£)?[^\w]*$")

#: Theme font references. The analysis already reads these to measure text.
MAJOR_LATIN = "+mj-lt"
MINOR_LATIN = "+mn-lt"


class ColorToken(BaseModel):
    """One colour, and whether the template gave us a slot to point at.

    ``ref`` is what gets written into the shape (D11); ``rgb`` is only for
    measuring contrast here and for the literal fallback when ``ref`` is None.
    """

    ref: Optional[str] = None
    rgb: str
    #: OOXML luminance modulation, in the format's own 0..100000 scale. Set
    #: when the colour is a TINT of the referenced slot rather than the slot
    #: itself; `rgb` then carries the tinted value, for measuring contrast.
    lum_mod: Optional[int] = None
    lum_off: Optional[int] = None

    @property
    def referenced(self) -> bool:
        return self.ref is not None


def _to_hsl(rgb: str) -> Tuple[float, float, float]:
    value = (rgb or "").lstrip("#")
    try:
        r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return 0.0, 0.0, 0.0
    return colorsys.rgb_to_hls(r, g, b)


def _from_hsl(hue: float, light: float, sat: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, max(0.0, min(1.0, light)), sat)
    return "".join(f"{round(channel * 255):02X}" for channel in (r, g, b))


def tint(token: ColorToken, *, lum_mod: int, lum_off: int) -> ColorToken:
    """`token` lightened the way OOXML does it, as a REFERENCE not a copy.

    PowerPoint templates never paint a card with a flat brand colour; they use
    a tint of one, and a tint written as ``lumMod``/``lumOff`` on a scheme
    colour still follows a theme change. So a muted surface can be derived
    without inventing a value the template does not contain (D11, D12).
    """
    hue, light, sat = _to_hsl(token.rgb)
    shifted = light * (lum_mod / 100000) + (lum_off / 100000)
    return token.model_copy(
        update={
            "rgb": _from_hsl(hue, shifted, sat),
            "lum_mod": lum_mod,
            "lum_off": lum_off,
        }
    )


def saturation(rgb: str) -> float:
    return _to_hsl(rgb)[2]


def lightness(rgb: str) -> float:
    return _to_hsl(rgb)[1]


class ColorPair(BaseModel):
    """A surface and the ink that belongs on it (D12).

    ``usable`` is False when no ink of the template reached ``MIN_CONTRAST`` on
    this surface: the surface is then not offered as a fill at all, rather than
    rescued with a colour the template does not contain.
    """

    name: str
    surface: ColorToken
    on_surface: ColorToken
    contrast: float
    usable: bool = True


class TypeToken(BaseModel):
    """One level of the type scale, bound to the role that uses it."""

    role: ZoneRole
    font_ref: Optional[str] = None
    font_name: str = ""
    size_pt: float
    bold: bool = False
    #: Multiple of the font size; the vertical rhythm is built from these.
    line_height: float = 1.2

    @property
    def line_pt(self) -> float:
        return self.size_pt * self.line_height


class SpacingScale(BaseModel):
    """Gap steps, per-mille of the slide's shorter side.

    A scale rather than one unit: one unit makes every gap the same, which is
    not rhythm. Steps are named by index — 0 tightest.
    """

    steps: List[int] = Field(default_factory=lambda: [6, 12, 20, 32, 52])

    def step(self, index: int) -> int:
        if not self.steps:
            return 0
        return self.steps[max(0, min(index, len(self.steps) - 1))]

    def nearest(self, value: int) -> int:
        """The scale step closest to `value` — used to snap a measured gap."""
        if not self.steps:
            return value
        return min(self.steps, key=lambda s: abs(s - value))


class Grid(BaseModel):
    """Columns inside the usable area. Positions are per-mille of the slide."""

    columns: int = 12
    area: Box
    #: Gutter between columns, per-mille of the shorter side.
    gutter: int = 12

    def span(self, start: int, count: int, *, shorter_to_x: float) -> Tuple[int, int]:
        """The x and width, in per-mille of the slide width, of `count` columns
        starting at `start`. `shorter_to_x` converts a shorter-side per-mille
        into a width per-mille (see `DesignSystem.shorter_to_x`).
        """
        columns = max(1, self.columns)
        start = max(0, min(start, columns - 1))
        count = max(1, min(count, columns - start))
        gutter = round(self.gutter * shorter_to_x)
        total_gutter = gutter * (columns - 1)
        column_w = (self.area.w - total_gutter) / columns
        x = self.area.x + round(start * (column_w + gutter))
        w = round(count * column_w + (count - 1) * gutter)
        return x, w


class IconRef(BaseModel):
    """One icon the template carries, and where to find it again.

    Only icons the template NAMES are kept. A bank of pictures called
    "Picture 12" cannot be chosen meaningfully by anyone, and placing them by
    turn would be decoration by lottery — worse than no icon at all.
    """

    #: The name a reader would use: the shape's alt text, or its own name.
    name: str
    #: The slide the icon lives on — its id, which survives reordering — and
    #: the shape key inside it.
    slide_id: int
    key: str
    #: Width over height, so a square frame never stretches a wide glyph.
    aspect: float = 1.0


class ShapeLanguage(BaseModel):
    """How this template draws a block, read from the blocks it draws.

    A template teaches more than its colours: whether it fills its panels or
    only outlines them, how round their corners are, how much air it leaves
    inside them and between them, whether a figure sits above its label or
    below. Composing in the template's language means reading these and using
    them — not reproducing one of its slides (design.md D5, D18).

    Every field has a defensible default, because a template that shows none of
    this must still be composable.
    """

    #: python-pptx adjustment for a rounded rectangle, 0 (square) to 0.5 (pill).
    corner_radius: float = 0.06
    stroked: bool = False
    #: Does the template paint its blocks, or leave them as outlines on the page?
    filled: bool = True
    #: Air inside a block and between two blocks in a row, per-mille of the
    #: shorter side. None when the template showed none, and the scale answers.
    padding: Optional[int] = None
    column_gap: Optional[int] = None
    #: Does a figure sit above the label that names it, or under it?
    figure_above_label: bool = True


class OpticalAnchors(BaseModel):
    """Where the template starts its blocks, so composed slides line up (D13).

    Read, never chosen. ``source`` records whether the template's own slides or
    only its master could answer — the slides win when they disagree.
    """

    title_y: int
    content_y: int
    footer_y: Optional[int] = None
    source: Literal["slides", "master"] = "master"


class DesignSystem(BaseModel):
    """Everything a composed slide is allowed to draw from."""

    #: EMU, carried here so the grid arithmetic needs nothing else.
    slide_width: int
    slide_height: int
    pairs: List[ColorPair] = Field(default_factory=list)
    type_scale: List[TypeToken] = Field(default_factory=list)
    spacing: SpacingScale = Field(default_factory=SpacingScale)
    grid: Optional[Grid] = None
    shapes: ShapeLanguage = Field(default_factory=ShapeLanguage)
    anchors: Optional[OpticalAnchors] = None
    #: Token names that had no theme slot to point at and were read as literals
    #: (D11). Reported to the author rather than shipped silently.
    unreferenced: List[str] = Field(default_factory=list)
    #: Fixtures the canvas layout inherits — logo, band, footer. Already
    #: trimmed out of ``grid.area``; kept so the renderer can check its work.
    reserved: List[Box] = Field(default_factory=list)
    #: The template's own icons, when it names them (D22).
    icons: List[IconRef] = Field(default_factory=list)

    @property
    def shorter_is_height(self) -> bool:
        return self.slide_height <= self.slide_width

    @property
    def shorter_to_x(self) -> float:
        """Convert a shorter-side per-mille into a slide-width per-mille."""
        if not self.slide_width:
            return 1.0
        shorter = min(self.slide_width, self.slide_height)
        return shorter / self.slide_width

    @property
    def shorter_to_y(self) -> float:
        """Convert a shorter-side per-mille into a slide-height per-mille."""
        if not self.slide_height:
            return 1.0
        shorter = min(self.slide_width, self.slide_height)
        return shorter / self.slide_height

    def gap_x(self, index: int) -> int:
        return round(self.spacing.step(index) * self.shorter_to_x)

    def gap_y(self, index: int) -> int:
        return round(self.spacing.step(index) * self.shorter_to_y)

    def pair(self, name: str) -> Optional[ColorPair]:
        for pair in self.pairs:
            if pair.name == name:
                return pair
        return None

    def usable_pair(self, name: str) -> Optional[ColorPair]:
        """The pair under `name` only if it may be used as a fill."""
        pair = self.pair(name)
        return pair if pair is not None and pair.usable else None

    @property
    def block_padding(self) -> int:
        """Air inside a block: the template's own, or the scale's second step."""
        observed = self.shapes.padding
        return observed if observed else self.spacing.step(1)

    def icon(self, name: str) -> Optional[IconRef]:
        wanted = (name or "").strip().casefold()
        return next(
            (icon for icon in self.icons if icon.name.casefold() == wanted), None
        )

    def type_for(self, role: ZoneRole) -> Optional[TypeToken]:
        for token in self.type_scale:
            if token.role == role:
                return token
        return None

    @property
    def complete(self) -> bool:
        """Enough to compose from. A template that fails this is left alone."""
        return bool(self.pairs and self.type_scale and self.grid and self.anchors)


def _channel(value: int) -> float:
    ratio = value / 255.0
    return ratio / 12.92 if ratio <= 0.03928 else ((ratio + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: str) -> float:
    """WCAG relative luminance of an ``RRGGBB`` string."""
    text = rgb.lstrip("#")
    if len(text) != 6:
        return 0.0
    try:
        red, green, blue = (int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 0.0
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(one: str, other: str) -> float:
    """WCAG contrast ratio between two ``RRGGBB`` strings, 1.0 to 21.0."""
    first, second = relative_luminance(one), relative_luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def best_pair(name: str, surface: ColorToken, inks: List[ColorToken]) -> ColorPair:
    """Pair `surface` with the most readable ink the template offers.

    Never invents a colour: when nothing reaches ``MIN_CONTRAST`` the pair is
    returned unusable, and the surface is simply not offered as a fill.
    """
    if not inks:
        return ColorPair(
            name=name, surface=surface, on_surface=surface, contrast=1.0, usable=False
        )
    scored = [(contrast_ratio(surface.rgb, ink.rgb), ink) for ink in inks]
    contrast, ink = max(scored, key=lambda item: item[0])
    return ColorPair(
        name=name,
        surface=surface,
        on_surface=ink,
        contrast=round(contrast, 2),
        usable=contrast >= MIN_CONTRAST,
    )
