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

"""Persisted models of the builder: the template inventory the analysis
produces, the author overrides, and the analysis envelope the form consumes.

Geometry is normalized to per-mille of the slide (0..1000) so the form can draw
zone outlines over a rendered thumbnail without knowing the slide size.
"""

from __future__ import annotations

from typing import List, Literal, Optional, get_args

from fred_sdk.contracts.capability import Public
from pydantic import BaseModel, Field

# `keep` is a shape-name annotation's "do not touch": the renderer never writes it.
ZoneRole = Literal[
    "title",
    "subtitle",
    "heading",
    "body",
    "caption",
    "number",
    "label",
    "image",
    "table",
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


# One closed vocabulary for the inventory, the overrides and the plan.
SlideKind = Literal[
    "cover",
    "agenda",
    "section",
    "bullets",
    "two_columns",
    "comparison",
    "cards",
    "figures",
    "process",
    "timeline",
    "team",
    "quote",
    "image_text",
    "table",
    "closing",
    "other",
]

SLIDE_KINDS: tuple[SlideKind, ...] = get_args(SlideKind)

# Who set a pattern's kind, label and slot purposes; vision falls back to rules.
LabelSource = Literal["heuristic", "vision"]

PatternSource = Literal["layout", "slide"]

ExclusionReason = Literal[
    "chart",
    "table",
    "icon_bank",
    "no_placeholder",
    "unsupported_parts",
    "author",
]


# Rounding room when rows are summed against the table's height budget.
TABLE_SLACK_PT = 0.5


class TableSpec(BaseModel):
    """What a template's data table holds, measured at analysis (design.md D14).

    Heights are in points. A row is never shorter than ``row_pt`` (the
    template's own rows) and the rows together never taller than ``height_pt``.
    """

    header: bool
    # Characters per line of each column at its template width (cell margins off).
    columns: List[int]
    widths: List[int]  # EMU, per column
    margin: int  # EMU, left plus right cell margin
    line_pt: float
    pad_pt: float  # top plus bottom cell margin
    row_pt: float
    height_pt: float

    def row_height(self, lines: int, scale: float = 1.0) -> float:
        return max(self.row_pt * scale, lines * self.line_pt * scale + self.pad_pt)

    def body_lines(self, scale: float = 1.0, header_lines: int = 1) -> int:
        """One-line body rows the table holds under its header at ``scale``."""
        room = self.height_pt + TABLE_SLACK_PT
        if self.header:
            room -= self.row_height(header_lines, scale)
        return max(0, int(room // self.row_height(1, scale)))


class Zone(BaseModel):
    """One fillable area of a pattern.

    ``key`` addresses the shape: ``ph:<idx>`` for a placeholder, ``sp:<id/..>``
    for a free shape (its shape-id path through groups). ``chars_per_line`` ×
    ``max_lines`` is the capacity measured once at analysis: the fit check, the
    renderer and the tool description all read it.
    """

    key: str
    role: ZoneRole
    box: Box
    sample: str = ""
    font_pt: Optional[float] = None
    chars_per_line: Optional[int] = None
    max_lines: Optional[int] = None
    # The box grows with its text instead of wrapping inside its outline (a KPI
    # figure sized to "62"): its capacity is what the designer typed, not a limit.
    grows: bool = False
    # What the slot says on this slide ("subtitle", "KPI value"), from vision.
    purpose: Optional[str] = None
    # Set on a `table` zone; its ``max_lines`` are the body lines at full size.
    table: Optional[TableSpec] = None
    # An image zone drawn over a layout or master shape no slide can remove:
    # left empty, that frame shows, so the zone needs a picture (design.md D20).
    framed: bool = False


class RepeatGroup(BaseModel):
    """N sibling items of identical structure (agenda entries, KPI cards, steps).

    ``items`` holds the zones of every item, in reading order; ``item_zones`` is
    the role list of one item, in the same order inside each item.
    """

    key: str
    count: int
    item_zones: List[ZoneRole]
    items: List[List[Zone]]
    # Shape key of each item's container (the group), for removing unused items.
    item_keys: List[str]


class Pattern(BaseModel):
    id: str
    source: PatternSource
    # Layout index in its master, or 1-based slide number, for display only.
    source_index: int
    name: str
    label: str
    kind: SlideKind
    zones: List[Zone] = []
    groups: List[RepeatGroup] = []
    included: bool = True
    exclusion_reason: Optional[ExclusionReason] = None
    # False for a one-off slide (decoration, a specific org chart): kept in the
    # inventory but never chosen as an archetype.
    reusable: bool = True
    labelled_by: LabelSource = "heuristic"
    # Analysis notes surfaced in the form (e.g. why a slide cannot be copied).
    warnings: List[str] = []

    @property
    def fillable(self) -> bool:
        return any(zone.role != "keep" for zone in self.zones) or any(self.groups)


class AnalysisSummary(BaseModel):
    patterns: int
    # Included but not reusable: shown in the form, never chosen.
    fixed: int
    excluded: int
    layouts: int
    slides: int


class TemplateInventory(BaseModel):
    """What the analysis knows about one template. Persisted in the stored
    config next to the template asset key (never the bytes)."""

    slide_width: int
    slide_height: int
    # Rules the patterns were computed with (`analysis.ANALYSIS_VERSION`);
    # an older inventory is recomputed from the stored template on the next save.
    analysis_version: int = 0
    patterns: List[Pattern] = []
    # Free text repeated on several slides (footers, confidentiality lines):
    # kept so a later review can explain why a box is not a zone.
    shared_texts: List[str] = []

    def pattern(self, pattern_id: str) -> Optional[Pattern]:
        for pattern in self.patterns:
            if pattern.id == pattern_id:
                return pattern
        return None

    def summary(self) -> AnalysisSummary:
        included = [p for p in self.patterns if p.included]
        return AnalysisSummary(
            patterns=len([p for p in included if p.reusable]),
            fixed=len([p for p in included if not p.reusable]),
            excluded=len(self.patterns) - len(included),
            layouts=len([p for p in self.patterns if p.source == "layout"]),
            slides=len([p for p in self.patterns if p.source == "slide"]),
        )


class PatternOverride(BaseModel):
    """The author's corrections for one pattern. Only set fields apply."""

    # Names a slide of the template, which travels with the template on a copy.
    pattern_id: Public[str]
    label: Optional[str] = None
    kind: Optional[SlideKind] = None
    included: Optional[bool] = None


class AnalysisError(BaseModel):
    code: str
    message: str


class AnalyzeResult(BaseModel):
    """Envelope of the stateless ``/analyze`` route and of ``validate_config``."""

    inventory: Optional[TemplateInventory] = None
    summary: Optional[AnalysisSummary] = None
    errors: List[AnalysisError] = []
    # Overrides that no longer matched after a re-upload (form feedback).
    dropped_overrides: List[str] = Field(default_factory=list)
