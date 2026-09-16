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

# The plan field a zone of each role is filled from. The catalogue names these
# to the agent and the scoring below asks whether a pattern can show them, so a
# pattern is never chosen for content it has nowhere to put. Roles absent here
# are never filled.
SLIDE_FIELDS: Dict[str, str] = {
    "title": "title",
    "subtitle": "subtitle",
    "body": "bullets",
    "caption": "bullets",
    "heading": "columns.heading",
}
ITEM_FIELDS: Dict[str, str] = {
    "number": "number",
    "heading": "heading",
    "title": "heading",
    "subtitle": "heading",
    "body": "text",
    "caption": "text",
    "label": "label",
    "image": "image",
}

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
        named = value.get("text") or value.get("heading") or value.get("title")
        if named is not None:
            return _as_text(named)
        # A model that wrapped a bullet under a key of its own invention still
        # meant the text inside; dropping it loses content without a word.
        texts = [t for t in (_as_text(v) for v in value.values()) if t and t.strip()]
        return "\n".join(texts) or None
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


def _with_aliases(value: Dict[str, Any], aliases: Dict[str, str]) -> Dict[str, Any]:
    """Rename the field names a model guesses from zone roles to the plan's
    own; a field given under its own name wins over an alias.

    Two aliases of the same field (``text`` and ``content`` both meaning
    ``bullets``) are kept in order rather than first-wins, which used to drop
    one of them silently.
    """
    out = {k: v for k, v in value.items() if k not in aliases}
    extra: Dict[str, List[Any]] = {}
    for alias, field in aliases.items():
        if alias in value and not out.get(field):
            extra.setdefault(field, []).append(value[alias])
    for field, values in extra.items():
        out[field] = values[0] if len(values) == 1 else values
    return out


# The catalogue shows these zone roles; a model naturally reuses them as keys.
_ITEM_ALIASES = {
    "body": "text",
    "description": "text",
    "value": "number",
    "title": "heading",
}
_SLIDE_ALIASES = {"body": "bullets", "text": "bullets", "content": "bullets"}


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
            return {
                k: _as_text(v) for k, v in _with_aliases(value, _ITEM_ALIASES).items()
            }
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
    # Keys of the call that match no field and no alias: their content is not in
    # the deck, and the agent can only fix that if it is told.
    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"invalid_entry": str(value)[:80]}
        renamed = _with_aliases(value, _SLIDE_ALIASES)
        known = set(cls.model_fields) | set(_SLIDE_ALIASES)
        ignored = [
            key
            for key, content in value.items()
            if key not in known and content not in (None, "", [], {})
        ]
        return {**renamed, "ignored_fields": ignored}

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


def _pattern_fields(pattern: Pattern) -> Tuple[set, set]:
    """(slide fields, item fields) a pattern can display."""
    slide_fields = {
        SLIDE_FIELDS[z.role] for z in pattern.zones if z.role in SLIDE_FIELDS
    }
    item_fields = {
        ITEM_FIELDS[z.role]
        for group in pattern.groups
        for item in group.items
        for z in item
        if z.role in ITEM_FIELDS
    }
    return slide_fields, item_fields


# How much losing each field costs. A title has nowhere else to go; column
# headings fall back to a bold first bullet, so losing one hurts less.
_FIELD_WEIGHT: Dict[str, float] = {
    "title": 3.0,
    "bullets": 3.0,
    "columns": 3.0,
    "items": 3.0,
    "heading": 2.0,
    "text": 2.0,
    "number": 2.0,
    "image": 2.0,
    "subtitle": 1.0,
    "label": 1.0,
    "columns.heading": 1.0,
}


def _shown_fields(pattern: Pattern, slide: SlidePlan) -> Tuple[float, float]:
    """What share of the slide's content this pattern can show, weighted by how
    costly each field is to lose. A field with nowhere to go never reaches the
    reader."""
    available, item_fields = _pattern_fields(pattern)
    bodies = sum(1 for z in pattern.zones if SLIDE_FIELDS.get(z.role) == "bullets")
    given = shown = 0.0

    def check(name: str, filled, can_show: bool) -> None:
        nonlocal given, shown
        if filled:
            weight = _FIELD_WEIGHT[name]
            given += weight
            shown += weight if can_show else 0.0

    check(
        "title",
        slide.title,
        "title" in available
        # With columns the headings own those zones: the title is then lost.
        or ("columns.heading" in available and not slide.columns),
    )
    check("subtitle", slide.subtitle, "subtitle" in available or bodies > 0)
    check(
        "bullets", slide.bullets, bodies > 0 or bool(item_fields & {"text", "heading"})
    )
    check("columns", len(slide.columns) >= 2, bodies >= 2)
    check(
        "columns.heading",
        any(c.heading for c in slide.columns),
        "columns.heading" in available,
    )
    check("items", slide.items, bool(pattern.groups))
    for name in ("number", "heading", "text", "label"):
        check(
            name, any(getattr(item, name) for item in slide.items), name in item_fields
        )
    check(
        "image",
        slide.image or slide.images,
        any(z.role == "image" for z in pattern.zones) or "image" in item_fields,
    )
    return shown, given


