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

"""The deck plan the agent hands to the build tool: content only, with an
optional ``kind`` last. Which template slide shows each entry is decided in
:mod:`assign`; this module also says, in plan fields, what a pattern holds.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    Pattern,
    RepeatGroup,
    SlideKind,
    Zone,
)

# The plan field a zone of each role is filled from: the catalogue names these
# to the agent, since a role name it cannot map to a field is content lost.
# Roles absent here are never filled.
SLIDE_FIELDS: Dict[str, str] = {
    "title": "title",
    "subtitle": "subtitle",
    "body": "bullets",
    "caption": "bullets",
    "heading": "columns.heading",
}
ITEM_KEYS = ("number", "heading", "text", "label", "image")
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

# Small models get JSON shapes wrong (a list as one string, a number as an
# int): every model below coerces what it can, since a validation error would
# reach the user as an opaque tool failure.


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
        # A bullet written as {heading, text} keeps both.
        named = [_as_text(value.get(k)) for k in ("heading", "title", "text")]
        if any(named):
            return ": ".join(t for t in named if t)
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


def _empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _seq(value: Any) -> List[Any]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _with_aliases(value: Dict[str, Any], aliases: Dict[str, str]) -> Dict[str, Any]:
    """Rename the field names a model guesses from zone roles to the plan's
    own. A field given under its name and an alias keeps both texts (first-wins
    dropped one silently); only ``kind`` keeps the first."""
    out = {k: v for k, v in value.items() if k not in aliases}
    for alias, field in aliases.items():
        extra = value.get(alias)
        if _empty(extra):
            continue
        current = out.get(field)
        if _empty(current):
            out[field] = extra
        elif field != "kind" and _as_text(extra) != _as_text(current):
            out[field] = _seq(current) + _seq(extra)
    return out


def _quote(value: Any) -> str:
    text = " ".join((_as_text(value) or "").split())
    return text if len(text) <= 40 else text[:39] + "…"


def _ignored(value: Dict[str, Any], known: set[str]) -> List[str]:
    """Keys that match no field nor alias, with their text: content the deck
    would not hold. A re-validated dump carries the earlier ones."""
    carried = list(value.get("ignored_fields") or [])
    return carried + [
        f"{key} '{_quote(content)}'"
        for key, content in value.items()
        if key not in known and not _empty(content)
    ]


# The catalogue shows these zone roles; a model naturally reuses them as keys.
_ITEM_ALIASES = {
    "body": "text",
    "description": "text",
    "value": "number",
    "title": "heading",
}
_COLUMN_ALIASES = {
    "title": "heading",
    "text": "bullets",
    "body": "bullets",
    "content": "bullets",
}
_SLIDE_ALIASES = {
    "body": "bullets",
    "text": "bullets",
    "content": "bullets",
    # What the first schema called it.
    "pattern": "kind",
    "type": "kind",
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

    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"heading": _as_text(value)}
        renamed = _with_aliases(value, _ITEM_ALIASES)
        texts = {k: _as_text(renamed.get(k)) for k in ITEM_KEYS}
        known = set(cls.model_fields) | set(_ITEM_ALIASES)
        return {**texts, "ignored_fields": _ignored(value, known)}


class PlanColumn(BaseModel):
    heading: Optional[str] = Field(
        default=None, description="Column heading (one line)."
    )
    bullets: List[str] = Field(
        default_factory=list,
        description="Column bullets; prefix '- ' for a sub-bullet.",
    )

    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"bullets": _as_text_list(value)}
        renamed = _with_aliases(value, _COLUMN_ALIASES)
        known = set(cls.model_fields) | set(_COLUMN_ALIASES)
        return {
            "heading": _as_text(renamed.get("heading")),
            "bullets": _as_text_list(renamed.get("bullets")),
            "ignored_fields": _ignored(value, known),
        }


def _cells(value: Any) -> List[str]:
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, (list, tuple)):
        value = [value]
    return [(_as_text(cell) or "").strip() for cell in value]


class PlanTable(BaseModel):
    """A data table: column titles and rows of cells, filled into a table the
    template holds."""

    header: List[str] = Field(
        default_factory=list, description="Column titles, one per column."
    )
    rows: List[List[str]] = Field(
        default_factory=list,
        description="Rows of cells, each as many cells as the header; short text.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            value = {"rows": value}
        if not isinstance(value, dict):
            return {"rows": [[_as_text(value) or ""]]}
        header = value.get("header") or value.get("headers") or value.get("columns")
        rows = value.get("rows") or value.get("data") or value.get("body") or []
        if not isinstance(rows, (list, tuple)):
            rows = [rows]
        # Rows written as objects name their columns.
        first = next((r for r in rows if isinstance(r, dict)), None)
        if not header and first is not None:
            header = list(first)
        header_cells = _cells(header) if header else []
        cells = [
            [(_as_text(r.get(h)) or "").strip() for h in header_cells]
            if isinstance(r, dict) and header_cells
            else _cells(r)
            for r in rows
            if r is not None
        ]
        cells = [r for r in cells if any(r)]
        # Ragged rows are padded: a missing cell is an empty one.
        width = max([len(header_cells)] + [len(r) for r in cells])
        return {
            "header": header_cells + [""] * (width - len(header_cells))
            if header_cells
            else [],
            "rows": [r + [""] * (width - len(r)) for r in cells],
        }

    @property
    def width(self) -> int:
        return max([len(self.header)] + [len(r) for r in self.rows])

    def has_content(self) -> bool:
        return any(self.header) or any(any(r) for r in self.rows)


class SlidePlan(BaseModel):
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
    table: Optional[PlanTable] = Field(
        default=None,
        description="A data table {header, rows}; only on a kind that lists a table.",
    )
    notes: Optional[str] = Field(default=None, description="Speaker notes.")
    # Last on purpose: the model writes the content first, then names its kind.
    kind: Optional[SlideKind] = Field(
        default=None,
        description="Optional kind of slide; left out, it is inferred from the content.",
    )
    # Set when the model sent something that is not a slide object at all.
    invalid_entry: SkipJsonSchema[Optional[str]] = None
    # Keys of the call that match no field and no alias (`key 'text'`): the
    # assigner returns them as a problem rather than drop their text.
    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)
    # The template slide the delivered deck shows it on: kept while it fits.
    built_on: SkipJsonSchema[Optional[str]] = None
    # Set by a `like` change: the template slide asked for, and the slide whose
    # design it is (file numbering); cleared once the deck is delivered.
    asked_design: SkipJsonSchema[Optional[str]] = None
    asked_from: SkipJsonSchema[Optional[int]] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"invalid_entry": str(value)[:80]}
        renamed = _with_aliases(value, _SLIDE_ALIASES)
        known = set(cls.model_fields) | set(_SLIDE_ALIASES)
        return {**renamed, "ignored_fields": _ignored(value, known)}

    @field_validator("title", "subtitle", "image", "notes", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Optional[str]:
        return _as_text(value)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> Optional[str]:
        """An unknown kind is dropped: the content then decides."""
        text = lexicon.normalize(_as_text(value) or "").replace(" ", "_")
        text = lexicon.LEGACY_KINDS.get(text, text)
        return text if text in SLIDE_KINDS else None

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
        or (slide.table is not None and slide.table.has_content())
    )


# --- what a pattern holds, in plan fields ------------------------------------------------


# Chars per word, space included: errs short of French business prose (~6), so a
# word budget never promises more than the measured chars hold.
CHARS_PER_WORD = 7


def word_budget(chars_per_line: int, lines: int) -> str:
    """A room as a word count: small models follow words, not characters."""
    per_line = (chars_per_line + 1) // CHARS_PER_WORD
    if per_line == 0:
        return "1 short word"
    words = per_line * lines
    return "1 word" if words == 1 else f"≤{words} words"


def capacity_text(chars_per_line: int, lines: int) -> str:
    """How a zone's room is quoted to the agent, in the tool description and errors."""
    chars = f"≈{chars_per_line} chars" + (f" × {lines} lines" if lines > 1 else "")
    return f"{word_budget(chars_per_line, lines)} ({chars})"


