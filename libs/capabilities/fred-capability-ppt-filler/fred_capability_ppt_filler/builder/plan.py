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


# --- charts ---------------------------------------------------------------------------

CHART_TYPES = ("column", "bar", "line", "pie", "doughnut", "stacked_column", "area")
# Readability caps of every chart, whatever its zone.
MAX_SERIES = 4
MAX_SLICES = 6
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
    "stacked bar": "stacked_column",
    "stacked columns": "stacked_column",
    "column stacked": "stacked_column",
    "areas": "area",
}
# Design keys a model adds to a chart: the template decides them, never the call.
_CHART_STYLE_KEYS = frozenset(
    ("color", "colors", "colour", "colours", "palette", "style", "theme", "legend")
    + ("position", "size", "width", "height", "font", "fonts", "x_axis", "y_axis")
)
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
        if mixed or (decimals != 3 and digits.count(digits[last]) == 1):
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
    match = _NUMBER.match(str(value).replace(" ", " ").replace(" ", " "))
    if match is None:
        return None, ""
    number = _decimal(match.group(2))
    unit = (match.group(3).strip() + match.group(1).strip()).strip()
    if number is None or len(unit) > 6 or re.search(r"\d", unit):
        return None, ""
    return number, unit


class PlanSeries(BaseModel):
    """One series of a chart: a name and one value per category."""

    name: str = Field(default="", description="Series name, shown in the legend.")
    values: List[Optional[float]] = Field(
        default_factory=list,
        description="One number per category, in the categories' order.",
        json_schema_extra=lambda schema: schema.update({"items": {"type": "number"}}),
    )
    # Values that did not read as numbers, by index, with the text sent.
    unread: SkipJsonSchema[Dict[int, str]] = Field(default_factory=dict)
    units: SkipJsonSchema[List[str]] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            value = {"values": value}
        name = next(
            (value.get(k) for k in ("name", "label", "title") if value.get(k)), ""
        )
        raw = next(
            (value[k] for k in ("values", "data", "y") if value.get(k) is not None),
            [],
        )
        raw = list(raw) if isinstance(raw, (list, tuple)) else [raw]
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
        }


class PlanChart(BaseModel):
    """A data chart: the model gives the numbers, the template its look."""

    type: str = Field(
        default="column",
        description="column | bar (horizontal) | line | pie | doughnut | stacked_column | "
        "area (one or two series).",
        json_schema_extra={"enum": list(CHART_TYPES)},
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Category labels: the x axis, or a pie's slices.",
    )
    series: List[PlanSeries] = Field(
        default_factory=list,
        description="Series, each {name, values}: one number per category.",
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
        "(percentages, the default), value (the numbers, with `unit`) or both. To "
        "display numbers instead of percentages on a pie, set show: 'value'.",
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
        description="stacked_column only: value (the default) or percent (every "
        "column fills 100 %, to compare shares).",
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
        }
        data = _with_aliases(value, aliases)
        kind, asked = _chart_type(data.get("type"))
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
            and not any(k in s for k in ("values", "data", "y"))
            and len(s) > 1
        ]
        if paired and not categories:
            categories = [k for k in paired[0] if k not in ("name", "label", "title")]
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
        style = [k for k in value if lexicon.normalize(k) in _CHART_STYLE_KEYS]
        style += [
            f"series.{k}"
            for s in series
            if isinstance(s, dict)
            for k in s
            if lexicon.normalize(k) in _CHART_STYLE_KEYS
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
            "asked_intents": asked_intents,
            "asked_type": asked,
            "style_fields": sorted(set(value.get("style_fields") or []) | set(style)),
            "ignored_fields": _ignored(
                {k: v for k, v in value.items() if k not in style}, known
            ),
        }

    @model_validator(mode="after")
    def _unit_from_values(self) -> "PlanChart":
        """Every value written with the same unit ("45 %") gives the unit."""
        units = {u for s in self.series for u in s.units}
        written = sum(len(s.units) for s in self.series)
        counted = sum(len(s.values) for s in self.series)
        if not self.unit and len(units) == 1 and written == counted and "" not in units:
            self.unit = units.pop()
        return self

    def has_content(self) -> bool:
        return bool(self.categories) or any(s.values for s in self.series)


REPEAT_LAYOUT_HINT = (
    "true: this slide keeps the previous slide's layout. Set it only when the user "
    "explicitly asked for identical consecutive slides; never on your own initiative."
)


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
    chart: Optional[PlanChart] = Field(
        default=None,
        description="A data chart {type, categories, series [{name, values}], title, unit, "
        "show}: "
        "numbers only, the template sets colours and fonts.",
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

    @field_validator("repeat_layout", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return as_flag(value)

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


# Set by delivery and `like` only: never read from the model's call.
HIDDEN_FIELDS = ("built_on", "asked_design", "asked_from")


class DeckPlan(BaseModel):
    slides: List[SlidePlan]
    file_name: Optional[str] = Field(
        default=None, description="Short file name for the deck; '.pptx' is added."
    )
    # The deck as a file holds it, not a plan still under revision.
    delivered: SkipJsonSchema[bool] = False


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
        or (slide.chart is not None and slide.chart.has_content())
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


def chart_summary(zone: Zone) -> str:
    """What a chart zone holds: its types and, as a column chart, its room."""
    room = (
        f": categories max {zone.max_lines}, labels "
        f"{capacity_text(zone.chars_per_line, 2)}, series max {MAX_SERIES}"
        if zone.max_lines and zone.chars_per_line
        else ""
    )
    return f"chart ({', '.join(CHART_TYPES)}){room}"


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
    parts.extend(chart_summary(z) for z in pattern.zones if z.role == "chart")
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
