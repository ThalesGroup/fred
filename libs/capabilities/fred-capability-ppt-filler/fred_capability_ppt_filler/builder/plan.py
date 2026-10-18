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

import math
import re
from collections import Counter
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

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


# A key figure's direction, shown as an arrow glyph before it (never a colour).
Trend = Literal["up", "down", "flat"]
TREND_GLYPHS: Dict[str, str] = {"up": "▲", "down": "▼", "flat": "►"}

# The catalogue shows these zone roles; a model naturally reuses them as keys.
_ITEM_ALIASES = {
    "body": "text",
    "description": "text",
    "value": "number",
    "title": "heading",
    "direction": "trend",
    "evolution": "trend",
    "tendency": "trend",
}
_COLUMN_ALIASES = {
    "title": "heading",
    "text": "bullets",
    "body": "bullets",
    "content": "bullets",
}
# Names a model may give `repeat_layout`, in a slide or as an edit `field`.
REPEAT_ALIASES = ("same_layout", "keep_layout", "repeat_previous_layout")


def as_flag(value: Any) -> bool:
    """A loose yes: true, 1, "true", "yes", "oui"; anything else is no."""
    if isinstance(value, (list, tuple)):
        return any(as_flag(v) for v in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return (_as_text(value) or "").strip().lower() in ("true", "yes", "oui", "1")


_SLIDE_ALIASES = {
    "body": "bullets",
    "text": "bullets",
    "content": "bullets",
    # What the first schema called it.
    "pattern": "kind",
    "type": "kind",
    "message": "takeaway",
    "key_message": "takeaway",
    "key_takeaway": "takeaway",
    "sources": "source",
    "data_source": "source",
    **{alias: "repeat_layout" for alias in REPEAT_ALIASES},
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
    trend: Optional[Trend] = Field(
        default=None,
        description="Optional, with a number: up, down or flat, shown as an arrow "
        "before the figure.",
    )

    # A `trend` naming no direction: the text sent, for the note.
    asked_trend: SkipJsonSchema[Optional[str]] = None
    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"heading": _as_text(value)}
        renamed = _with_aliases(value, _ITEM_ALIASES)
        texts = {k: _as_text(renamed.get(k)) for k in ITEM_KEYS}
        trend, asked = _named(renamed.get("trend"), _TREND_NAMES)
        if not trend and _empty(renamed.get("trend")):
            asked = value.get("asked_trend")
        known = set(cls.model_fields) | set(_ITEM_ALIASES)
        return {
            **texts,
            "trend": trend,
            "asked_trend": None if trend else asked,
            "ignored_fields": _ignored(value, known),
        }


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


_TABLE_ALIASES = {
    "total": "total_row",
    "totals_row": "total_row",
    "has_total": "total_row",
    "last_row_total": "total_row",
    "highlighted_row": "highlight_row",
    "emphasis_row": "highlight_row",
    "highlighted_column": "highlight_column",
    "emphasis_column": "highlight_column",
}


def _total(value: Any) -> bool:
    """A loose yes, or a word naming the last row ("last", "dernière")."""
    if as_flag(value):
        return True
    text = (
        lexicon.normalize(_as_text(_seq(value)[0]) or "") if not _empty(value) else ""
    )
    return text in ("last", "last row", "derniere", "derniere ligne", "oui", "total")


def _reference(value: Any) -> Optional[int | str]:
    """A row or column named by its index or its text; the first of a list."""
    first = _seq(value)[0] if not _empty(value) else None
    if isinstance(first, bool) or first is None:
        return None
    if isinstance(first, int):
        return first
    if isinstance(first, float) and first.is_integer():
        return int(first)
    text = (_as_text(first) or "").strip()
    return text[:60] or None


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
    total_row: bool = Field(
        default=False,
        description="Optional: true when the last row is a total, shown as one.",
    )
    highlight_row: Optional[int | str] = Field(
        default=None,
        description="Optional: the one row that matters, by its first cell's text or "
        "its index in rows (from 0).",
    )
    highlight_column: Optional[int | str] = Field(
        default=None,
        description="Optional: the one column that matters, by its header text or "
        "its index (from 0).",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            value = {"rows": value}
        if not isinstance(value, dict):
            return {"rows": [[_as_text(value) or ""]]}
        value = _with_aliases(value, _TABLE_ALIASES)
        intents = {
            "total_row": _total(value.get("total_row")),
            "highlight_row": _reference(value.get("highlight_row")),
            "highlight_column": _reference(value.get("highlight_column")),
        }
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
            **intents,
        }

    @property
    def width(self) -> int:
        return max([len(self.header)] + [len(r) for r in self.rows])

    def has_content(self) -> bool:
        return any(self.header) or any(any(r) for r in self.rows)


# --- charts ---------------------------------------------------------------------------

CHART_TYPES = (
    "column",
    "bar",
    "line",
    "pie",
    "doughnut",
    "stacked_column",
    "area",
    "stacked_bar",
    "radar",
    "scatter",
    "bubble",
)
# Types drawn from numeric points {x, y, size} rather than categories.
XY_TYPES = ("scatter", "bubble")
STACKED_TYPES = ("stacked_column", "stacked_bar")
# Readability caps of every chart, whatever its zone.
MAX_SERIES = 4
MAX_SLICES = 6
# Chart frames one template slide may hold, each filled from `charts`.
MAX_CHARTS_PER_SLIDE = 4
_CHART_TYPE_NAMES = {
    "columns": "column",
    "histogram": "column",
    "vertical bar": "column",
    "bars": "bar",
    "horizontal bar": "bar",
    "lines": "line",
    "curve": "line",
    "camembert": "pie",
    "donut": "doughnut",
    "ring": "doughnut",
    "stacked": "stacked_column",
    "stacked columns": "stacked_column",
    "column stacked": "stacked_column",
    "areas": "area",
    "stacked bar": "stacked_bar",
    "stacked bars": "stacked_bar",
    "horizontal stacked": "stacked_bar",
    "horizontal stacked bar": "stacked_bar",
    "spider": "radar",
    "web": "radar",
    "toile": "radar",
    "araignee": "radar",
    "xy": "scatter",
    "scatter plot": "scatter",
    "nuage de points": "scatter",
    "dispersion": "scatter",
    "correlation": "scatter",
    "bubbles": "bubble",
    "bulles": "bubble",
}
# Design keys a model adds to a chart: the template decides them, never the call.
_CHART_STYLE_KEYS = frozenset(
    ("color", "colors", "colour", "colours", "palette", "style", "theme", "legend")
    + ("position", "size", "width", "height", "font", "fonts", "x_axis", "y_axis")
)
_STYLE_NAMES = frozenset(lexicon.normalize(k) for k in _CHART_STYLE_KEYS)
# What a pie's or doughnut's slice labels show, and the words models use for it.
PieShow = Literal["share", "value", "both"]
_SHOW_NAMES: Dict[str, PieShow] = {
    **dict.fromkeys(
        ("share", "shares", "percent", "percents", "percentage", "percentages", "%")
        + ("pct", "pourcentage", "pourcentages", "part", "parts", "ratio"),
        "share",
    ),
    **dict.fromkeys(
        ("value", "values", "number", "numbers", "count", "counts", "absolute")
        + ("amount", "amounts", "valeur", "valeurs", "nombre", "nombres"),
        "value",
    ),
    **dict.fromkeys(
        ("both", "all", "value and share", "values and percentages")
        + ("value and percentage", "les deux", "valeur et pourcentage"),
        "both",
    ),
}
# Intents: what matters on a chart, in the words models use for it.
ChartSort = Literal["desc", "asc", "given"]
StackedAs = Literal["value", "percent"]
_SORT_NAMES: Dict[str, ChartSort] = {
    **dict.fromkeys(
        ("desc", "descending", "decreasing", "largest first", "biggest first")
        + ("highest first", "high to low", "largest", "true", "yes", "decroissant")
        + ("ordre decroissant", "du plus grand au plus petit", "par ordre decroissant"),
        "desc",
    ),
    **dict.fromkeys(
        ("asc", "ascending", "increasing", "smallest first", "lowest first")
        + (
            "low to high",
            "croissant",
            "ordre croissant",
            "du plus petit au plus grand",
        ),
        "asc",
    ),
    **dict.fromkeys(
        ("given", "as given", "none", "no", "false", "original", "unsorted", "as is")
        + ("order given", "aucun", "tel quel", "ordre donne", "ordre d origine"),
        "given",
    ),
}
_STACKED_NAMES: Dict[str, StackedAs] = {
    **dict.fromkeys(
        ("percent", "percents", "percentage", "percentages", "%", "100%", "100 %")
        + ("100", "share", "shares", "pourcentage", "pourcentages", "normalized"),
        "percent",
    ),
    **dict.fromkeys(
        ("value", "values", "absolute", "number", "numbers", "valeur", "valeurs"),
        "value",
    ),
}
_TREND_NAMES: Dict[str, Trend] = {
    **dict.fromkeys(
        ("up", "rising", "rise", "increase", "increasing", "growth", "growing")
        + ("higher", "positive", "hausse", "en hausse", "augmentation", "croissance")
        + ("monte", "progression", "↑", "▲", "+"),
        "up",
    ),
    **dict.fromkeys(
        ("down", "falling", "fall", "decrease", "decreasing", "decline", "lower")
        + ("negative", "baisse", "en baisse", "diminution", "recul", "descend")
        + ("↓", "▼"),
        "down",
    ),
    **dict.fromkeys(
        ("flat", "stable", "steady", "unchanged", "constant", "level", "same")
        + ("inchange", "stagnation", "→", "►", "="),
        "flat",
    ),
}
_NUMBER = re.compile(r"^([^\d+\-.,]*?)\s*([+\-]?\d[\d\s.,']*)\s*(\D*)$")


def _chart_type(value: Any) -> Tuple[str, Optional[str]]:
    """The type to build and, for a type the builder does not offer, the one asked."""
    text = lexicon.normalize(_as_text(value) or "")
    text = re.sub(r"\s*(chart|graph|graphique|diagramme)\s*", " ", text).strip()
    if not text:
        return "column", None
    name = text.replace(" ", "_")
    if name in CHART_TYPES:
        return name, None
    found = _CHART_TYPE_NAMES.get(text)
    return (found, None) if found else ("column", text[:30])


def _named(value: Any, names: Mapping[str, Any]) -> Tuple[Optional[Any], Optional[str]]:
    """The word a mode names and, for words that name none, the text sent."""
    first = _seq(value)[0] if not _empty(value) else None
    if isinstance(first, bool):
        first = str(first)
    text = lexicon.normalize(_as_text(first) or "")
    if not text:
        return None, None
    found = names.get(text) or names.get(text.replace("+", " and "))
    return (found, None) if found else (None, text[:30])


def _show(value: Any) -> Tuple[Optional[PieShow], Optional[str]]:
    return _named(value, _SHOW_NAMES)


def _highlight(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """One name to emphasise; several names are the text sent, for the note."""
    names = [t.strip() for t in (_as_text(v) for v in _seq(value)) if t and t.strip()]
    if len(names) > 1:
        return None, _quote(", ".join(names))
    return (names[0][:60], None) if names else (None, None)


def _decimal(digits: str) -> Optional[float]:
    """``1 200``, ``12,5``, ``1,200.50``, ``1.200,5``: the last separator
    followed by other than three digits is the decimal one."""
    digits = re.sub(r"[\s']", "", digits)
    separators = [i for i, c in enumerate(digits) if c in ".,"]
    if separators:
        last = separators[-1]
        decimals = len(digits) - last - 1
        mixed = len({digits[i] for i in separators}) > 1
        # "0,125" is a decimal: no number is written with a leading 0 group.
        zero = digits[:last].lstrip("+-") == "0"
        if mixed or (digits.count(digits[last]) == 1 and (decimals != 3 or zero)):
            digits = re.sub(r"[.,]", "", digits[:last]) + "." + digits[last + 1 :]
        else:
            digits = re.sub(r"[.,]", "", digits)
    try:
        number = float(digits)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def read_number(value: Any) -> Tuple[Optional[float], str]:
    """A value as a number and the unit written around it (``"45 %"`` →
    ``(45.0, "%")``); ``(None, "")`` when it does not read as one."""
    if isinstance(value, bool) or value is None:
        return None, ""
    if isinstance(value, (int, float)):
        return (float(value), "") if math.isfinite(value) else (None, "")
    match = _NUMBER.match(
        str(value).replace("\u2212", "-").replace(" ", " ").replace(" ", " ")
    )
    if match is None:
        return None, ""
    number = _decimal(match.group(2))
    unit = (match.group(3).strip() + match.group(1).strip()).strip()
    if number is None or len(unit) > 6 or re.search(r"\d", unit):
        return None, ""
    return number, unit


POINT_AXES = ("x", "y", "size")
_POINT_ALIASES = {
    **dict.fromkeys(("z", "r", "radius", "weight", "volume", "sizes"), "size"),
    **dict.fromkeys(("name", "title", "text"), "label"),
}


def _point_like(value: Any) -> bool:
    if isinstance(value, dict):
        return any(k in value for k in ("x", "y"))
    return isinstance(value, (list, tuple)) and len(value) in (2, 3, 4)


class PlanPoint(BaseModel):
    """One point of a scatter or bubble chart."""

    x: Optional[float] = Field(default=None, description="Horizontal axis value.")
    y: Optional[float] = Field(default=None, description="Vertical axis value.")
    size: Optional[float] = Field(
        default=None, description="bubble only: the bubble's size, positive."
    )
    label: Optional[str] = Field(
        default=None, description="Optional short name of the point (1-2 words)."
    )
    # Axis values that did not read as numbers, with the text sent.
    unread: SkipJsonSchema[Dict[str, str]] = Field(default_factory=dict)
    units: SkipJsonSchema[Dict[str, str]] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            value = dict(zip(POINT_AXES + ("label",), value))
        elif not isinstance(value, dict):
            value = {"y": value}
        data = _with_aliases(value, _POINT_ALIASES)
        carried = dict(value.get("unread") or {})
        out: Dict[str, Any] = {"unread": {}, "units": {}}
        for axis in POINT_AXES:
            raw = data.get(axis)
            if _empty(raw):
                out[axis] = None
                if axis in carried:
                    out["unread"][axis] = carried[axis]
                continue
            number, unit = read_number(_seq(raw)[0])
            out[axis] = number
            if number is None:
                out["unread"][axis] = _quote(raw)[:20]
            elif isinstance(raw, str):
                out["units"][axis] = unit
        label = _as_text(data.get("label"))
        out["label"] = label.strip() if label and label.strip() else None
        return out


class PlanSeries(BaseModel):
    """One series of a chart: a name and one value per category, or its points."""

    name: str = Field(default="", description="Series name, shown in the legend.")
    values: List[Optional[float]] = Field(
        default_factory=list,
        description="One number per category, in the categories' order.",
        json_schema_extra=lambda schema: schema.update({"items": {"type": "number"}}),
    )
    # Values that did not read as numbers, by index, with the text sent.
    unread: SkipJsonSchema[Dict[int, str]] = Field(default_factory=dict)
    units: SkipJsonSchema[List[str]] = Field(default_factory=list, exclude=True)
    points: List[PlanPoint] = Field(
        default_factory=list,
        description="scatter and bubble only, instead of values: [{x, y, size, label}].",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            value = {"values": value}
        name = next(
            (value.get(k) for k in ("name", "label", "title") if value.get(k)), ""
        )
        points = value.get("points")
        raw = next(
            (value[k] for k in ("values", "data", "y") if value.get(k) is not None),
            [],
        )
        raw = list(raw) if isinstance(raw, (list, tuple)) else [raw]
        if points is None and isinstance(value.get("x"), (list, tuple)):
            points, raw = _parallel_points(value), []
        elif points is None and raw and all(_point_like(v) for v in raw):
            points, raw = raw, []
        carried = {int(k): v for k, v in (value.get("unread") or {}).items()}
        values: List[Optional[float]] = []
        unread: Dict[int, str] = {}
        units: List[str] = []
        for index, entry in enumerate(raw):
            number, unit = read_number(entry)
            values.append(number)
            if number is None:
                unread[index] = carried.get(index) or _quote(entry)[:20]
            elif isinstance(entry, str):
                units.append(unit)
        return {
            "name": _as_text(name) or "",
            "values": values,
            "unread": unread,
            "units": units,
            "points": [p for p in _seq(points or []) if p is not None],
        }


def _parallel_points(value: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """``{x: [...], y: [...], size: [...], labels: [...]}`` as one point per x."""
    aliases = {"values": "y", "names": "labels", "point_labels": "labels"}
    data = _with_aliases(
        dict(value), {**aliases, **dict.fromkeys(("z", "sizes", "radius"), "size")}
    )
    columns = {k: _seq(data.get(k) or []) for k in ("x", "y", "size")}
    labels = _seq(data.get("labels") or [])
    return [
        {
            "x": x,
            "y": columns["y"][i] if i < len(columns["y"]) else None,
            "size": columns["size"][i] if i < len(columns["size"]) else None,
            "label": labels[i] if i < len(labels) else None,
        }
        for i, x in enumerate(columns["x"])
    ]


class PlanChart(BaseModel):
    """A data chart: the model gives the numbers, the template its look."""

    type: str = Field(
        default="column",
        description="column | bar (horizontal) | line | pie | doughnut | stacked_column | "
        "area (one or two series) | stacked_bar (parts of a whole per category, long "
        "labels) | radar (3-8 criteria compared for 1-3 items) | scatter (how two "
        "measures relate across items; points {x, y}) | bubble (scatter plus a third "
        "measure as size).",
        json_schema_extra={"enum": list(CHART_TYPES)},
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Category labels: the x axis, or a pie's slices.",
    )
    series: List[PlanSeries] = Field(
        default_factory=list,
        description="Series, each {name, values}: one number per category; for "
        "scatter and bubble, each {name, points}.",
    )
    title: Optional[str] = Field(
        default=None, description="Optional caption of the chart itself."
    )
    unit: Optional[str] = Field(
        default=None, description="Optional unit of the values: '%', 'M€', 'days'."
    )
    show: Optional[PieShow] = Field(
        default=None,
        description="pie and doughnut only, what the slice labels show: share "
        "(percentages of the total), value (the numbers, with `unit`) or both. Left "
        "out: value when `unit` is set, else share.",
    )
    highlight: Optional[str] = Field(
        default=None,
        description="Optional: the one category (or, with several series, the one "
        "series) that matters, written as in categories or series. It is drawn in "
        "the accent colour and the rest in grey. A name, never a colour.",
    )
    sort: Optional[ChartSort] = Field(
        default=None,
        description="Optional: desc (largest first), asc (smallest first) or given "
        "(the order written, the default). Not for line or area charts.",
    )
    stacked_as: Optional[StackedAs] = Field(
        default=None,
        description="stacked_column and stacked_bar only: value (the default) or "
        "percent (every column or bar fills 100 %, to compare shares).",
    )
    x_title: Optional[str] = Field(
        default=None,
        description="scatter and bubble, required: what the horizontal axis measures.",
    )
    x_unit: Optional[str] = Field(
        default=None, description="scatter and bubble: unit of the x values."
    )
    y_title: Optional[str] = Field(
        default=None,
        description="scatter and bubble, required: what the vertical axis measures "
        "(its unit is `unit`).",
    )
    size_title: Optional[str] = Field(
        default=None, description="bubble: what the bubble size measures."
    )
    size_unit: Optional[str] = Field(
        default=None, description="bubble: unit of the sizes."
    )
    # Intent words that name nothing (field → text sent), for the note.
    asked_intents: SkipJsonSchema[Dict[str, str]] = Field(default_factory=dict)
    # An unknown type built as a column chart: the type asked, for the note.
    asked_type: SkipJsonSchema[Optional[str]] = None
    # A `show` naming no mode: the text sent, for the revision.
    asked_show: SkipJsonSchema[Optional[str]] = None
    # Design keys the call carried (colours, position): the template decides them.
    style_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)
    ignored_fields: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            value = {"series": value}
        if not isinstance(value, dict):
            return {"ignored_fields": [f"chart '{_quote(value)}'"]}
        value = dict(value)
        # An axis written as a word is its title; an axis object stays design.
        for axis in ("x", "y"):
            if isinstance(value.get(f"{axis}_axis"), str):
                value.setdefault(f"{axis}_title", value.pop(f"{axis}_axis"))
        aliases = {
            "chart_type": "type",
            "kind": "type",
            "labels": "categories",
            "x": "categories",
            "data": "series",
            "datasets": "series",
            "caption": "title",
            "units": "unit",
            "display": "show",
            "labels_as": "show",
            "show_as": "show",
            "emphasis": "highlight",
            "emphasize": "highlight",
            "emphasise": "highlight",
            "highlighted": "highlight",
            "focus": "highlight",
            "order": "sort",
            "sort_by": "sort",
            "sorting": "sort",
            "sort_order": "sort",
            "stacking": "stacked_as",
            **dict.fromkeys(("x_label", "x_axis_title", "xlabel", "x_name"), "x_title"),
            **dict.fromkeys(("y_label", "y_axis_title", "ylabel", "y_name"), "y_title"),
            **dict.fromkeys(
                ("size_label", "size_axis_title", "bubble_size"), "size_title"
            ),
            "x_units": "x_unit",
            "y_unit": "unit",
            "y_units": "unit",
            "size_units": "size_unit",
        }
        kind, asked = _chart_type(
            _with_aliases(value, {"chart_type": "type", "kind": "type"}).get("type")
        )
        xy = kind in XY_TYPES
        if xy:
            # On a scatter, `x` holds the x values, never the categories.
            aliases.pop("x")
        data = _with_aliases(value, aliases)
        if kind == "column" and value.get("asked_type"):
            asked = value["asked_type"]
        show, asked_show = _show(data.get("show"))
        sort, asked_sort = _named(data.get("sort"), _SORT_NAMES)
        stacked_as, asked_stacked = _named(data.get("stacked_as"), _STACKED_NAMES)
        highlight, asked_highlight = _highlight(data.get("highlight"))
        # A re-validated dump carries its unread words while the field stays empty.
        carried = dict(value.get("asked_intents") or {})
        asked_intents: Dict[str, str] = {}
        for field, text in (
            ("highlight", asked_highlight),
            ("sort", asked_sort),
            ("stacked_as", asked_stacked),
        ):
            text = text or (carried.get(field) if _empty(data.get(field)) else None)
            if text:
                asked_intents[field] = text
        title = _as_text(data.get("title"))
        categories = data.get("categories")
        series = data.get("series")
        if series is None and data.get("values") is not None:
            series = [{"name": title or "", "values": data["values"]}]
        if isinstance(series, dict):
            if all(isinstance(v, (list, tuple)) for v in series.values()):
                series = [{"name": k, "values": v} for k, v in series.items()]
            else:
                categories = categories or list(series)
                series = [{"name": title or "", "values": list(series.values())}]
        series = list(series) if isinstance(series, (list, tuple)) else []
        if series and all(isinstance(v, (int, float, str)) for v in series):
            series = [{"name": title or "", "values": series}]
        # A series written as {category: value} pairs names its categories.
        paired = [
            s
            for s in series
            if isinstance(s, dict)
            and not any(k in s for k in ("values", "data", "y", "points", "x"))
            and len(s) > 1
        ]
        if paired and not categories and not xy:
            categories = [k for k in paired[0] if k not in ("name", "label", "title")]
        if xy:
            categories, series = _xy_series(data, categories, series, title)
            paired = []
        series = [
            {
                "name": s.get("name") or s.get("label") or s.get("title") or "",
                "values": [s.get(c) for c in categories or []],
            }
            if s in paired
            else s
            for s in series
        ]
        known = set(cls.model_fields) | set(aliases) | {"values"}
        if xy:
            known |= {"x", "y", "size", "sizes", "points"}
        style = [k for k in value if _style_key(k, value[k], xy)]
        style += [
            f"series.{k}"
            for s in series
            if isinstance(s, dict)
            for k in s
            if _style_key(k, s[k], True)
        ]
        return {
            "type": kind,
            "categories": [(_as_text(c) or "").strip() for c in _seq(categories or [])],
            "series": [s for s in series if s is not None],
            "title": title,
            "unit": _as_text(data.get("unit")),
            "show": show,
            "asked_show": None if show else asked_show or value.get("asked_show"),
            "highlight": highlight,
            "sort": sort,
            "stacked_as": stacked_as,
            **{
                name: _as_text(data.get(name))
                for name in ("x_title", "x_unit", "y_title", "size_title", "size_unit")
            },
            "asked_intents": asked_intents,
            "asked_type": asked,
            "style_fields": sorted(set(value.get("style_fields") or []) | set(style)),
            "ignored_fields": _ignored(
                {k: v for k, v in value.items() if k not in style}, known
            ),
        }

    @model_validator(mode="after")
    def _unit_from_values(self) -> "PlanChart":
        """Every value written with the same unit ("45 %") gives the unit; on a
        scatter or bubble, each axis its own."""
        if not self.unit:
            self.unit = _one_unit(
                [u for s in self.series for u in s.units],
                sum(len(s.values) for s in self.series),
            )
        points = [p for s in self.series for p in s.points]
        for axis, field in (("y", "unit"), ("x", "x_unit"), ("size", "size_unit")):
            if points and not getattr(self, field):
                written = [p.units[axis] for p in points if axis in p.units]
                counted = sum(1 for p in points if getattr(p, axis) is not None)
                setattr(self, field, _one_unit(written, counted))
        return self

    def points(self) -> List[PlanPoint]:
        return [p for s in self.series for p in s.points]

    def has_content(self) -> bool:
        return bool(self.categories) or any(s.values or s.points for s in self.series)


def _one_unit(written: List[str], counted: int) -> Optional[str]:
    units = set(written)
    if counted and len(units) == 1 and len(written) == counted and "" not in units:
        return units.pop()
    return None


def _style_key(key: str, value: Any, xy: bool) -> bool:
    """A design key; on a scatter or bubble, a list of sizes is data."""
    name = lexicon.normalize(key)
    if name == "size" and xy and isinstance(value, (list, tuple)):
        return False
    return name in _STYLE_NAMES


def _values_of(series: Any) -> Optional[List[Any]]:
    if isinstance(series, (list, tuple)):
        return list(series)
    if not isinstance(series, dict) or "points" in series or "x" in series:
        return None
    raw = next((series[k] for k in ("values", "data", "y") if k in series), None)
    return list(raw) if isinstance(raw, (list, tuple)) else None


def _xy_series(
    data: Mapping[str, Any], categories: Any, series: List[Any], title: Optional[str]
) -> Tuple[Any, List[Any]]:
    """A scatter's or bubble's series as points: chart-level parallel lists or
    points, and numeric categories read as x values. Text categories stay, for
    the shape problem to name."""
    labels = categories
    if not data.get("series") and isinstance(data.get("x"), (list, tuple)):
        columns = {
            "x": data["x"],
            "y": data.get("y") if data.get("y") is not None else data.get("values"),
            "size": data.get("size") or data.get("sizes"),
            "labels": labels,
        }
        return [], [
            {"name": title or "", **{k: v for k, v in columns.items() if v is not None}}
        ]
    if not data.get("series") and data.get("points") is not None:
        return categories, [{"name": title or "", "points": data["points"]}]
    # "Q1" reads as a number after a unit: a category starting with a letter is text.
    texts = [(_as_text(c) or "").strip() for c in _seq(categories or [])]
    if not texts or any(read_number(t)[0] is None or t[:1].isalpha() for t in texts):
        return categories, series
    converted = []
    for entry in series:
        values = _values_of(entry)
        if values is None:
            converted.append(entry)
            continue
        name = entry.get("name") if isinstance(entry, dict) else None
        converted.append(
            {
                "name": name or "",
                "points": [{"x": x, "y": y} for x, y in zip(_seq(categories), values)],
            }
        )
    return [], converted


REPEAT_LAYOUT_HINT = (
    "true: this slide keeps the previous slide's layout. Set it only when the user "
    "explicitly asked for identical consecutive slides; never on your own initiative."
)


class SlidePlan(BaseModel):
    # First on purpose: the model decides what the slide makes the audience
    # conclude before writing its content.
    takeaway: Optional[str] = Field(
        default=None,
        description="What the audience concludes when looking at this slide, as a full "
        "sentence ('Italy weighs twice Spain in headcount, so hiring should start "
        "there'). Not the title: the slide's visible content delivers it, so changing it "
        "means rewriting that content; it is shown itself only when the user explicitly "
        "asks. Not needed on cover, agenda, section, closing and quote slides.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Short title, a few words pointing to the takeaway.",
    )
    subtitle: Optional[str] = None
    number: Optional[str] = Field(
        default=None,
        description="A section slide's number ('02'). Omitted → its place among the "
        "deck's sections.",
    )
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
    chart: Optional[PlanChart] = Field(
        default=None,
        description="A data chart {type, categories, series [{name, values}], title, unit, "
        "show}: "
        "numbers only, the template sets colours and fonts.",
    )
    charts: List[PlanChart] = Field(
        default_factory=list,
        description="Several charts on one slide, in reading order; only on a slide the "
        "catalogue lists with `charts×N`, exactly N charts, each with a title.",
    )
    source: Optional[str] = Field(
        default=None,
        description="Where the slide's figures come from, required with a chart, a "
        "numeric table or numbered items: the document's name, 'user' (typed in the "
        "chat), or 'illustrative' only when the user asked for made-up data.",
    )
    notes: Optional[str] = Field(default=None, description="Speaker notes.")
    repeat_layout: bool = Field(
        default=False,
        description=REPEAT_LAYOUT_HINT,
    )
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
    # `columns` arrived as one object, not a list: one column or several meant
    # cannot be told apart, so the assigner refuses it instead of guessing.
    single_columns: SkipJsonSchema[bool] = False
    # The template slide the delivered deck shows it on: kept while it fits.
    built_on: SkipJsonSchema[Optional[str]] = None
    # Set by a `like` change: the template slide asked for, and the slide whose
    # design it is (file numbering); cleared once the deck is delivered.
    asked_design: SkipJsonSchema[Optional[str]] = None
    asked_from: SkipJsonSchema[Optional[int]] = None
    # The delivered file slide's hash (`slide_fingerprints`): what it shows.
    rendered: SkipJsonSchema[Optional[str]] = None
    # The user asked for the key messages on the slides: the takeaway goes in
    # the template's takeaway zone when it fits. Set by the tool only.
    takeaway_shown: SkipJsonSchema[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"invalid_entry": str(value)[:80]}
        renamed = _with_aliases(value, _SLIDE_ALIASES)
        known = set(cls.model_fields) | set(_SLIDE_ALIASES)
        single = bool(value.get("single_columns")) or isinstance(
            renamed.get("columns"), dict
        )
        return {
            **renamed,
            "ignored_fields": _ignored(value, known),
            "single_columns": single,
        }

    @field_validator(
        "takeaway",
        "title",
        "subtitle",
        "number",
        "image",
        "source",
        "notes",
        mode="before",
    )
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

    @field_validator("repeat_layout", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return as_flag(value)

    @field_validator("bullets", "images", mode="before")
    @classmethod
    def _texts(cls, value: Any) -> List[str]:
        return _as_text_list(value)

    @field_validator("columns", "items", "charts", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [v for v in value if v is not None]
        return [value]


# Set by delivery and `like` only: never read from the model's call.
HIDDEN_FIELDS = (
    "built_on",
    "asked_design",
    "asked_from",
    "rendered",
    "takeaway_shown",
)


def without_hidden(slide: SlidePlan) -> SlidePlan:
    """The slide with every tool-set field back to its default."""
    return slide.model_copy(
        update={
            name: SlidePlan.model_fields[name].get_default(call_default_factory=True)
            for name in HIDDEN_FIELDS
        }
    )


# Fields of the whole deck, never of one slide.
DECK_FIELDS = ("file_name", "audience", "main_message")


class DeckPlan(BaseModel):
    slides: List[SlidePlan]
    file_name: Optional[str] = Field(
        default=None, description="Short file name for the deck; '.pptx' is added."
    )
    audience: Optional[str] = None
    main_message: Optional[str] = None
    # Asked by the model; honoured only when the user asked for key messages.
    show_takeaways: bool = False
    # The deck as a file holds it, not a plan still under revision.
    delivered: SkipJsonSchema[bool] = False
    # Shown to the user as an outline, waiting for their answer.
    proposed: SkipJsonSchema[bool] = False


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
        or bool(slide_charts(slide))
    )


def named_charts(slide: SlidePlan) -> List[Tuple[str, PlanChart]]:
    """The slide's charts as sent, each with the path a problem names it by."""
    if slide.charts:
        return [(f"charts[{i}]", chart) for i, chart in enumerate(slide.charts)]
    return [("chart", slide.chart)] if slide.chart is not None else []


def shown_charts(slide: SlidePlan) -> List[Tuple[str, PlanChart]]:
    """The charts the slide shows, named: `charts`, else its one `chart`."""
    return [(at, chart) for at, chart in named_charts(slide) if chart.has_content()]


def slide_charts(slide: SlidePlan) -> List[PlanChart]:
    return [chart for _, chart in shown_charts(slide)]


# --- what a pattern holds, in plan fields ------------------------------------------------


# Smallest font scale the overflow control applies before truncating.
MIN_FONT_SCALE = 0.7
# Fields whose entries each start their own paragraph in one zone.
LIST_FIELDS = ("bullets", "columns.bullets")

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


def max_entries(lines: int) -> int:
    """Entries a zone of ``lines`` lines holds: each takes a line or more,
    even at the smallest font (render `_fit`)."""
    return int(lines / MIN_FONT_SCALE)


def entries_text(count: int) -> str:
    return f"{count} entr{'y' if count == 1 else 'ies'}"


def list_capacity_text(chars_per_line: int, lines: int) -> str:
    """A list field's room: its lines always shown, and the entries they hold."""
    rows = f"{lines} line{'s' if lines > 1 else ''}"
    return (
        f"{word_budget(chars_per_line, lines)} (≈{chars_per_line} chars × {rows}, "
        f"max {entries_text(max_entries(lines))})"
    )


def _room(zones: Sequence[Zone]) -> Optional[Tuple[int, int]]:
    """The room the agent can count on across zones filled from one field: the
    tightest one, since that is the zone that truncates. A zone that grows with
    its text has no limit to quote."""
    bounded = [z for z in zones if not z.grows and z.chars_per_line and z.max_lines]
    if not bounded:
        return None
    tightest = min(bounded, key=lambda z: (z.chars_per_line or 0) * (z.max_lines or 0))
    return tightest.chars_per_line or 1, tightest.max_lines or 1


def _limit(zones: Sequence[Zone], listed: bool = False) -> str:
    room = _room(zones)
    if not room:
        return ""
    return " " + (list_capacity_text if listed else capacity_text)(*room)


def _required(zones: Sequence[Zone]) -> str:
    """A picture zone left empty shows its frame or a hole: it needs a picture."""
    return " (required)" if zones else ""


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


def chart_summary(zones: Sequence[Zone]) -> str:
    """What a slide's chart zones hold: their count and types, and as column
    charts the smallest one's room."""
    zone = min(zones, key=lambda z: (z.max_lines or 0, z.chars_per_line or 0))
    room = (
        f": categories max {zone.max_lines}, labels "
        f"{capacity_text(zone.chars_per_line, 2)}, series max {MAX_SERIES}"
        if zone.max_lines and zone.chars_per_line
        else ""
    )
    field = f"charts×{len(zones)}" if len(zones) > 1 else "chart"
    return f"{field} ({', '.join(CHART_TYPES)}){room}"


# A free text box this close above a chart frame of a multi-chart slide is that
# chart's heading (per mille of the slide, as the analysis pairs text).
_HEADING_GAP = 120
_HEADING_OVERLAP = -40
_HEADING_ROLES = ("heading", "label", "body", "caption", "subtitle")


def chart_headings(pattern: Pattern) -> Dict[str, Zone]:
    """Per chart zone key, the free text box right above it that shows its
    title; only on a slide with several charts (one chart keeps its title)."""
    frames = [z for z in pattern.zones if z.role == "chart"]
    if len(frames) < 2:
        return {}
    texts = [
        z for z in pattern.zones if z.role in _HEADING_ROLES and z.key.startswith("sp:")
    ]
    found: Dict[str, Zone] = {}
    for frame in frames:
        above = []
        for text in texts:
            gap = frame.box.y - (text.box.y + text.box.h)
            overlap = min(text.box.x + text.box.w, frame.box.x + frame.box.w) - max(
                text.box.x, frame.box.x
            )
            if (
                _HEADING_OVERLAP <= gap <= _HEADING_GAP
                and overlap * 2 >= min(text.box.w, frame.box.w)
                and text not in found.values()
            ):
                above.append((gap, text))
        if above:
            found[frame.key] = min(above, key=lambda pair: pair[0])[1]
    return found


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
        f"{field}{f'×{len(same)}' if len(same) > 1 else ''}"
        f"{_limit(same, field in LIST_FIELDS)}"
        for field, same in _slide_fields(pattern)
    ]
    images = [z for z in pattern.zones if z.role == "image"]
    if images:
        parts.append(f"images×{len(images)}{_required(images)}")
    parts.extend(table_summary(z) for z in pattern.zones if z.role == "table")
    frames = [z for z in pattern.zones if z.role == "chart"]
    if frames:
        parts.append(chart_summary(frames))
    parts.extend(group_summary(g) for g in pattern.groups)
    # Shows the takeaway only when the user asks for key messages on the slides.
    for zone in (z for z in pattern.zones if z.takeaway):
        room = _room([zone])
        parts.append("takeaway zone" + (f" {word_budget(*room)}" if room else ""))
    return "; ".join(parts) or "no editable zone"


def takeaway_aside(pattern: Pattern) -> List[Zone]:
    """Takeaway zones beside another text body: they show the takeaway alone,
    never a column of the slide's content. A slide's only body holds its bullets."""
    takeaways = [z for z in pattern.zones if z.takeaway]
    others = any(
        z.role in ("body", "caption") and not z.takeaway for z in pattern.zones
    )
    return takeaways if others else []


def _slide_fields(pattern: Pattern) -> List[Tuple[str, List[Zone]]]:
    """The slide fields one pattern's own zones are filled from, as the renderer
    fills them, each with its zones."""
    found: List[Tuple[str, List[Zone]]] = []
    seen: set[str] = set()
    titled = {z.key for z in chart_headings(pattern).values()}
    aside = takeaway_aside(pattern)
    # Captions hold the bullets only on a slide without a body (`body_like`).
    bodies = sum(z.role == "body" and z not in aside for z in pattern.zones)
    field_of = {
        z.key: None
        if z.key in titled or z in aside or (bodies and z.role == "caption")
        else SLIDE_FIELDS.get(z.role)
        for z in pattern.zones
    }
    headings = [z for z in pattern.zones if z.role == "heading" and z.key not in titled]
    columned = bodies > 1 and pattern.kind not in (
        "cover",
        "section",
        "quote",
        "closing",
    )
    if headings and "title" not in field_of.values() and not columned:
        # The renderer writes the title into the leftmost heading, `columns` aside
        # (`_place_text`).
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
        quote = list_capacity_text if field in LIST_FIELDS else capacity_text
        others = "".join(
            f"; {kind} {quote(*by_kind[kind])}"
            for kind in SLIDE_KINDS
            if kind in by_kind and by_kind[kind] != common
        )
        hints.append((field, f"Room: {lead}{quote(*common)}{others}."))
    return tuple(hints)