def _room(zones: Sequence[Zone]) -> Optional[Tuple[int, int]]:
    """The room the agent can count on across zones filled from one field: the
    tightest one, since that is the zone that truncates. A zone that grows with
    its text has no limit to quote."""
    bounded = [z for z in zones if not z.grows and z.chars_per_line and z.max_lines]
    if not bounded:
        return None
    tightest = min(bounded, key=lambda z: (z.chars_per_line or 0) * (z.max_lines or 0))
    return tightest.chars_per_line or 1, tightest.max_lines or 1


def _limit(zones: Sequence[Zone]) -> str:
    room = _room(zones)
    return " " + capacity_text(*room) if room else ""


def _required(zones: Sequence[Zone]) -> str:
    """A framed picture shows its frame when left empty: it needs a picture."""
    return " (required)" if any(z.framed for z in zones) else ""


def table_summary(zone: Zone) -> str:
    spec = zone.table
    if spec is None:
        return "table"
    widths = sorted(set(spec.columns))
    per_cell = (
        f"≈{widths[0]}"
        if len(widths) == 1
        else "≈" + "/".join(str(c) for c in spec.columns)
    )
    head = "header + " if spec.header else ""
    return (
        f"table 2 to {len(spec.columns)} columns ({per_cell} chars per cell line), "
        f"{head}≈{zone.max_lines} lines of rows"
    )


