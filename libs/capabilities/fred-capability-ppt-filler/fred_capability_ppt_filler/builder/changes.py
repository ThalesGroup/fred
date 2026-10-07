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

"""Changes against the previous deck plan: replace, insert, remove or edit
slides by their number in that plan. The result is a whole plan; the tool
assigns and renders it as any full call, so quality never depends on the mode."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder.plan import DeckPlan, SlidePlan

_OPS: Tuple[str, ...] = ("replace", "insert", "remove", "edit")
_OP_ALIASES = {
    "delete": "remove",
    "add": "insert",
    "update": "edit",
    "set": "edit",
    "modify": "edit",
}
_SLIDES_ALIASES = ("with", "new_slides", "new_slide", "content")
# Slide fields (and their aliases) a model may write in the change itself.
_SLIDE_KEYS = frozenset(
    ("title", "subtitle", "bullets", "columns", "items", "image", "images", "table")
    + ("notes", "kind", "body", "text", "pattern", "type")
)


class ChangeError(ValueError):
    """Every bad change of one call, each with its remedy."""

    def __init__(self, problems: List[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def _unknown(key: str, op: Any) -> str:
    if key in _SLIDE_KEYS and op == "edit":
        return f"'{key}' is a slide field: write it as `field` '{key}' with its `value`"
    if key in _SLIDE_KEYS:
        return f"'{key}' is a slide field, which {op or 'this change'} does not take: drop it"
    return (
        f"unknown key '{key}': a change takes op, slide, after, slides, field and value; "
        "drop it"
    )


def _number(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


class SlideChange(BaseModel):
    """One change to the previous deck, its slides numbered as in that deck."""

    op: Optional[str] = Field(
        default=None,
        description="replace | insert | remove | edit.",
        json_schema_extra={"enum": list(_OPS)},
    )
    slide: Optional[int] = Field(
        default=None,
        description="replace, remove, edit: the slide's number in the previous deck.",
    )
    after: Optional[int] = Field(
        default=None,
        description="insert: the new slides go after this slide of the previous deck; 0 = at the start.",
    )
    slides: List[SlidePlan] = Field(
        default_factory=list,
        description="replace, insert: the new slides, written as in `slides`.",
    )
    field: Optional[str] = Field(
        default=None,
        description="edit: the field to set, e.g. 'title', 'bullets[1]', 'items[2].label' (indexes from 0).",
    )
    value: Any = Field(
        default=None,
        description="edit: the new value (text, list or object); null removes a list element.",
    )

    has_value: SkipJsonSchema[bool] = False
    unknown: SkipJsonSchema[List[str]] = Field(default_factory=list)
    raw_numbers: SkipJsonSchema[Dict[str, str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"unknown": [f"'{str(value)[:40]}' is not a change object"]}
        data = dict(value)
        op = data.get("op") or data.get("operation") or data.get("action")
        if isinstance(op, str):
            op = op.strip().lower()
            op = _OP_ALIASES.get(op, op)
        slides = data.get("slides")
        for alias in _SLIDES_ALIASES:
            if slides in (None, [], {}) and data.get(alias) not in (None, [], {}):
                slides = data[alias]
        # A slide object written under `slide` is the content, not a number.
        slide = data.get("slide")
        if isinstance(slide, dict) and slides in (None, [], {}):
            slides, slide = slide, None
        if isinstance(slides, dict):
            slides = [slides]
        known = {"op", "operation", "action", "slide", "after", "slides", "field"}
        known |= {"value", *_SLIDES_ALIASES}
        if "has_value" in data:  # a validated change dumped and read again
            return {k: v for k, v in data.items() if k in cls.model_fields}
        # A new slide written in the change itself, not under `slides`.
        flat = {k: v for k, v in data.items() if k in _SLIDE_KEYS}
        unknown = [_unknown(k, op) for k in data if k not in known | set(flat)]
        if flat and op in ("replace", "insert"):
            if slides in (None, [], {}):
                slides = [flat]
            else:
                unknown.append(
                    f"{', '.join(flat)} sent beside `slides`: it is unclear which new slide "
                    "they belong to; put them inside that slide's entry of `slides`"
                )
        elif flat:
            unknown += [_unknown(k, op) for k in flat]
        raw = {
            k: str(n)[:20]
            for k, n in (("slide", slide), ("after", data.get("after")))
            if n is not None and _number(n) is None
        }
        return {
            "op": op if isinstance(op, str) else None,
            "slide": _number(slide),
            "after": _number(data.get("after")),
            "slides": slides if isinstance(slides, list) else [],
            "field": data.get("field") if isinstance(data.get("field"), str) else None,
            "value": data.get("value"),
            "has_value": "value" in data,
            "unknown": unknown,
            "raw_numbers": raw,
        }

    @field_validator("slides", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        return [v for v in value if v is not None] if isinstance(value, list) else []


# --- edit paths -------------------------------------------------------------------------

_Type = Union[str, Tuple[str, Any]]
_FIELDS: Dict[str, Dict[str, _Type]] = {
    "slide": {
        "title": "text",
        "subtitle": "text",
        "bullets": ("list", "text"),
        "columns": ("list", "column"),
        "items": ("list", "item"),
        "image": "text",
        "images": ("list", "text"),
        "table": "table",
        "notes": "text",
        "kind": "text",
    },
    "column": {"heading": "text", "bullets": ("list", "text")},
    "item": {k: "text" for k in ("number", "heading", "text", "label", "image")},
    "table": {"header": ("list", "text"), "rows": ("list", ("list", "text"))},
}
_PATH = re.compile(r"^[a-z_]+(\[\d+\])*(\.[a-z_]+(\[\d+\])*)*$")
_TOKEN = re.compile(r"([a-z_]+)|\[(\d+)\]")


def _empty_of(kind: _Type) -> Any:
    if isinstance(kind, tuple):
        return []
    return {} if kind in _FIELDS else None


def _edit(slide: Dict[str, Any], path: str, value: Any) -> Optional[str]:
    """Set ``path`` of a dumped slide in place; the reason it cannot, else None."""
    if not _PATH.match(path):
        return f"'{path}' is not a field path (write e.g. 'title', 'bullets[1]', 'items[2].label')"
    tokens = [(m.group(1), m.group(2)) for m in _TOKEN.finditer(path)]
    node: Any = slide
    kind: _Type = "slide"
    shown = ""
    for position, (key, index) in enumerate(tokens):
        last = position == len(tokens) - 1
        if key is not None:
            fields = _FIELDS.get(kind) if isinstance(kind, str) else None
            if fields is None or key not in fields:
                where = f"'{shown}'" if shown else "a slide"
                allowed = ", ".join(fields) if fields else "an index [n]"
                return f"'{key}' is not a field of {where} (it takes {allowed})"
            shown += ("." if shown else "") + key
            if last:
                node[key] = value
                return None
            kind = fields[key]
            if node.get(key) is None:
                node[key] = _empty_of(kind)
            node = node[key]
            continue
        n = int(index)
        if not isinstance(kind, tuple):
            return f"'{shown}' is not a list: write '{shown}' without [{n}]"
        size = len(node)
        span = f"{shown}[0] to {shown}[{size - 1}]" if size else "none yet"
        if last:
            if n < size:
                if value is None:
                    del node[n]
                else:
                    node[n] = value
                return None
            if n == size and value is not None:
                node.append(value)
                return None
            return (
                f"'{shown}' has {size} entries ({span}); give an index up to {size} "
                "(that one adds an entry)"
            )
        if n >= size:
            return f"'{shown}' has {size} entries ({span})"
        kind = kind[1]
        if node[n] is None:
            node[n] = _empty_of(kind)
        node = node[n]
        shown += f"[{n}]"
    return None  # pragma: no cover - the loop returns on the last token


# --- applying ---------------------------------------------------------------------------


def change_shape(changes: List[SlideChange]) -> Tuple[Tuple[str, int, int, str], ...]:
    """What a list of changes does, without its content: a corrected resend of
    the same changes has the same shape."""
    return tuple(
        sorted(
            (
                c.op or "",
                -1 if c.slide is None else c.slide,
                -1 if c.after is None else c.after,
                c.field or "",
            )
            for c in changes
        )
    )


def _check(change: SlideChange, n: int) -> List[str]:
    """What is wrong with one change on its own, each with its remedy."""
    issues = list(change.unknown)
    for key, raw in change.raw_numbers.items():
        issues.append(f"`{key}` '{raw}' is not a number: give the slide's number")
    if change.op not in _OPS:
        given = f"'{change.op}'" if change.op else "no `op`"
        return issues + [
            f"{given} is not an operation: use replace, insert, remove or edit"
        ]
    if change.op == "insert":
        if change.after is None and "after" not in change.raw_numbers:
            issues.append(
                "insert needs `after`: the slide number the new slides follow (0 = at the start)"
            )
        elif change.after is not None and not 0 <= change.after <= n:
            issues.append(
                f"`after` {change.after} does not exist; the previous deck has {n} slides. "
                f"Use a number from 0 to {n}"
            )
    elif change.slide is None:
        if "slide" not in change.raw_numbers:
            issues.append(
                f"{change.op} needs `slide`: the slide's number in the previous deck"
            )
    elif not 1 <= change.slide <= n:
        issues.append(
            f"slide {change.slide} does not exist; the previous deck has {n} slides. "
            f"Use a number from 1 to {n}"
        )
    if change.op in ("replace", "insert") and not change.slides:
        issues.append(f"{change.op} needs `slides`: the new slide objects")
    if change.op == "edit":
        if not change.field:
            issues.append("edit needs `field`, e.g. 'title' or 'items[2].label'")
        if not change.has_value:
            issues.append(
                "edit needs `value`: the new text, list or object (null removes)"
            )
    return issues


def apply_changes(base: DeckPlan, changes: List[SlideChange]) -> DeckPlan:
    """The whole plan after ``changes``, all numbered on ``base``. Untouched
    slides stay the base's objects; raises :class:`ChangeError` listing every
    bad change, so nothing is built from half of them."""
    n = len(base.slides)
    problems: List[str] = []
    replaced: Dict[int, List[SlidePlan]] = {}
    removed: set[int] = set()
    # The change that took each slide first: a second one on it is a conflict.
    owner: Dict[int, int] = {}
    inserts: Dict[int, List[SlidePlan]] = {}
    edits: Dict[int, List[Tuple[int, SlideChange]]] = {}

    def report(k: int, change: SlideChange, why: str) -> None:
        problems.append(f"changes[{k}] ({change.op or '?'}): {why}.")

    for k, change in enumerate(changes):
        issues = _check(change, n)
        if issues:
            for issue in issues:
                report(k, change, issue)
            continue
        if change.op == "insert":
            inserts.setdefault(change.after or 0, []).extend(change.slides)
            continue
        number = change.slide or 0
        whole = number in replaced or number in removed
        if change.op in ("replace", "remove"):
            if number in owner:
                report(
                    k,
                    change,
                    f"slide {number} is already changed by changes[{owner[number]}]: send one "
                    "replace or remove per slide, and put edits in the replacement",
                )
                continue
            owner[number] = k
            if change.op == "replace":
                replaced[number] = change.slides
            else:
                removed.add(number)
            continue
        if whole:
            report(
                k,
                change,
                f"slide {number} is replaced or removed by changes[{owner[number]}]: put the "
                "edit in the replacement slide instead",
            )
            continue
        owner.setdefault(number, k)
        if base.slides[number - 1].invalid_entry is not None:
            report(
                k, change, f"slide {number} was not a slide object: replace it instead"
            )
            continue
        edits.setdefault(number, []).append((k, change))

    edited: Dict[int, SlidePlan] = {}
    for number, entries in edits.items():
        dumped = base.slides[number - 1].model_dump()
        failed = False
        for k, change in entries:
            why = _edit(dumped, change.field or "", change.value)
            if why:
                report(k, change, f"slide {number}: {why}")
                failed = True
        if not failed:
            edited[number] = SlidePlan.model_validate(dumped)
    if problems:
        raise ChangeError(problems)

    slides: List[SlidePlan] = list(inserts.get(0, []))
    for number, slide in enumerate(base.slides, start=1):
        if number in replaced:
            # The replacement keeps the replaced slide's design when it fits.
            new = replaced[number]
            first = new[0].model_copy(update={"built_on": slide.built_on})
            slides.extend([first, *new[1:]] if new[0].built_on is None else new)
        elif number not in removed:
            slides.append(edited.get(number, slide))
        slides.extend(inserts.get(number, []))
    return DeckPlan(slides=slides, file_name=base.file_name)
