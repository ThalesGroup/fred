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

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Intent = Literal[
    "title",
    "section",
    "agenda",
    "content",
    "two_columns",
    "comparison",
    "image_text",
    "cards",
    "steps",
    "statement",
    "contact",
    "fixed",
]

INTENTS: tuple[Intent, ...] = (
    "title",
    "section",
    "agenda",
    "content",
    "two_columns",
    "comparison",
    "image_text",
    "cards",
    "steps",
    "statement",
    "contact",
    "fixed",
)

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

PatternSource = Literal["layout", "slide"]

ExclusionReason = Literal[
    "chart", "table", "icon_bank", "no_placeholder", "unsupported_parts", "author"
]


class Box(BaseModel):
    """Per-mille geometry on the slide."""

    x: int
    y: int
    w: int
    h: int


class Zone(BaseModel):
    """One fillable area of a pattern.

    ``key`` addresses the shape: ``ph:<idx>`` for a placeholder, ``sp:<id/..>``
    for a free shape (its shape-id path through groups). ``max_chars`` is the
    analysis' capacity estimate the tool description passes to the agent.
    """

    key: str
    role: ZoneRole
    box: Box
    sample: str = ""
    font_pt: Optional[float] = None
    max_chars: Optional[int] = None
    max_lines: Optional[int] = None


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
    intent: Intent
    zones: List[Zone] = []
    groups: List[RepeatGroup] = []
    included: bool = True
    exclusion_reason: Optional[ExclusionReason] = None
    # An example slide the designer put in the deck outranks a bare layout of
    # the same intent.
    preferred: bool = False
    # Analysis notes surfaced in the form (e.g. why a slide cannot be copied).
    warnings: List[str] = []

    @property
    def fillable(self) -> bool:
        return any(zone.role != "keep" for zone in self.zones) or any(self.groups)


class AnalysisSummary(BaseModel):
    patterns: int
    fixed: int
    excluded: int
    layouts: int
    slides: int


class TemplateInventory(BaseModel):
    """What the analysis knows about one template. Persisted in the stored
    config next to the template asset key (never the bytes)."""

    slide_width: int
    slide_height: int
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
            patterns=len([p for p in included if p.intent != "fixed"]),
            fixed=len([p for p in included if p.intent == "fixed"]),
            excluded=len(self.patterns) - len(included),
            layouts=len([p for p in self.patterns if p.source == "layout"]),
            slides=len([p for p in self.patterns if p.source == "slide"]),
        )


class PatternOverride(BaseModel):
    """The author's corrections for one pattern. Only set fields apply."""

    pattern_id: str
    label: Optional[str] = None
    intent: Optional[Intent] = None
    included: Optional[bool] = None
    # zone key -> role; `keep` means "do not touch".
    zone_roles: dict[str, ZoneRole] = {}


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
