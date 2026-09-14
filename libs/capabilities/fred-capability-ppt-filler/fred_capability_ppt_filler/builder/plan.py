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

import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.models import (
    INTENTS,
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


# The plan comes from a model, and small models get JSON shapes wrong (a bullet
# list as one string, a number as an int, a stray string in a list). Every
# model below coerces what it can instead of rejecting the call: a validation
# error would reach the user as an opaque tool failure.


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(t for t in (_as_text(v) for v in value) if t)
    if isinstance(value, dict):
        return _as_text(value.get("text") or value.get("heading") or value.get("title"))
    return str(value)


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for entry in value:
            text = _as_text(entry)
            if text and text.strip():
                out.append(text)
        return out
    text = _as_text(value)
    return [text] if text else []


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

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _as_text(v) for k, v in value.items()}
        return {"heading": _as_text(value)}


class PlanColumn(BaseModel):
    heading: Optional[str] = Field(
        default=None, description="Column heading (one line)."
    )
    bullets: List[str] = Field(
        default_factory=list,
        description="Column bullets; prefix '- ' for a sub-bullet.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                "heading": _as_text(value.get("heading") or value.get("title")),
                "bullets": _as_text_list(value.get("bullets") or value.get("text")),
            }
        return {"bullets": _as_text_list(value)}


class SlidePlan(BaseModel):
    pattern: str = Field(
        default="",
        description="A pattern id from the catalogue, or an intent name.",
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
    # Set when the model sent something that is not a slide object at all.
    invalid_entry: SkipJsonSchema[Optional[str]] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"invalid_entry": str(value)[:80]}
        return value

    @field_validator("title", "subtitle", "image", "notes", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Optional[str]:
        return _as_text(value)

    @field_validator("pattern", mode="before")
    @classmethod
    def _pattern(cls, value: Any) -> str:
        return _as_text(value) or ""

    @field_validator("bullets", "images", mode="before")
    @classmethod
    def _texts(cls, value: Any) -> List[str]:
        return _as_text_list(value)

    @field_validator("columns", "items", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [v for v in value if v is not None]
        return [value]


class DeckPlan(BaseModel):
    slides: List[SlidePlan]
    file_name: Optional[str] = Field(
        default=None, description="Short file name for the deck; '.pptx' is added."
    )


class Resolution(BaseModel):
    pattern: Pattern
    # Human-readable reason when the requested pattern was not used as is.
    substitution: Optional[str] = None


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


def infer_intent(slide: SlidePlan) -> str:
    """The intent a slide's content implies, when its pattern cannot be used."""
    if len(slide.columns) >= 2:
        return "two_columns"
    if slide.items:
        numbers = [i.number for i in slide.items if i.number]
        if numbers and all(lexicon.is_year(n) for n in numbers):
            return "steps"
        if all(not (i.text or i.label) for i in slide.items):
            return "agenda"
        return "cards"
    if slide.image or slide.images:
        return "image_text"
    if slide.bullets:
        return "content" if slide.title else "statement"
    if slide.subtitle:
        return "title"
    if slide.title:
        return "section"
    return "fixed"


def _for_intent(
    inventory: TemplateInventory, intent: str
) -> Tuple[Optional[Pattern], Optional[str]]:
    direct = best_for_intent(inventory, intent)
    if direct is not None:
        return direct, None
    for fallback in DEGRADATION.get(intent, ()):
        candidate = best_for_intent(inventory, fallback)
        if candidate is not None:
            return candidate, intent
    return None, intent


_NUMBERED_ID = re.compile(r"^(layout|slide)\s*[:#_ -]?\s*(\d+)$", re.IGNORECASE)


def _fits(pattern: Pattern, slide: SlidePlan) -> bool:
    """Whether a pattern has somewhere to put the slide's main content."""
    roles = [z.role for z in pattern.zones]
    body_like = sum(1 for r in roles if r in ("body", "caption", "subtitle"))
    if len(slide.columns) >= 2 and body_like < 2:
        return False
    if slide.items and not pattern.groups:
        return False
    if slide.bullets and not body_like and not pattern.groups:
        return False
    return True


def _loose_match(inventory: TemplateInventory, requested: str) -> Optional[Pattern]:
    """A pattern the model meant but did not name exactly: `slide:12` read as
    the 12th slide, `layout 3` as the 4th layout, or the pattern's label."""
    match = _NUMBERED_ID.match(requested.strip())
    if match:
        kind, number = match.group(1).lower(), int(match.group(2))
        for pattern in included_patterns(inventory):
            if pattern.source == kind and pattern.source_index == number:
                return pattern
    wanted = lexicon.normalize(requested)
    if wanted:
        for pattern in included_patterns(inventory):
            if lexicon.normalize(pattern.label) == wanted:
                return pattern
    return None


def resolve(inventory: TemplateInventory, slide: SlidePlan) -> Resolution:
    """Map a plan slide to a pattern, never failing while the template has one.

    Exact id → intent name → a loosely named pattern → the intent the slide's
    content implies; an excluded pattern stands in for its own intent. Every
    step past the exact match is reported as a substitution.
    """
    requested = (slide.pattern or "").strip()
    pattern = inventory.pattern(requested) if requested else None
    if pattern is not None and pattern.included:
        return Resolution(pattern=pattern)

    if requested in INTENTS:
        found, degraded_from = _for_intent(inventory, requested)
        if found is not None:
            reason = (
                f"no '{degraded_from}' pattern in this template, used '{found.label}' ({found.intent})"
                if degraded_from
                else None
            )
            return Resolution(pattern=found, substitution=reason)

    if pattern is None and requested:
        loose = _loose_match(inventory, requested)
        if loose is not None and _fits(loose, slide):
            return Resolution(
                pattern=loose,
                substitution=f"'{requested}' is not a pattern id, used '{loose.id}' (\"{loose.label}\")",
            )

    intent = pattern.intent if pattern is not None else infer_intent(slide)
    found, _ = _for_intent(inventory, intent)
    if found is None:
        found, _ = _for_intent(inventory, "content")
    if found is None:
        included = included_patterns(inventory)
        if not included:
            raise ValueError("This template offers no usable pattern.")
        found = included[0]
    if pattern is not None:
        why = f"'{requested}' is excluded from this template"
    elif requested:
        why = f"'{requested}' is not a pattern of this template"
    else:
        why = "no pattern given"
    return Resolution(
        pattern=found,
        substitution=f"{why}, used '{found.id}' (\"{found.label}\", {found.intent}) from the slide's content",
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
