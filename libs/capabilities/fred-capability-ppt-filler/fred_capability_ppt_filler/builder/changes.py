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
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from fred_capability_ppt_filler.builder.plan import (
    HIDDEN_FIELDS,
    REPEAT_ALIASES,
    DeckPlan,
    SlidePlan,
)

_OPS: Tuple[str, ...] = ("replace", "insert", "remove", "edit")
_OP_ALIASES = {
    "delete": "remove",
    "add": "insert",
    "update": "edit",
    "set": "edit",
    "modify": "edit",
}
_SLIDES_ALIASES = ("with", "new_slides", "new_slide", "content")
# The edit field that gives a slide the template slide of another one.
LIKE = "like"
# The edit field that keeps the previous slide's layout, as the user asked.
REPEAT = "repeat_layout"
# Slide fields (and their aliases) a model may write in the change itself.
_SLIDE_KEYS = frozenset(
    ("title", "subtitle", "bullets", "columns", "items", "image", "images", "table")
    + ("chart", "charts", "takeaway", "source")
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
        description=(
            "edit: the field to set, e.g. 'title', 'bullets[1]', 'items[2].label' (indexes "
            "from 0), or 'like' (a design)."
        ),
    )
    value: Any = Field(
        default=None,
        description=(
            "edit: the new value (text, list or object); null removes a list element; "
            "'like': a slide number."
        ),
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
        known |= {"value", "like", *_SLIDES_ALIASES}
        if "has_value" in data:  # a validated change dumped and read again
            return {k: v for k, v in data.items() if k in cls.model_fields}
        # `{"op": "edit", "slide": 7, "like": 5}` means the `like` field.
        if "like" in data and not data.get("field") and "value" not in data:
            data["field"], data["value"] = LIKE, data["like"]
        # `{"op": "edit", "slide": 7, "repeat_layout": true}` means that field.
        for key in (REPEAT, *REPEAT_ALIASES):
            if (
                op == "edit"
                and key in data
                and not data.get("field")
                and "value" not in data
            ):
                data["field"], data["value"] = REPEAT, data[key]
                known.add(key)
        if data.get("field") in REPEAT_ALIASES:
            data["field"] = REPEAT
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
        "takeaway": "text",
        "source": "text",
        "title": "text",
        "subtitle": "text",
        "bullets": ("list", "text"),
        "columns": ("list", "column"),
        "items": ("list", "item"),
        "image": "text",
        "images": ("list", "text"),
        "table": "table",
        "chart": "chart",
        "charts": ("list", "chart"),
        "notes": "text",
        "kind": "text",
        REPEAT: "flag",
    },
    "column": {"heading": "text", "bullets": ("list", "text")},
    "item": {
        k: "text" for k in ("number", "heading", "text", "label", "image", "trend")
    },
    "table": {
        "header": ("list", "text"),
        "rows": ("list", ("list", "text")),
        "total_row": "flag",
        "highlight_row": "text",
        "highlight_column": "text",
    },
    "chart": {
        "type": "text",
        "title": "text",
        "unit": "text",
        "show": "text",
        "highlight": "text",
        "sort": "text",
        "stacked_as": "text",
        "x_title": "text",
        "x_unit": "text",
        "y_title": "text",
        "size_title": "text",
        "size_unit": "text",
        "categories": ("list", "text"),
        "series": ("list", "series"),
    },
    "series": {
        "name": "text",
        "values": ("list", "number"),
        "points": ("list", "point"),
    },
    "point": {"x": "number", "y": "number", "size": "number", "label": "text"},
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
    held = len(slide.get("charts") or [])
    if tokens[0][0] == "chart" and held:
        return (
            f"this slide has {held} chart(s) in `charts`: edit 'charts[i]"
            f"{path.removeprefix('chart')}' (i from 0 to {held - 1})"
        )
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


def _like_problem(base: DeckPlan, number: int, value: Any) -> Optional[str]:
    """Why slide ``number`` cannot take the design of the slide ``value`` names."""
    n = len(base.slides)
    ref = _number(value)
    if ref is None:
        return (
            f"`like` takes as `value` the number of the slide whose design to use "
            f"(e.g. 5), not '{str(value)[:20]}'"
        )
    if not 1 <= ref <= n:
        return (
            f"`like` {ref}: slide {ref} does not exist; the previous deck has {n} slides. "
            f"Use a number from 1 to {n}"
        )
    if ref == number:
        return (
            f"`like` {ref} is slide {number} itself, which already has its design: give "
            "the number of the slide whose design it should take"
        )
    if base.slides[ref - 1].built_on is None:
        return (
            f"slide {ref} has no design yet (it is not in the last delivered deck): build "
            "the deck first, then ask for that slide's design"
        )
    return None


def _asked(base: DeckPlan, ref: int) -> Dict[str, Any]:
    """The design of slide ``ref`` as the delivered file shows it, whatever the
    same call changes on that slide."""
    return {"asked_design": base.slides[ref - 1].built_on, "asked_from": ref}