def _item_fields(group: RepeatGroup) -> Dict[str, List[Zone]]:
    """The item fields one repeat group holds, with their zones."""
    fields: Dict[str, List[Zone]] = {}
    for item in group.items:
        for zone in item:
            field = ITEM_FIELDS.get(zone.role)
            if field:
                fields.setdefault(field, []).append(zone)
    if (
        "heading" not in fields
        and "label" not in fields
        and len(fields.get("text", [])) == group.count
    ):
        # The renderer writes the heading in bold atop the text (`_heading_lead`).
        fields = {("heading+text" if k == "text" else k): v for k, v in fields.items()}
    return fields


def group_summary(group: RepeatGroup) -> str:
    """What one repeat group's items hold: ``items max N [field ≈C chars, …]``."""
    shown = ", ".join(
        name + (_required(zones) if name == "image" else _limit(zones))
        for name, zones in _item_fields(group).items()
    )
    # "max", not "×N": told `items×8`, an agent pads a five-point agenda.
    return f"items max {group.count} [{shown}]"


def zone_summary(pattern: Pattern) -> str:
    """The plan fields one pattern holds, with their limits."""
    if not pattern.fillable:
        return "shown as is: no content, or only its own title"
    parts = [
        f"{field}{f'×{len(same)}' if len(same) > 1 else ''}{_limit(same)}"
        for field, same in _slide_fields(pattern)
    ]
    images = [z for z in pattern.zones if z.role == "image"]
    if images:
        parts.append(f"images×{len(images)}{_required(images)}")
    parts.extend(table_summary(z) for z in pattern.zones if z.role == "table")
    parts.extend(group_summary(g) for g in pattern.groups)
    return "; ".join(parts) or "no editable zone"


def _slide_fields(pattern: Pattern) -> List[Tuple[str, List[Zone]]]:
    """The slide fields one pattern's own zones are filled from, as the renderer
    fills them, each with its zones."""
    found: List[Tuple[str, List[Zone]]] = []
    seen: set[str] = set()
    field_of = {z.key: SLIDE_FIELDS.get(z.role) for z in pattern.zones}
    headings = [z for z in pattern.zones if z.role == "heading"]
    if headings and "title" not in field_of.values():
        # The renderer writes the title into the leftmost heading (`_assign_text`).
        first = min(headings, key=lambda z: (z.box.x // 150, z.box.y))
        field_of[first.key] = "title"
    fields_of = set(field_of.values())
    for zone in pattern.zones:
        field = field_of[zone.key]
        if field is None or field in seen:
            continue
        seen.add(field)
        same = [z for z in pattern.zones if field_of[z.key] == field]
        if field == "bullets" and pattern.kind in ("cover", "section"):
            # Under a cover title the body holds the subtitle (see `_assign_text`).
            if "subtitle" in fields_of:
                continue
            field = "subtitle"
        # Several body zones are reached through `columns` only (a closing
        # slide takes one bullet per zone instead).
        if field == "bullets" and len(same) > 1:
            field = (
                "bullets, one per line,"
                if pattern.kind == "closing"
                else "columns.bullets"
            )
        found.append((field, same))
    return found


# Catalogue field names → the schema fields they are written in.
_SCHEMA_FIELDS = {
    "bullets, one per line,": ("bullets",),
    "heading+text": ("items.text",),
    "image": (),
}


def field_hints(patterns: Sequence[Pattern]) -> Tuple[Tuple[str, str], ...]:
    """Per schema field, its room on this template: per kind the
    roomiest variant's, so a text within it always has a slide of that kind,
    quoted as the most common room plus the kinds that differ."""
    rooms: Dict[str, Dict[str, Tuple[int, int]]] = {}
    for pattern in (p for p in patterns if p.fillable):
        named = _slide_fields(pattern) + [
            (f"items.{f}", z)
            for g in pattern.groups
            for f, z in _item_fields(g).items()
        ]
        for name, zones in named:
            room = _room(zones)
            for field in _SCHEMA_FIELDS.get(name.removeprefix("items."), (name,)):
                best = rooms.setdefault(field, {}).get(pattern.kind)
                if room and (best is None or room[0] * room[1] > best[0] * best[1]):
                    rooms[field][pattern.kind] = room
    hints = []
    for field, by_kind in sorted(rooms.items()):
        if not by_kind:
            continue
        counts = Counter(by_kind.values())
        common = max(counts, key=lambda r: (counts[r], r[0] * r[1]))
        # A room only one kind has is named after it ("cover ≈32 chars").
        named = [k for k in SLIDE_KINDS if by_kind.get(k) == common]
        lead = f"{named[0]} " if counts[common] == 1 else ""
        others = "".join(
            f"; {kind} {capacity_text(*by_kind[kind])}"
            for kind in SLIDE_KINDS
            if kind in by_kind and by_kind[kind] != common
        )
        hints.append((field, f"Room: {lead}{capacity_text(*common)}{others}."))
    return tuple(hints)
