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

"""The deck plan the agent hands to the build tool, and how a slide of the
plan resolves to one pattern of the effective inventory.

One semantic shape for every slide (design.md D4): a pattern consumes the
fields its zones can hold and ignores the rest. ``pattern`` names either a
pattern id or an intent; an intent resolves to the preferred pattern of that
intent, degrading along :data:`DEGRADATION` when the template lacks it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from fred_capability_ppt_filler.builder.models import (
    INTENTS,
    Intent,
    Pattern,
    TemplateInventory,
)

# Closest available intent when the requested one has no pattern, in order.
DEGRADATION: Dict[str, Tuple[str, ...]] = {
    "title": ("section", "statement", "content"),
    "section": ("title", "statement", "content"),
    "agenda": ("steps", "cards", "content"),
    "content": ("two_columns", "image_text", "statement"),
    "two_columns": ("comparison", "content"),
    "comparison": ("two_columns", "content"),
    "image_text": ("content", "cards"),
    "cards": ("steps", "two_columns", "content"),
    "steps": ("cards", "agenda", "content"),
    "statement": ("section", "content"),
    "contact": ("content",),
    "fixed": (),
}


class PlanItem(BaseModel):
    """One entry of a repeated group (agenda line, KPI card, step, person)."""

    number: Optional[str] = Field(
        default=None,
        description="Figure shown big: '01', '60%', '2024'. Omitted → numbered automatically.",
    )
    heading: Optional[str] = Field(
        default=None, description="Short title of the item (one line)."
    )
    text: Optional[str] = Field(
        default=None, description="Body of the item, one to three short lines."
    )
    label: Optional[str] = Field(
        default=None, description="Small caption under a figure."
    )
    image: Optional[str] = Field(
        default=None,
        description="document_id of an image for the item, from list_images_in_folder.",
    )


class PlanColumn(BaseModel):
    heading: Optional[str] = Field(
        default=None, description="Column heading (one line)."
    )
    bullets: List[str] = Field(
        default_factory=list,
        description="Column bullets; prefix '- ' for a sub-bullet.",
    )


class SlidePlan(BaseModel):
    pattern: str = Field(
        description="A pattern id from the catalogue, or an intent name."
    )
    title: Optional[str] = None
    subtitle: Optional[str] = None
    bullets: List[str] = Field(
        default_factory=list,
        description="Body bullets, telegraphic; prefix '- ' for a sub-bullet. Inline **bold** allowed.",
    )
    columns: List[PlanColumn] = Field(default_factory=list)
    items: List[PlanItem] = Field(default_factory=list)
    image: Optional[str] = Field(
        default=None,
        description="document_id of the slide's image, from list_images_in_folder.",
    )
    images: List[str] = Field(
        default_factory=list,
        description="document_ids for a pattern with several image zones, in order.",
    )
    notes: Optional[str] = Field(default=None, description="Speaker notes.")


class DeckPlan(BaseModel):
    slides: List[SlidePlan]
    file_name: Optional[str] = Field(
        default=None, description="Short file name for the deck; '.pptx' is added."
    )


class Resolution(BaseModel):
    pattern: Pattern
    # Set when the requested intent was replaced by another one.
    substituted_from: Optional[str] = None


def included_patterns(inventory: TemplateInventory) -> List[Pattern]:
    return [pattern for pattern in inventory.patterns if pattern.included]


def best_for_intent(inventory: TemplateInventory, intent: str) -> Optional[Pattern]:
    """The preferred included pattern of ``intent``: an example slide first,
    then a layout, in inventory order."""
    candidates = [p for p in included_patterns(inventory) if p.intent == intent]
    if not candidates:
        return None
    preferred = [p for p in candidates if p.preferred]
    return (preferred or candidates)[0]


def resolve(inventory: TemplateInventory, requested: str) -> Resolution:
    """Map a plan's ``pattern`` value to a pattern, or raise ``ValueError``."""
    pattern = inventory.pattern(requested)
    if pattern is not None:
        if not pattern.included:
            raise ValueError(
                f"Pattern '{requested}' is excluded from this template; pick one from the catalogue."
            )
        return Resolution(pattern=pattern)
    if requested not in INTENTS:
        valid = ", ".join(p.id for p in included_patterns(inventory))
        raise ValueError(f"Unknown pattern '{requested}'. Valid pattern ids: {valid}.")
    intent: Intent = requested  # type: ignore[assignment]
    direct = best_for_intent(inventory, intent)
    if direct is not None:
        return Resolution(pattern=direct)
    for fallback in DEGRADATION.get(intent, ()):
        candidate = best_for_intent(inventory, fallback)
        if candidate is not None:
            return Resolution(pattern=candidate, substituted_from=intent)
    raise ValueError(
        f"This template offers no pattern for '{intent}' nor any substitute; pick a pattern id from the catalogue."
    )


def has_content(slide: SlidePlan) -> bool:
    return bool(
        (slide.title and slide.title.strip())
        or (slide.subtitle and slide.subtitle.strip())
        or any(b.strip() for b in slide.bullets)
        or any(c.heading or c.bullets for c in slide.columns)
        or any(
            i.heading or i.text or i.number or i.label or i.image for i in slide.items
        )
        or slide.image
        or slide.images
    )