def _shown(slide: SlidePlan, kinds: Mapping[str, str]) -> Tuple[Dict[str, Any], Any]:
    """What a slide shows: its content and template slide, a kind left out
    being its template slide's."""
    design = slide.asked_design or slide.built_on
    content = slide.model_dump(exclude=set(HIDDEN_FIELDS))
    content["kind"] = slide.kind or kinds.get(design or "")
    return content, design


def unchanged(base: DeckPlan, changed: DeckPlan, kinds: Mapping[str, str]) -> bool:
    """Whether ``changed`` shows exactly what ``base`` does, slide for slide;
    ``kinds`` maps a template slide to its kind."""
    return len(base.slides) == len(changed.slides) and all(
        _shown(a, kinds) == _shown(b, kinds)
        for a, b in zip(base.slides, changed.slides)
    )


# Content a slide can lose when its kind changes; notes always stay.
CLEARABLE = (
    "takeaway",
    "title",
    "subtitle",
    "bullets",
    "columns",
    "items",
    "image",
    "images",
    "table",
    "chart",
    "charts",
)


def _clear_for_kind(
    before: SlidePlan,
    dumped: Dict[str, Any],
    entries: List[Tuple[int, SlideChange]],
    unplaced: Callable[[SlidePlan], List[str]],
) -> List[str]:
    """A kind edit moves the slide to another shape: the old content the new kind
    has no place for goes, unless this call sets it. Returns what went."""
    slide = SlidePlan.model_validate(dumped)
    if slide.kind is None or slide.kind == before.kind:
        return []
    sent = {(c.field or "").split("[")[0].split(".")[0] for _, c in entries}
    gone = [f for f in unplaced(slide) if f in CLEARABLE and f not in sent]
    for name in gone:
        dumped[name] = None
    return gone


def apply_changes(
    base: DeckPlan,
    changes: List[SlideChange],
    unplaced: Optional[Callable[[SlidePlan], List[str]]] = None,
    cleared: Optional[Dict[int, List[str]]] = None,
) -> DeckPlan:
    """The whole plan after ``changes``, all numbered on ``base``. Untouched
    slides stay the base's objects; raises :class:`ChangeError` listing every
    bad change, so nothing is built from half of them. With ``unplaced``, a kind
    edit clears the fields it names; ``cleared`` gets them per resulting slide."""
    n = len(base.slides)
    problems: List[str] = []
    replaced: Dict[int, List[SlidePlan]] = {}
    removed: set[int] = set()
    # The change that took each slide first: a second one on it is a conflict.
    owner: Dict[int, int] = {}
    inserts: Dict[int, List[SlidePlan]] = {}
    edits: Dict[int, List[Tuple[int, SlideChange]]] = {}
    likes: List[Tuple[int, SlideChange, int]] = []

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
        if change.op == "edit" and change.field == LIKE:
            why = _like_problem(base, number, change.value)
            if why:
                report(k, change, why)
            else:
                likes.append((k, change, _number(change.value) or 0))
            continue
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

    # Resolved once every replace and remove is known, whatever their order.
    liked: Dict[int, int] = {}
    for k, change, ref in likes:
        number = change.slide or 0
        if number in removed:
            report(k, change, f"slide {number} is removed by changes[{owner[number]}]")
        elif number in liked:
            report(
                k,
                change,
                f"slide {number} already takes slide {liked[number]}'s design",
            )
        elif number not in replaced and base.slides[number - 1].invalid_entry:
            report(
                k, change, f"slide {number} was not a slide object: replace it instead"
            )
        else:
            liked[number] = ref

    edited: Dict[int, SlidePlan] = {}
    gone: Dict[int, List[str]] = {}
    for number in sorted(set(edits) | (set(liked) - set(replaced))):
        entries = edits.get(number, [])
        dumped = base.slides[number - 1].model_dump()
        failed = False
        for k, change in entries:
            why = _edit(dumped, change.field or "", change.value)
            if why:
                report(k, change, f"slide {number}: {why}")
                failed = True
        if number in liked:
            dumped.update(_asked(base, liked[number]))
            # The design decides the kind, unless this call sets one.
            if not any(c.field == "kind" for _, c in entries):
                dumped["kind"] = None
        if not failed and unplaced is not None and number not in liked:
            before = base.slides[number - 1]
            gone[number] = _clear_for_kind(before, dumped, entries, unplaced)
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
            if number in liked:
                first = first.model_copy(update=_asked(base, liked[number]))
            slides.extend([first, *new[1:]])
        elif number not in removed:
            slides.append(edited.get(number, slide))
            if gone.get(number) and cleared is not None:
                cleared[len(slides)] = gone[number]
        slides.extend(inserts.get(number, []))
    return DeckPlan(
        slides=slides,
        file_name=base.file_name,
        audience=base.audience,
        main_message=base.main_message,
        show_takeaways=base.show_takeaways,
    )