# A picture zone left unfilled is a white hole the reader reads as a mistake.
_IMAGE_HOLE = 12.0
# An example slide the designer built outranks a bare layout, but never at the
# cost of a field that would be lost.
_PREFERRED_BONUS = 6.0


def _overflow_penalty(pattern: Pattern, slide: SlidePlan) -> float:
    """What the slide's text would lose on this pattern's body.

    Only overflow is scored. A body roomier than the content is merely plain;
    one too small truncates, and choosing it throws content away.
    """
    room = sum(
        z.max_chars or 0
        for z in pattern.zones
        if SLIDE_FIELDS.get(z.role) == "bullets" and not z.grows
    )
    text = sum(len(b) for b in slide.bullets) + sum(
        len(b) for column in slide.columns for b in column.bullets
    )
    if not room or text <= room:
        return 0.0
    return -30.0 * min(1.0, (text - room) / room)


def score_pattern(pattern: Pattern, slide: SlidePlan) -> float:
    """How well a pattern serves one slide's content. Higher is better."""
    shown, given = _shown_fields(pattern, slide)
    value = 100.0 * (shown / given if given else 1.0)
    unfilled = sum(1 for z in pattern.zones if z.role == "image")
    if unfilled and not (slide.image or slide.images):
        value -= _IMAGE_HOLE * unfilled
    if pattern.preferred:
        value += _PREFERRED_BONUS
    return value + _overflow_penalty(pattern, slide)


def best_for_intent(
    inventory: TemplateInventory, intent: str, slide: Optional[SlidePlan] = None
) -> Optional[Pattern]:
    """The included pattern of ``intent`` that best serves ``slide``.

    Without a slide, the preferred example slide then the first layout, in
    inventory order. With one, the pattern is scored on the content it is
    actually given: taking the first of the intent is how a cards slide ended
    up on a pattern whose cards have no heading, and an image layout on a plan
    carrying no image. A fixed slide asked by intent closes the deck, so one
    named as a closing slide ("Merci", "Thank you") comes first.
    """
    candidates = [p for p in included_patterns(inventory) if p.intent == intent]
    if not candidates:
        return None
    if intent == "fixed":
        closing = [
            p
            for p in candidates
            if lexicon.name_matches(p.label, lexicon.CLOSING_NAMES)
            or lexicon.name_matches(p.name, lexicon.CLOSING_NAMES)
        ]
        if closing:
            return closing[0]
    if slide is not None:
        return max(candidates, key=lambda p: score_pattern(p, slide))
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


# Keeps the intent the slide asked for unless a fallback serves it markedly
# better — a nudge, not enough to overturn a field the requested intent shows.
_REQUESTED_INTENT_BONUS = 3.0


def _for_intent(
    inventory: TemplateInventory, intent: str, slide: Optional[SlidePlan] = None
) -> Tuple[Optional[Pattern], Optional[str]]:
    direct = best_for_intent(inventory, intent, slide)
    if slide is None:
        if direct is not None:
            return direct, None
        for fallback in DEGRADATION.get(intent, ()):
            candidate = best_for_intent(inventory, fallback)
            if candidate is not None:
                return candidate, intent
        return None, intent

    # The template may hold no pattern of this intent that can show the slide's
    # content; a neighbouring intent that can beats one that cannot.
    options: List[Tuple[Pattern, Optional[str], float]] = []
    if direct is not None:
        options.append(
            (direct, None, score_pattern(direct, slide) + _REQUESTED_INTENT_BONUS)
        )
    for fallback in DEGRADATION.get(intent, ()):
        candidate = best_for_intent(inventory, fallback, slide)
        if candidate is not None:
            options.append((candidate, intent, score_pattern(candidate, slide)))
    if not options:
        return None, intent
    pattern, degraded_from, _ = max(options, key=lambda option: option[2])
    return pattern, degraded_from


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
        found, degraded_from = _for_intent(inventory, requested, slide)
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
    found, _ = _for_intent(inventory, intent, slide)
    if found is None:
        found, _ = _for_intent(inventory, "content", slide)
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
