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

"""Which template slide shows each entry of a plan, decided for the whole deck.

A slide's candidates are the patterns that hold all of its content: of the
requested kind, then of the kinds close to it (never an unrelated one); with
no kind, of the kinds its content suggests, then of any kind. Each
substitution is reported with the edit that would give the requested kind.
A list longer than its kind's slides hold first continues on a second slide
of the same kind. A beam search picks one per slide under the deck rules,
pricing every reuse of a template slide anywhere in the deck. A slide that
fits nothing is a problem the model must fix, named down to the element:
never a silent fallback.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Sequence, Tuple

from fred_capability_ppt_filler.builder import charts, lexicon
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    Pattern,
    SlideKind,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import (
    ITEM_FIELDS,
    SLIDE_FIELDS,
    DeckPlan,
    PlanChart,
    PlanItem,
    PlanTable,
    SlidePlan,
    _limit,
    capacity_text,
    group_summary,
    has_content,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import (
    _assign_group,
    _assign_text,
    _fit,
    _Line,
    _only_names_the_slide,
    _reading_order,
    _unused_item_fields,
    chart_host,
    fit_table,
    zone_capacity,
)

# Costs of a fitting pattern; lower wins. A kind further down the list costs
# more than any plainness of fit, so content shape decides first.
_KIND_STEP = 10.0
_LAYOUT = 5.0  # an example slide the designer built outranks a bare layout
_IMAGE_HOLE = 4.0  # an empty picture zone is removed, leaving a gap
_EMPTY_ZONE = 1.5  # an unfilled text zone is swept away
_UNUSED_ITEM = 0.5
_SHRUNK = 1.0
_HEADING_LEAD = 1.0  # a heading in bold atop the text: a heading zone reads better
# Per earlier use anywhere in the deck: above the fit costs, so an unused slide
# of the same kind wins, but below _KIND_STEP until the second reuse.
_REUSE = 8.0
_REPEAT = 3.0  # the same slide twice in a row
_TRIPLE = 1000.0  # three in a row: taken only when nothing else fits
# Per content use of a template slide beyond the author's max:
# another variant of the tier wins while one fits.
_OVER_MAX = 100.0
_BEAM = 32
_NOTE_USES = 3  # the passive note when the variety check is off
# Slides a deck legitimately repeats: never a reason to ask for variety.
_STRUCTURAL = ("cover", "section", "agenda", "closing")
# What a variety ask counts: one template slide, one kind, or nothing.
VarietyCheck = Literal["template_slide", "kind", "off"]
# What each kind suits, in the order alternatives are offered.
SHAPE_HINTS: Dict[str, str] = {
    "figures": "a few key numbers, each a value + a short label",
    "timeline": "dated items or milestones",
    "cards": "parallel items",
    "process": "ordered steps",
    "table": "a comparison across criteria",
    "comparison": "two options side by side",
    "two_columns": "two groups of points",
    "image_text": "a point with a picture",
    "quote": "one key statement",
    "bullets": "a short list",
    "team": "people",
}
_MAX_OTHER_KINDS = 5
# Kinds a requested kind may be built as when none of its slides fits, closest
# first: a list stays a list, a title slide a title slide. A kind absent here
# ("other") keeps the content-based fallback. Rationale: design.md.
CLOSE_KINDS: Dict[str, Tuple[SlideKind, ...]] = {
    "cover": ("section",),
    "agenda": ("bullets", "process", "timeline"),
    "section": ("quote",),
    "bullets": ("two_columns", "cards", "image_text"),
    "two_columns": ("comparison", "table"),
    "comparison": ("two_columns", "table"),
    "table": ("comparison", "two_columns"),
    "cards": ("bullets", "two_columns", "comparison", "process"),
    "figures": ("cards", "bullets"),
    "process": ("timeline", "bullets"),
    "timeline": ("process", "bullets"),
    "team": ("cards",),
    "quote": ("section", "bullets"),
    "image_text": ("bullets", "two_columns"),
    "closing": ("section", "bullets"),
    # A content placeholder able to hold a chart: the fit check keeps the rest out.
    "chart": ("bullets", "two_columns", "image_text"),
}

_MAX_KIND_OPTIONS = 3
# Slides one list may take: longer, it is a document the model must restructure.
_MAX_PARTS = 2
# A continuation on another template slide than its first part's.
_SPLIT_SWITCH = _KIND_STEP


@dataclass
class Misfit:
    """One reason a pattern cannot hold a slide, and the edit that would fix it."""

    text: str
    option: str = ""
    # Set for one element too long: what it is, its length, its zone's room.
    source: str = ""
    length: int = 0
    room: str = ""
    target: int = 0


@dataclass
class SlideProblem:
    """Why one slide of the plan fits no slide of the template, and what would."""

    index: int  # 1-based position in the plan's `slides`
    problem: str
    options: List[str]
    kind: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slide": self.index,
            "kind": self.kind,
            "problem": self.problem,
            "options": self.options,
        }


@dataclass
class Repeat:
    """A template slide, or a content kind, on three slides or more, and what
    else could vary it."""

    kind: str
    slides: List[int]  # 1-based positions in the plan
    labels: List[str]  # the template slides they use, distinct
    unused: List[str]  # unused variants of its kind, "label: zones"
    others: List[str]  # one unused slide per other non-structural kind
    suggested: List[str]  # "slides 9, 10 → cards holds … (why)"
    structural: bool = False  # cover/section/agenda/closing slides: never asked
    at_most: int = _NOTE_USES - 1  # the slides this group may hold

    @property
    def revisable(self) -> bool:
        return not self.structural and bool(
            self.unused or self.others or self.suggested
        )


@dataclass
class Assignment:
    # Aligned with the plan's slides; None for an entry that is not a slide.
    patterns: List[Optional[Pattern]] = field(default_factory=list)
    problems: List[SlideProblem] = field(default_factory=list)
    # Substitutions and repetitions the agent should hear about.
    notes: List[str] = field(default_factory=list)
    repeats: List[Repeat] = field(default_factory=list)
    # Per 1-based plan index of a split slide: its parts and their patterns.
    parts: Dict[int, List[Tuple[SlidePlan, Pattern]]] = field(default_factory=dict)
    # Aligned with the deck's slides: the entries before a list's continuation,
    # so the render numbers it on from its first part (never stored).
    starts: List[int] = field(default_factory=list)

    def deck(
        self, plan: DeckPlan
    ) -> Tuple[DeckPlan, List[Optional[Pattern]], List[int]]:
        """The deck as delivered, a split slide as its parts and no entry that
        is not a slide, with each slide's number in ``plan`` (shared by parts)."""
        slides: List[SlidePlan] = []
        patterns: List[Optional[Pattern]] = []
        numbers: List[int] = []
        for number, (slide, pattern) in enumerate(
            zip(plan.slides, self.patterns), start=1
        ):
            if slide.invalid_entry is not None:
                continue
            for part, chosen in self.parts.get(number, [(slide, pattern)]):
                slides.append(part)
                patterns.append(chosen)
                numbers.append(number)
        return plan.model_copy(update={"slides": slides}), patterns, numbers


def assignable(inventory: TemplateInventory) -> List[Pattern]:
    return [p for p in inventory.patterns if p.included and p.reusable]


# --- kind inference -----------------------------------------------------------------------


def _sequential(numbers: Sequence[str]) -> bool:
    digits = [n.strip() for n in numbers]
    return all(d.isdigit() for d in digits) and [int(d) for d in digits] == list(
        range(int(digits[0]), int(digits[0]) + len(digits))
    )


def infer_kinds(slide: SlidePlan) -> List[SlideKind]:
    """Kinds the slide's content shape suits, best first."""
    kinds: List[SlideKind]
    if slide.table is not None and slide.table.has_content():
        return ["table"]
    if _chart(slide) is not None:
        return ["chart", *CLOSE_KINDS["chart"]]
    if len(slide.columns) >= 2:
        headed = all(c.heading for c in slide.columns)
        kinds = (
            ["comparison", "two_columns"] if headed else ["two_columns", "comparison"]
        )
    elif slide.items:
        numbers = [i.number for i in slide.items if i.number]
        if numbers and all(lexicon.is_year(n) for n in numbers):
            kinds = ["timeline", "process", "cards", "figures"]
        elif numbers and not _sequential(numbers):
            kinds = ["figures", "cards", "process"]
        elif all(not (i.text or i.label or i.image) for i in slide.items):
            kinds = ["agenda", "process", "cards", "team"]
        elif numbers:
            kinds = ["process", "timeline", "agenda", "cards"]
        else:
            kinds = ["cards", "process", "team", "figures", "agenda"]
    elif slide.image or slide.images:
        kinds = ["image_text", "section", "bullets"]
    elif slide.bullets:
        kinds = (
            ["bullets", "two_columns", "comparison", "image_text", "quote"]
            if slide.title
            else ["quote", "bullets"]
        )
    elif slide.title or slide.subtitle:
        kinds = ["section", "quote"]
    else:
        kinds = ["closing"]
    # A short title that names a kind ("Sommaire", "Merci") breaks the tie.
    title = slide.title or ""
    named = lexicon.kind_from_name(title) if len(title.split()) <= 4 else None
    if named in kinds:
        kinds.remove(named)  # type: ignore[arg-type]
        kinds.insert(0, named)  # type: ignore[arg-type]
    elif named == "closing" and not slide.items and not slide.columns:
        kinds.insert(0, "closing")
    return kinds


# Text patterns of a list that another kind would show better.
_DATED = re.compile(r"^(?:\w{1,10}\.?\s+)?(?:19|20)\d{2}\b")
_STEP = re.compile(r"^(?:\d{1,2}\s*[.)]|(?:étape|etape|step|phase)\s*\d)", re.I)
_LABELLED = re.compile(r"^([^:]{1,40}?)\s*:\s*(.*)$")
_FIGURE_CHARS = 40


def _lines(slide: SlidePlan) -> List[str]:
    """The slide's text as bullet lines, a sub-line prefixed with '- '."""
    lines = list(slide.bullets)
    for column in slide.columns:
        lines += ([f"{column.heading} :"] if column.heading else []) + [
            f"- {b.removeprefix('- ')}" for b in column.bullets
        ]
    for item in slide.items:
        head = " ".join(t for t in (item.number, item.heading) if t)
        body = " ".join(t for t in (item.text, item.label) if t)
        lines.append(f"{head} : {body}" if head and body else head or body)
    return [re.sub(r"[*_`]", "", line).strip() for line in lines if line.strip()]


class Shape(NamedTuple):
    kinds: Tuple[SlideKind, ...]
    entries: int
    why: str
    longest: int  # chars of the longest entry, its sub-lines included


def content_shape(slide: SlidePlan) -> Optional[Shape]:
    """The kinds a slide's lines suit, how many entries they make and why,
    read from text patterns only: dates, steps, figures, labelled groups."""
    lines = _lines(slide)
    sub = [line.startswith("- ") for line in lines]
    texts = [line[2:].strip() if s else line for line, s in zip(lines, sub)]
    top = [t for t, s in zip(texts, sub) if not s]
    if len(top) >= 3 and all(_STEP.match(t) for t in top):
        return Shape(("process",), len(top), "numbered steps", _longest(top))
    dated = [t for t in texts if _DATED.match(t)]
    if len(dated) >= 3 or (len(dated) >= 2 and 2 * len(dated) >= len(texts)):
        return Shape(("timeline",), len(dated), "dated items", _longest(dated))
    if not any(sub) and 2 <= len(top) <= 6:
        if all(len(t) <= _FIGURE_CHARS and re.search(r"\d", t) for t in top):
            return Shape(("figures",), len(top), "short figures", _longest(top))
    # Each top-level line with its sub-lines: [labelled, text after ':', sub-lines, chars].
    entries: List[List[Any]] = []
    for text, is_sub in zip(texts, sub):
        if is_sub and entries:
            entries[-1][2] = True
            entries[-1][3] += len(text)
        elif not is_sub:
            m = _LABELLED.match(text)
            short = m is not None and len(m.group(1).split()) <= 4
            entries.append([short, bool(m and m.group(2)), False, len(text)])
    n = len(entries)
    if not (2 <= n <= 6 and all(e[0] and (e[1] or e[2]) for e in entries)):
        return None
    longest = max(e[3] for e in entries)
    if all(e[2] and not e[1] for e in entries):
        kinds: Tuple[SlideKind, ...] = (
            ("two_columns", "cards") if n == 2 else ("cards",)
        )
        return Shape(
            kinds, n, f"{n} groups of '- ' lines under 'Label :' lines", longest
        )
    return Shape(("cards",), n, "parallel 'Label : text' points", longest)


def _longest(texts: List[str]) -> int:
    return max(len(t) for t in texts)


# --- fit check ----------------------------------------------------------------------------


def _list_name(source: str) -> str:
    return re.sub(r"\[\d+\]$", "", source)


def _too_long(
    zone: Zone, lines: List[_Line], what: str, size: Tuple[int, int]
) -> Misfit:
    per_line, rows = zone_capacity(zone, *size)
    room = capacity_text(per_line, rows)
    if len(lines) == 1:
        source = lines[0].source or what
        length, target = len(lines[0].text), per_line * rows
        return Misfit(
            f"{source} is {length} chars; this zone holds {room}",
            f"shorten {source} to {room}",
            source,
            length,
            room,
            target,
        )
    longest = max(lines, key=lambda line: len(line.text))
    name = _list_name(longest.source) if longest.source else what
    total = sum(len(line.text) for line in lines)
    return Misfit(
        f"{name}: {len(lines)} entries, {total} chars; this zone holds {room} "
        f"(longest: {longest.source or name}, {len(longest.text)} chars)",
        f"keep {name} within {room}: shorten or drop entries",
    )


def _check_zone(
    zone: Zone,
    lines: List[_Line],
    what: str,
    size: Tuple[int, int],
    reasons: List[Misfit],
) -> float:
    if zone.grows or not lines:
        return 0.0
    _, scale, truncated = _fit(zone, lines, size[0], size[1])
    if truncated:
        reasons.append(_too_long(zone, lines, what, size))
        return 0.0
    return _SHRUNK if scale is not None else 0.0


_NO_PLACE = ": this slide has no place for it"


def _chart(slide: SlidePlan) -> Optional[PlanChart]:
    chart = slide.chart
    return chart if chart is not None and chart.has_content() else None


def _no_place(what: str, pattern: Pattern) -> Misfit:
    option = f"drop {what}"
    if what == "chart":
        option = "give the chart a slide of its own (title and chart)"
    if what == "bullets" and pattern.groups:
        most = max(g.count for g in pattern.groups)
        option = f"give the bullets as items (at most {most})"
    elif what == "items" and any(z.role in ("body", "caption") for z in pattern.zones):
        option = "give the items as bullets"
    return Misfit(what + _NO_PLACE, option)


def unplaced(
    inventory: TemplateInventory, slide: SlidePlan, kind: Optional[str]
) -> List[str]:
    """The slide's fields that no template slide of ``kind`` has a place for,
    beside the rest of its content; none when the template has no such slide."""
    size = (inventory.slide_width, inventory.slide_height)
    found: Optional[set[str]] = None
    for pattern in assignable(inventory):
        if pattern.kind != kind:
            continue
        reasons, _ = misfit(pattern, slide, size)
        lost = {
            r.text.removesuffix(_NO_PLACE)
            for r in reasons
            if r.text.endswith(_NO_PLACE)
        }
        found = lost if found is None else found & lost
    return sorted(found or ())


def misfit(
    pattern: Pattern, slide: SlidePlan, size: Tuple[int, int]
) -> Tuple[List[Misfit], float]:
    """Why ``pattern`` cannot hold all of ``slide`` (empty when it can), and the
    cost of the fit. Uses the renderer's own placement, so a fitting pattern
    loses nothing when rendered."""
    if not pattern.fillable:
        if not has_content(slide) or _only_names_the_slide(slide, pattern):
            return [], 0.0
        return [
            Misfit(
                "this slide is shown as is and takes no content",
                f"send only the title '{pattern.label}'",
            )
        ], 0.0
    reasons: List[Misfit] = []
    lost: List[str] = []
    text = _assign_text(pattern, slide, lost)
    images = list(dict.fromkeys(([slide.image] if slide.image else []) + slide.images))
    image_zones = sum(1 for z in pattern.zones if z.role == "image")
    if len(images) > image_zones:
        reasons.append(
            Misfit(
                f"images: {len(images)} given, max {image_zones}",
                f"keep at most {image_zones} image(s)",
            )
        )
    capacity = max((g.count for g in pattern.groups), default=0)
    if slide.items and not capacity:
        lost.append("items")
    elif len(slide.items) > capacity:
        reasons.append(
            Misfit(
                f"items: {len(slide.items)} given, max {capacity}",
                f"trim to {capacity} items or split them over two slides",
            )
        )
    lost.extend(_unused_item_fields(pattern.groups, slide, size))
    held = [w for w in lost if w.startswith("column ")]
    if held:
        most = int(held[0].split()[1]) - 1
        reasons.insert(
            0,
            Misfit(
                f"columns: {len(slide.columns)} given, max {most}",
                f"keep at most {most} columns or split them over two slides",
            ),
        )
    cost = 0.0
    tables = [z for z in pattern.zones if z.role == "table"]
    given = slide.table is not None and slide.table.has_content()
    if given and not tables:
        lost.append("table")
    elif given and slide.table is not None:
        fit = fit_table(tables[0], slide.table)
        if fit.problem is not None:
            reasons.append(Misfit(*fit.problem))
        elif fit.scale is not None:
            cost += _SHRUNK
    elif tables:
        reasons.append(
            Misfit(
                "this slide shows a table and needs `table` {header, rows}",
                "give the content as `table`, or another kind",
            )
        )
    chart = _chart(slide)
    host = chart_host(pattern, text) if chart is not None else None
    if chart is not None and host is None:
        lost.append("chart")
    elif chart is not None and host is not None:
        reasons.extend(
            Misfit(*found) for found in charts.fit_problems(host, chart, size)
        )
    elif any(z.role == "chart" for z in pattern.zones):
        reasons.append(
            Misfit(
                "this slide shows a chart and needs `chart` {type, categories, series}",
                "give the content as `chart`, or another kind",
            )
        )
    reasons[:0] = [_no_place(what, pattern) for what in lost if what not in held]

    # A framed picture left empty shows its layout's frame.
    empty = _reading_order([z for z in pattern.zones if z.role == "image"])
    framed = any(z.framed for z in empty[len(images) :])
    zones = {z.key: z for z in pattern.zones}
    for key, lines in text.items():
        zone = zones[key]
        cost += _check_zone(
            zone, lines, SLIDE_FIELDS.get(zone.role, "bullets"), size, reasons
        )
    for group in pattern.groups:
        group_text, pictures, used = _assign_group(group, slide, size)
        framed |= any(
            z.framed and not pictures.get(z.key)
            for item in group.items[:used]
            for z in item
        )
        item_zones = {z.key: z for item in group.items for z in item}
        long_items: Dict[str, List[Misfit]] = {}
        for key, lines in group_text.items():
            zone = item_zones[key]
            what = f"items[].{ITEM_FIELDS.get(zone.role, zone.role)}"
            found: List[Misfit] = []
            cost += _check_zone(zone, lines, what, size, found)
            cost += _HEADING_LEAD if lines and lines[0].heading else 0.0
            for reason in found:
                long_items.setdefault(what, []).append(reason)
        # One line per item field: six cards too long are one fix, not six.
        for what, found in long_items.items():
            reasons.append(found[0] if len(found) == 1 else _many(found))
    if framed:
        reasons.append(
            Misfit(
                "images: this slide's picture area shows a frame when left empty",
                "give a picture from list_images_in_folder for each, or use another kind",
            )
        )
    if reasons:
        return reasons, 0.0

    for zone in pattern.zones:
        if zone.role == "image":
            cost += 0.0 if images else _IMAGE_HOLE
        elif (
            zone.role not in ("keep", "table", "chart")
            and zone.key not in text
            and zone is not host
        ):
            cost += _EMPTY_ZONE
    for group in pattern.groups:
        for item, zones in zip(slide.items, group.items):
            holes = sum(1 for z in zones if z.role == "image")
            cost += 0.0 if item.image else _IMAGE_HOLE * holes
    cost += _UNUSED_ITEM * max(0, capacity - len(slide.items)) if slide.items else 0.0
    if pattern.source == "layout":
        cost += _LAYOUT
    return reasons, cost


def _many(found: List[Misfit]) -> Misfit:
    """``items[0].text is 150 chars; …`` ×N folded into one reason."""
    if any(not f.source for f in found):
        return Misfit("; ".join(f.text for f in found), found[0].option)
    tightest = min(found, key=lambda f: f.target)
    return Misfit(
        f"{', '.join(f.source for f in found)} are "
        f"{', '.join(str(f.length) for f in found)} chars; each zone holds {found[0].room}",
        f"shorten every {re.sub(r'\[\d+\]', '[]', found[0].source)} to {tightest.room}",
    )


# --- text the deck would drop -----------------------------------------------------------


def _unbalanced(
    name: str, body: str, entries: List[Tuple[Optional[str], bool]]
) -> List[str]:
    """In a list where one entry has a heading and a body, an entry missing one
    is a half-written entry: its column or card would show a heading alone."""
    if not any(heading and has_body for heading, has_body in entries):
        return []
    found = []
    for index, (heading, has_body) in enumerate(entries):
        if heading and not has_body:
            found.append(f"{name}[{index}] has heading '{heading}' but no {body}")
        elif has_body and not heading:
            found.append(f"{name}[{index}] has {body} but no heading")
    return found


def _item_entries(items: List[PlanItem]) -> List[Tuple[Optional[str], bool]]:
    """An item's figure leads it as a heading would; a figure with its label
    (a figures card) is a whole entry, never reported."""
    return [
        (None, False)
        if i.number and i.label and not i.text
        else (i.heading or i.number, bool(i.text))
        for i in items
    ]


def _dropped_text(index: int, slide: SlidePlan) -> Optional[SlideProblem]:
    """Plan text the coercion could not map, or a half-written column or item."""
    found: List[str] = []
    options: List[str] = []
    if slide.ignored_fields:
        found.append(f"{', '.join(slide.ignored_fields)}: not a slide field")
        options.append(
            "put that text in title, subtitle, bullets, columns, items or notes"
        )
    for n, column in enumerate(slide.columns):
        if column.ignored_fields:
            found.append(
                f"columns[{n}]: {', '.join(column.ignored_fields)} is not a column field"
            )
            options.append("write columns as a list, one {heading, bullets} per column")
    if slide.chart is not None and slide.chart.ignored_fields:
        found.append(
            f"chart: {', '.join(slide.chart.ignored_fields)} is not a chart field"
        )
        options.append("give the chart only type, categories, series, title, unit")
    for n, item in enumerate(slide.items):
        if item.ignored_fields:
            found.append(
                f"items[{n}]: {', '.join(item.ignored_fields)} is not an item field"
            )
            options.append("give each item only number, heading, text, label, image")
    halves = _unbalanced(
        "columns", "bullets", [(c.heading, bool(c.bullets)) for c in slide.columns]
    ) + _unbalanced("items", "text", _item_entries(slide.items))
    if not found and not halves:
        return None
    parts = (["this text would be lost: " + "; ".join(found)] if found else []) + (
        ["incomplete entries: " + "; ".join(halves)] if halves else []
    )
    if halves:
        options.append("complete each entry, or drop the half-written one")
    return SlideProblem(
        index, "; ".join(parts), list(dict.fromkeys(options)), slide.kind
    )


def _chart_data(index: int, slide: SlidePlan) -> Optional[SlideProblem]:
    """The chart's data, checked once whatever slide will show it."""
    chart = slide.chart
    if chart is None:
        return None
    found = charts.data_problems(chart)
    if not found:
        return None
    return SlideProblem(
        index,
        "; ".join(what for what, _ in found),
        list(dict.fromkeys(fix for _, fix in found)),
        slide.kind,
    )


# --- deck assignment ----------------------------------------------------------------------


@dataclass
class _Slide:
    index: int  # 1-based position in the plan
    plan: SlidePlan
    first: bool
    last: bool
    # Kind tiers, best first: the first tier with a fitting pattern is used.
    tiers: List[List[SlideKind]] = field(default_factory=list)
    # Every assignable pattern, with its misfit reasons and cost.
    checked: List[Tuple[Pattern, List[Misfit], float]] = field(default_factory=list)
    candidates: List[Tuple[Pattern, float]] = field(default_factory=list)
    # A slide that fits nothing: the pattern closest to holding it, its misfits.
    closest: Optional[Tuple[Pattern, List[Misfit]]] = None
    # Part k of n of a split list, and the entries before it.
    part: int = 1
    parts: int = 1
    start: int = 0


def _kept(
    slide: _Slide, candidates: List[Tuple[Pattern, float]]
) -> List[Tuple[Pattern, float]]:
    """The template slide the delivered deck showed this slide on, alone, while
    it is still among the best-ranked kind's fits: a text change keeps its
    design, a kind the template replaced included."""
    kept = [c for c in candidates if c[0].id == slide.plan.built_on]
    return kept or candidates


def _asked(slide: _Slide, has_cover: bool) -> Optional[SlideProblem]:
    """A design the user asked for (`like`): that template slide alone, priced
    as no reuse, or why the slide cannot take it."""
    plan = slide.plan
    whose = (
        f"slide {plan.asked_from}'s design" if plan.asked_from else "the design asked"
    )
    drop = (
        "or drop the `like` change: the tool then picks a template slide that holds it"
    )
    found = next((c for c in slide.checked if c[0].id == plan.asked_design), None)
    if found is None:
        return SlideProblem(
            slide.index,
            f"{whose} (template slide '{plan.asked_design}') is no longer in the template",
            [drop.removeprefix("or ")],
            plan.kind,
        )
    pattern, reasons, cost = found
    named = f"{whose} (template slide '{pattern.label}', a '{pattern.kind}' slide)"
    if plan.kind and plan.kind != pattern.kind:
        return SlideProblem(
            slide.index,
            f"{named} holds '{pattern.kind}' content, but the slide asks for kind '{plan.kind}'",
            [
                f"set its kind to '{pattern.kind}' and shape its content for that slide",
                f"or drop the `like` change to keep kind '{plan.kind}'",
            ],
            plan.kind,
        )
    if not _allowed(pattern, slide, has_cover):
        why = (
            f"{named} can only be the {'first' if pattern.kind == 'cover' else 'last'} slide"
            if pattern.kind in ("cover", "closing")
            else f"the first slide is always the template's cover, not {named}"
        )
        return SlideProblem(
            slide.index,
            why,
            ["use the design of another slide", drop],
            plan.kind,
        )
    if reasons:
        return SlideProblem(
            slide.index,
            f"the slide does not fit {named}: " + "; ".join(m.text for m in reasons),
            [m.option for m in reasons if m.option] + [drop],
            plan.kind,
        )
    slide.candidates = [(pattern, cost)]
    return None


def _allowed(pattern: Pattern, slide: _Slide, has_cover: bool) -> bool:
    if pattern.kind == "cover":
        return slide.first
    if slide.first and has_cover:
        return False
    if pattern.kind == "closing":
        return slide.last
    return True


def _tiers(slide: _Slide, has_cover: bool) -> List[List[SlideKind]]:
    """The requested kind, then its close kinds; with no kind (or one with no
    close kinds), the kinds the content suggests, then any kind."""
    if slide.first and has_cover:
        return [["cover"]]
    asked = slide.plan.kind
    if asked and asked in CLOSE_KINDS:
        return [[asked], list(CLOSE_KINDS[asked])]
    inferred = infer_kinds(slide.plan)
    tiers: List[List[SlideKind]] = [[asked]] if asked else []
    tiers.append([k for k in inferred if k != asked])
    seen = set(inferred) | {asked}
    tiers.append([k for k in SLIDE_KINDS if k not in seen])
    return tiers


def _close(slide: _Slide) -> Optional[Tuple[SlideKind, ...]]:
    """The close kinds of the requested kind; None when the fallback is open."""
    asked = slide.plan.kind
    return CLOSE_KINDS.get(asked) if asked else None


def _candidates(slide: _Slide, has_cover: bool) -> List[Tuple[Pattern, float]]:
    for tier in slide.tiers:
        found = [
            (p, cost + _KIND_STEP * tier.index(p.kind))
            for p, reasons, cost in slide.checked
            if not reasons and p.kind in tier and _allowed(p, slide, has_cover)
        ]
        if found:
            return found
    return []


# --- a list continued on a second slide ---------------------------------------------------


@dataclass
class _Split:
    kind: SlideKind
    what: str  # "items" or "rows"
    entries: int
    most: int  # the kind's largest slide, in items; 0 for a table
    slides: List[_Slide]


def _table(slide: SlidePlan) -> Optional[PlanTable]:
    table = slide.table
    return table if table is not None and table.has_content() else None


def _entries(slide: SlidePlan) -> int:
    """The entries of the slide's list: items, else table rows."""
    table = _table(slide)
    return len(slide.items) or (len(table.rows) if table is not None else 0)


def _too_tall(reasons: List[Misfit]) -> bool:
    """Only the table's height keeps it out: fewer rows would fit."""
    return bool(reasons) and all(
        r.text.startswith("table: ") and " rows need " in r.text for r in reasons
    )


def _sizes(entries: int, count: int) -> List[int]:
    """Balanced, the first parts one longer: 9 over 2 → 5 + 4."""
    base, extra = divmod(entries, count)
    return [base + (1 if k < extra else 0) for k in range(count)]


def _parts(slide: _Slide, count: int) -> List[_Slide]:
    plan, table = slide.plan, _table(slide.plan)
    rows = table.rows if table is not None else []
    found: List[_Slide] = []
    start = 0
    for k, size in enumerate(_sizes(_entries(plan), count), start=1):
        update: Dict[str, Any] = {
            "title": f"{plan.title} ({k}/{count})" if plan.title else plan.title,
            "notes": plan.notes if k == 1 else None,
        }
        if plan.items:
            update["items"] = plan.items[start : start + size]
        elif table is not None:
            update["table"] = PlanTable(
                header=table.header, rows=rows[start : start + size]
            )
        found.append(
            _Slide(
                slide.index,
                plan.model_copy(update=update),
                first=slide.first and k == 1,
                last=slide.last and k == count,
                part=k,
                parts=count,
                start=start,
            )
        )
        start += size
    return found


def _split(
    slide: _Slide, pool: List[Pattern], size: Tuple[int, int], has_cover: bool
) -> Optional[_Split]:
    """The slide's list over at most ``_MAX_PARTS`` slides of its own kind (the
    requested one, or the first inferred one that holds it), when its entry
    count alone keeps it off that kind; None otherwise. Bullets never split."""
    plan, entries = slide.plan, _entries(slide.plan)
    if entries < 2 or (slide.first and has_cover):
        return None
    for kind in slide.tiers[0]:
        mine = [p for p in pool if p.kind == kind]
        most = max((g.count for p in mine for g in p.groups), default=0)
        if plan.items:
            if not most or entries <= most:
                continue
            count = math.ceil(entries / most)
        else:
            tables = [
                r
                for p, r, _ in slide.checked
                if p.kind == kind and any(z.role == "table" for z in p.zones)
            ]
            if not tables or not all(_too_tall(r) for r in tables):
                continue
            count = _MAX_PARTS
        if count > _MAX_PARTS:
            continue
        parts = _parts(slide, count)
        for part in parts:
            part.tiers = [[kind]]
            part.checked = [(p, *misfit(p, part.plan, size)) for p in mine]
            part.candidates = [
                (p, cost)
                for p, reasons, cost in part.checked
                if not reasons and _allowed(p, part, has_cover)
            ]
        if all(part.candidates for part in parts):
            what = "items" if plan.items else "rows"
            return _Split(kind, what, entries, most if plan.items else 0, parts)
    return None


def _split_note(split: _Split, at: Dict[int, int]) -> str:
    first = split.slides[0]
    sizes = " + ".join(str(_entries(s.plan)) for s in split.slides)
    more = "a second" if len(split.slides) == 2 else f"{len(split.slides) - 1} more"
    marked = (
        ", titles marked " + " and ".join(f"({s.part}/{s.parts})" for s in split.slides)
        if first.plan.title
        else ""
    )
    header = ", header repeated" if split.what == "rows" else ""
    if split.most:
        why = f"the largest '{split.kind}' slide holds {split.most}"
        remedy = f"send at most {split.most} {split.what}"
    else:
        why = f"they do not fit one '{split.kind}' slide"
        remedy = "send fewer rows or shorter cells"
    return (
        f"Slide {at[first.index]}: its {split.entries} {split.what} continue on {more} "
        f"'{split.kind}' slide ({sizes}{header}{marked}): {why}. Nothing to do; to "
        f"keep one slide, {remedy}."
    )


def _own(slide: _Slide, has_cover: bool) -> List[Tuple[Pattern, List[Misfit]]]:
    """Patterns the position allows, of a kind the slide's tiers rank."""
    kinds = {k for tier in slide.tiers for k in tier}
    return [
        (p, r)
        for p, r, _ in slide.checked
        if p.kind in kinds and _allowed(p, slide, has_cover)
    ]


def _tableless(slide: _Slide) -> bool:
    table = slide.plan.table
    return (
        table is not None
        and table.has_content()
        and not any(z.role == "table" for p, _, _ in slide.checked for z in p.zones)
    )


def _chartless(slide: _Slide) -> bool:
    """The slide has a chart and no template slide has a place for one."""
    return _chart(slide.plan) is not None and not any(
        z.role == "chart" or z.chart_capable
        for p, _, _ in slide.checked
        for z in p.zones
    )


def _chart_options(slide: _Slide) -> List[str]:
    """What the chart's data can become on this template, best first."""
    chart = _chart(slide.plan)
    kinds = {p.kind: p for p, _, _ in slide.checked}
    options = []
    if "table" in kinds:
        options.append(
            "give the data as `table` (a row per category, a column per series)"
        )
    values = len(chart.categories) * len(chart.series) if chart is not None else 0
    most = (
        max((g.count for g in kinds["figures"].groups), default=0)
        if "figures" in kinds
        else 0
    )
    if most and values <= most:
        options.append(
            f"give the {values} values as items of a 'figures' slide "
            "(number: the value, label: the category)"
        )
    options.append("keep the key numbers as bullets")
    return options


def _closest(slide: _Slide, has_cover: bool) -> Optional[Tuple[Pattern, List[Misfit]]]:
    """The kind closest to the content, then fewest problems, then the roomiest;
    None when no slide can take the position or a table must be rewritten."""
    # The asked kind (or, with none, the inferred kinds) ranks first: the advice
    # should be about that shape, not about an unrelated kind that happens to fit.
    rank = {k: 0 for tier in slide.tiers[:-1] for k in tier}
    rank.update({k: 1 for k in slide.tiers[-1]})
    own = _own(slide, has_cover)
    if not own or _tableless(slide) or _chartless(slide):
        return None
    # A chart's advice is about a slide that can show it.
    hosts = _chart(slide.plan) is not None
    return min(
        own,
        key=lambda pr: (
            rank[pr[0].kind],
            hosts and not any(z.role == "chart" for z in pr[0].zones),
            *_fewest(pr),
        ),
    )


def _fewest(pair: Tuple[Pattern, List[Misfit]]) -> Tuple[int, int]:
    """Fewest problems, then the roomiest."""
    pattern, reasons = pair
    room = sum((z.chars_per_line or 0) * (z.max_lines or 0) for z in pattern.zones)
    return len(reasons), -room


def _why_not(
    slide: _Slide, offered: set[str], asked: Optional[str] = None
) -> Optional[str]:
    """Why the requested kind cannot be used at all here; None when only its
    content keeps it out."""
    asked = asked or slide.plan.kind
    if asked == "cover" and not slide.first:
        return "only the first slide can be the cover"
    if asked == "closing" and not slide.last:
        return "a closing slide can only end the deck"
    if asked and asked not in offered:
        return f"this template has no '{asked}' slide"
    return None


def _once_fixed(slide: _Slide, has_cover: bool) -> List[Tuple[Pattern, float]]:
    """Where a misfit slide lands once its closest fit's problems are fixed: that
    pattern, and the variants of its kind with no other problem."""
    if slide.closest is None:
        return []
    closest, reasons = slide.closest
    fixed = {r.text for r in reasons}
    return [
        (p, 0.0)
        for p, found, _ in slide.checked
        if p.kind == closest.kind
        and _allowed(p, slide, has_cover)
        and {r.text for r in found} <= fixed
    ]


def _same_problem(slide: _Slide) -> set[str]:
    """Patterns sharing one of a misfit slide's problems: never offered to vary it."""
    if slide.closest is None:
        return set()
    texts = {r.text for r in slide.closest[1]}
    return {
        p.id for p, found, _ in slide.checked if any(r.text in texts for r in found)
    }


def _problem(slide: _Slide, has_cover: bool, offered: set[str]) -> SlideProblem:
    """The closest pattern's misfits, named down to the element, with fixes."""
    own = _own(slide, has_cover)
    options: List[str] = []
    if _tableless(slide):
        return SlideProblem(
            slide.index,
            "table: this template has no table slide",
            [
                "write the table as items (one item per row) or as columns",
                "or keep its key rows as bullets",
            ],
            slide.plan.kind,
        )
    if _chartless(slide):
        return SlideProblem(
            slide.index,
            "chart: this template has no slide for a chart",
            _chart_options(slide),
            slide.plan.kind,
        )
    asked, close = slide.plan.kind, _close(slide)
    if slide.closest is None and close is not None:
        problem = (
            f"this template has no '{asked}' slide and no close kind "
            f"({', '.join(close)})"
        )
        options.append("leave `kind` out: the slide goes to the kind its content suits")
    elif slide.closest is None:
        problem = "this template has no slide that can take this position"
        options.append("merge this content into another slide, or remove it")
    else:
        closest, reasons = slide.closest
        # A forced cover is not a close kind: the cover prefix below says why.
        forced = slide.first and has_cover
        lead = "closest fit"
        if close is not None and closest.kind != asked and not forced:
            why = _why_not(slide, offered)
            lead = f"{why}; closest close kind" if why else "closest close kind"
        problem = f"{lead}, a '{closest.kind}' slide: " + "; ".join(
            r.text for r in reasons
        )
        # With a requested kind, the count that matters is its own slides'.
        sized = [p for p, _ in own if close is None or p.kind == closest.kind]
        where = "slide of this template" if close is None else f"'{closest.kind}' slide"
        most = max((g.count for p in sized for g in p.groups), default=0)
        given = len(slide.plan.items)
        if slide.plan.items and most and given > most:
            reasons = [r for r in reasons if not r.text.startswith("items:")]
            count = f"items: {given} given; the largest {where} holds {most}"
            if given > most * _MAX_PARTS:
                # Over what a continuation slide adds: the model restructures it.
                count += f", {_MAX_PARTS} slides hold {most * _MAX_PARTS}"
                options += [
                    f"trim to {most * _MAX_PARTS} items (beyond {most} they continue "
                    "on a second slide)",
                    f"or keep {most} here and move the rest to slides of your own",
                ]
            else:
                options += [f"trim to {most} items", "split the items over two slides"]
            problem = "; ".join([count] + [r.text for r in reasons])
        options += [r.option for r in reasons if r.option]
        options.append(f"a '{closest.kind}' slide takes: {zone_summary(closest)}")
        options += _close_options(slide, own, closest.kind)
    if slide.first and has_cover:
        problem = "the first slide is always the template's cover; " + problem
        takes = f": {zone_summary(own[0][0])}" if own else ""
        options.append(f"add a cover slide before it{takes}")
        fitting = [
            p.kind
            for p, reasons, _ in slide.checked
            if not reasons and p.kind != "cover"
        ]
        for kind in list(dict.fromkeys(fitting))[:_MAX_KIND_OPTIONS]:
            options.append(f"as a second slide, kind '{kind}' holds this content")
    return SlideProblem(
        slide.index, problem, list(dict.fromkeys(options)), slide.plan.kind
    )


def _close_options(
    slide: _Slide, own: List[Tuple[Pattern, List[Misfit]]], named: str
) -> List[str]:
    """The close kinds the template offers here, each with what it takes."""
    found = []
    for kind in _close(slide) or ():
        mine = [pr for pr in own if pr[0].kind == kind]
        if kind != named and mine:
            best = min(mine, key=_fewest)[0]
            found.append(
                f"or rewrite it as kind '{kind}', which takes: {zone_summary(best)}"
            )
    return found[:_MAX_KIND_OPTIONS]


def _substitution(
    slide: _Slide, chosen: Pattern, offered: set[str], has_cover: bool, number: int
) -> Optional[str]:
    """What was built instead of the requested kind, why, and the edit that
    would give the requested kind."""
    # A chart in a content area is a substitution even when no kind was asked.
    asked = slide.plan.kind or ("chart" if _chart(slide.plan) is not None else None)
    # The first slide is the cover by rule, and the description says so.
    if not asked or chosen.kind == asked or (slide.first and chosen.kind == "cover"):
        return None
    head = f"Slide {number}: built as '{chosen.kind}' instead of '{asked}'"
    if asked == "chart" and chosen.kind != "chart":
        head += ", the chart in its content area"
    why = _why_not(slide, offered, asked)
    if why is not None:
        remedy = (
            "To make it the closing slide, move it to the end; otherwise nothing to do."
            if asked == "closing" and not slide.last
            else "Nothing to do."
        )
        return f"{head}: {why}. {remedy}"
    mine = [
        (p, r)
        for p, r, _ in slide.checked
        if p.kind == asked and _allowed(p, slide, has_cover)
    ]
    if not mine:  # pragma: no cover - _why_not covers every absent kind
        return f"{head}. Nothing to do."
    _, reasons = min(mine, key=_fewest)
    fixes = list(dict.fromkeys(r.option for r in reasons if r.option))
    remedy = (
        f"To get the '{asked}' slide, call again and {'; '.join(fixes)}; "
        "otherwise nothing to do."
        if fixes
        else "Nothing to do."
    )
    return (
        f"{head}: the '{asked}' slide does not fit "
        f"({'; '.join(r.text for r in reasons)}). {remedy}"
    )


class _Caps(NamedTuple):
    """The author's max, raised where the deck forces more."""

    slide: int  # uses of one template slide
    kind: int  # slides of one content kind


def _content(slide: _Slide, pattern: Optional[Pattern] = None) -> bool:
    """Counts towards variety: not a cover, section, agenda or closing."""
    return _wanted(slide) not in _STRUCTURAL and (
        pattern is None or pattern.kind not in _STRUCTURAL
    )


def _caps(slides: List[_Slide], pool: List[Pattern], max_uses: int) -> _Caps:
    content = sum(1 for s in slides if s.candidates and _content(s) and s.part == 1)
    variants = [p.kind for p in pool if p.kind not in _STRUCTURAL]

    def cap(distinct: int) -> int:
        return max(max_uses, math.ceil(content / distinct)) if distinct else max_uses

    return _Caps(cap(len(variants)), cap(len(set(variants))))


@dataclass
class _Path:
    cost: float
    chosen: Tuple[int, ...]  # candidate index per slide so far
    uses: Dict[str, int]
    content: Dict[str, int]  # uses by content slides, priced against the caps


def _beam(slides: List[_Slide], caps: Optional[_Caps] = None) -> List[Pattern]:
    """Cheapest pattern sequence under a deck-wide reuse cost. The use counts
    make the cost non-local, so a bounded beam replaces exact dynamic
    programming; paths with the same last two choices and uses are merged."""
    paths = [_Path(0.0, (), {}, {})]
    for i, slide in enumerate(slides):
        steps: List[Tuple[float, int, int]] = []
        for n, path in enumerate(paths):
            last = slides[i - 1].candidates[path.chosen[-1]][0].id if i >= 1 else None
            before = slides[i - 2].candidates[path.chosen[-2]][0].id if i >= 2 else None
            for c, (pattern, cost) in enumerate(slide.candidates):
                step = path.cost + cost + _REUSE * path.uses.get(pattern.id, 0)
                if slide.part > 1:
                    # A list's continuation: its first part's slide again is free.
                    if pattern.id != last:
                        step += _SPLIT_SWITCH
                    else:
                        step = path.cost + cost
                elif pattern.id == last:
                    step += _REPEAT + (_TRIPLE if pattern.id == before else 0.0)
                if (
                    caps is not None
                    and slide.part == 1
                    and _content(slide, pattern)
                    and path.content.get(pattern.id, 0) >= caps.slide
                ):
                    step += _OVER_MAX
                steps.append((step, n, c))
        steps.sort()
        kept: List[_Path] = []
        seen: set = set()
        for step, n, c in steps:
            path = paths[n]
            pattern = slide.candidates[c][0]
            uses = dict(path.uses)
            content = dict(path.content)
            # A split list counts as one slide.
            if slide.part == 1:
                uses[pattern.id] = uses.get(pattern.id, 0) + 1
            if slide.part == 1 and _content(slide, pattern):
                content[pattern.id] = content.get(pattern.id, 0) + 1
            state = (
                path.chosen[-1:],
                c,
                frozenset(uses.items()),
                frozenset(content.items()),
            )
            if state in seen:
                continue
            seen.add(state)
            kept.append(_Path(step, path.chosen + (c,), uses, content))
            if len(kept) == _BEAM:
                break
        paths = kept
    return [slides[i].candidates[c][0] for i, c in enumerate(paths[0].chosen)]


def _room(fields: List[List[Zone]]) -> Optional[int]:
    """Chars one entry holds over its measured fields, each at its tightest
    zone; None when none is measured. An unmeasured field adds nothing: read
    as endless room, it favoured a slide whose only text was a 12-char label."""
    rooms = []
    for zones in fields:
        bounded = [z for z in zones if not z.grows and z.chars_per_line and z.max_lines]
        if bounded:
            rooms.append(
                min((z.chars_per_line or 0) * (z.max_lines or 0) for z in bounded)
            )
    return sum(rooms) if rooms else None


@dataclass
class _Variant:
    holes: bool  # its items hold pictures the content does not have
    layout: bool
    hint: str  # what it holds, in the catalogue's words
    room: Optional[int]  # chars per entry; None when it grows


def _holding(pattern: Pattern, entries: int) -> Optional[_Variant]:
    """How ``pattern`` would hold that many entries, or None when it cannot."""
    if pattern.groups:
        group = max(pattern.groups, key=lambda g: g.count)
        if group.count < entries:
            return None
        by_field: Dict[str, List[Zone]] = {}
        for item in group.items:
            for zone in item:
                field = ITEM_FIELDS.get(zone.role, zone.role)
                by_field.setdefault(field, []).append(zone)
        holes = by_field.pop("image", None) is not None
        hint, room = group_summary(group), _room(list(by_field.values()))
    elif pattern.kind in ("two_columns", "comparison") and entries == 2:
        bodies = [z for z in pattern.zones if z.role in ("body", "caption")]
        if len(bodies) != 2:
            return None
        headings = [z for z in pattern.zones if z.role == "heading"]
        holes, room = False, _room([bodies] + ([headings] if headings else []))
        heading = f"heading{_limit(headings)}, " if headings else ""
        hint = f"exactly 2 columns [{heading}bullets{_limit(bodies)}]"
    else:
        return None
    return _Variant(holes, pattern.source == "layout", hint, room)


def _advice(pool: List[Pattern], kind: str, shape: Shape) -> Optional[str]:
    """``kind`` and what its favoured slide holds for this content, with the
    size to shorten to when the longest entry would not fit; None if none can.
    Favoured as the assigner would: room, no empty picture, an example slide."""
    found = [v for p in pool if p.kind == kind and (v := _holding(p, shape.entries))]
    if not found:
        return None

    def short(v: _Variant) -> bool:
        return v.room is not None and v.room < shape.longest

    best = min(found, key=lambda v: (short(v), v.holes, v.layout, -(v.room or 0)))
    shorten = (
        f", shorten each entry to {capacity_text(best.room or 1, 1)}"
        if short(best)
        else ""
    )
    return f"{kind} holds {best.hint}{shorten}"


def _suggested(
    slides: List[_Slide],
    kind: str,
    pool: List[Pattern],
    budget: Dict[str, int],
    given: Dict[str, int],
) -> List[str]:
    """Per slide, one other kind its content suits, the least suggested so far,
    while the template has a variant of it left; slides with the same advice share a line."""
    found: Dict[Tuple[str, str], List[int]] = {}
    for slide in slides:
        # A chart's data has one natural form: never recast into another kind.
        shape = content_shape(slide.plan) if _chart(slide.plan) is None else None
        if shape is None:
            continue
        blocked = _same_problem(slide)
        holds = [p for p in pool if p.id not in blocked]
        options = [
            (k, a)
            for k in shape.kinds
            if k != kind and budget.get(k, 0) > 0 and (a := _advice(holds, k, shape))
        ]
        if not options:
            continue
        chosen, advice = min(options, key=lambda o: given.get(o[0], 0))
        budget[chosen] -= 1
        given[chosen] = given.get(chosen, 0) + 1
        found.setdefault((shape.why, advice), []).append(slide.index)
    return [
        f"slide{'s' if len(at) > 1 else ''} {', '.join(map(str, at))} ({why}) → {advice}"
        for (why, advice), at in found.items()
    ]


def _wanted(slide: _Slide) -> Optional[str]:
    """The kind asked for the slide, or the one its content suggests first."""
    return slide.tiers[0][0] if slide.tiers and slide.tiers[0] else slide.plan.kind


def _repeats(
    slides: List[_Slide],
    chosen: Dict[int, Pattern],
    pool: List[Pattern],
    by_kind: bool,
    caps: Optional[_Caps],
) -> List[Repeat]:
    """Template slides (or, ``by_kind``, content kinds) on more slides than
    their cap, or on three slides or more without caps. Structural slides
    count apart; a kind is offered only while the template has more variants
    of it than the deck already uses."""
    used = {p.id for p in chosen.values()}
    unused = [p for p in pool if p.id not in used]
    variants: Dict[str, set[str]] = {}
    for p in pool:
        variants.setdefault(p.kind, set()).add(zone_summary(p))
    budget = {k: len(v) for k, v in variants.items()}
    for slide in slides:
        if slide.part > 1:
            continue
        k = chosen[slide.index].kind if slide.index in chosen else _wanted(slide)
        if k in budget:
            budget[k] -= 1
    given: Dict[str, int] = {}
    groups: Dict[Tuple[str, str], List[Tuple[_Slide, Pattern]]] = {}
    for slide in slides:
        pattern = chosen.get(slide.index)
        # A design the user asked for is never a reason to ask for variety.
        if pattern is None or slide.part > 1 or slide.plan.asked_design is not None:
            continue
        if not _content(slide, pattern):
            key = ("structural", pattern.id)
        else:
            key = ("kind", pattern.kind) if by_kind else ("slide", pattern.id)
        groups.setdefault(key, []).append((slide, pattern))
    repeats = []
    for (group_by, _), group in groups.items():
        kind = group[0][1].kind
        structural = group_by == "structural"
        # Chart slides may only vary among chart designs.
        recast = not structural and kind != "chart"
        at_most = _NOTE_USES - 1
        if caps is not None and not structural:
            at_most = caps.kind if by_kind else caps.slide
        if len(group) <= at_most:
            continue
        reused = len({p.id for _, p in group}) < len(group)
        # Left out: a variant that has the fit problem of every slide of the group.
        blocked = set.intersection(*(_same_problem(s) for s, _ in group))
        offer = [p for p in unused if p.id not in blocked]
        same = [f"{p.label}: {zone_summary(p)}" for p in offer if p.kind == kind]
        suggested = (
            _suggested([s for s, _ in group], kind, pool, budget, given)
            if recast
            else []
        )
        others = [
            f"'{other}' for {hint}: {p.label}: {zone_summary(p)}"
            for other, hint in SHAPE_HINTS.items()
            if recast
            and other not in _STRUCTURAL
            and other != kind
            and budget.get(other, 0) > 0
            for p in [next((q for q in offer if q.kind == other), None)]
            if p is not None
        ]
        repeats.append(
            Repeat(
                kind,
                [s.index for s, _ in group],
                list(dict.fromkeys(p.label for _, p in group)),
                list(dict.fromkeys(same)) if reused else [],
                others[:_MAX_OTHER_KINDS],
                suggested,
                structural,
                at_most,
            )
        )
    return repeats


def _repeat_note(repeat: Repeat, at: Dict[int, int]) -> str:
    """The passive note: the slides, the variants of their kind left unused,
    and the kinds their content suits."""
    at_text = ", ".join(str(at[n]) for n in repeat.slides)
    if len(repeat.labels) == 1:
        note = f"Slides {at_text} all use the template slide '{repeat.labels[0]}'."
    else:
        note = (
            f"Slides {at_text} are all '{repeat.kind}' slides (template slides "
            + ", ".join(f"'{label}'" for label in repeat.labels)
            + ")."
        )
    if repeat.unused:
        note += (
            f" Unused '{repeat.kind}' variants, to recast one of them: "
            + " | ".join(repeat.unused)
            + "."
        )
    if repeat.suggested:
        note += " Their content suits: " + "; ".join(repeat.suggested) + "."
    if repeat.unused or repeat.suggested:
        return note + " To vary them, recast one as above; otherwise nothing to do."
    return note + " Nothing to do: no other slide of this template suits them."


_PART_TITLE = re.compile(r"^(.*) \((\d+)/(\d+)\)$")


def _rejoin(slides: List[_Slide]) -> None:
    """Parts of a list split by an earlier build, now slides of their own in the
    stored deck: one list again for variety, and never split a second time."""
    for before, slide in zip(slides, slides[1:]):
        a = _PART_TITLE.match(before.plan.title or "")
        b = _PART_TITLE.match(slide.plan.title or "")
        if a and b and (a[1], a[3]) == (b[1], b[3]) and int(b[2]) == int(a[2]) + 1:
            before.part, before.parts = int(a[2]), int(a[3])
            slide.part, slide.parts = int(b[2]), int(b[3])
            slide.start = before.start + _entries(before.plan)


def assign(
    inventory: TemplateInventory,
    plan: DeckPlan,
    variety: VarietyCheck = "template_slide",
    max_uses: int = 2,
) -> Assignment:
    """One pattern per slide of ``plan``, or the problems that prevent it;
    ``variety`` says how repeats are grouped (``off`` groups by kind, for the
    note) and, unless ``off``, ``max_uses`` caps each group."""
    pool = assignable(inventory)
    has_cover = any(p.kind == "cover" for p in pool)
    offered = {p.kind for p in pool}
    size = (inventory.slide_width, inventory.slide_height)
    usable = [
        (index, slide)
        for index, slide in enumerate(plan.slides, start=1)
        if slide.invalid_entry is None
    ]
    slides = [
        _Slide(index, slide, first=n == 0, last=n == len(usable) - 1)
        for n, (index, slide) in enumerate(usable)
    ]
    _rejoin(slides)
    problems: List[SlideProblem] = []
    splits: Dict[int, _Split] = {}
    for slide in slides:
        dropped = _dropped_text(slide.index, slide.plan) or _chart_data(
            slide.index, slide.plan
        )
        if dropped is not None:
            problems.append(dropped)
            continue
        if not has_content(slide.plan) and not (slide.last and "closing" in offered):
            problems.append(
                SlideProblem(
                    slide.index,
                    "the slide is empty",
                    ["remove it", "give it content"],
                    slide.plan.kind,
                )
            )
            continue
        slide.tiers = _tiers(slide, has_cover)
        slide.checked = [(p, *misfit(p, slide.plan, size)) for p in pool]
        if slide.plan.asked_design is not None:
            asked = _asked(slide, has_cover)
            if asked is not None:
                problems.append(asked)
            continue
        slide.candidates = _kept(slide, _candidates(slide, has_cover))
        own_kind = (
            bool(slide.candidates) and slide.candidates[0][0].kind in slide.tiers[0]
        )
        # Its own kind over two slides before a close kind, before a revision.
        split = (
            None
            if own_kind or slide.parts > 1
            else _split(slide, pool, size, has_cover)
        )
        if split is not None:
            splits[slide.index] = split
        elif not slide.candidates:
            slide.closest = _closest(slide, has_cover)
            problems.append(_problem(slide, has_cover, offered))
            # Counted for variety where it lands once fixed: the ask joins this round.
            slide.candidates = _once_fixed(slide, has_cover)
    if not slides:
        return Assignment(problems=problems)
    slides = [
        part
        for slide in slides
        for part in (splits[slide.index].slides if slide.index in splits else [slide])
    ]
    by_kind = variety != "template_slide"
    caps = None if variety == "off" else _caps(slides, pool, max_uses)
    if problems:
        placed = [s for s in slides if s.candidates]
        found = {s.index: p for s, p in zip(placed, _beam(placed, caps)) if s.part == 1}
        return Assignment(
            problems=problems, repeats=_repeats(slides, found, pool, by_kind, caps)
        )

    chosen = _beam(slides, caps)
    patterns: List[Optional[Pattern]] = [None] * len(plan.slides)
    parts: Dict[int, List[Tuple[SlidePlan, Pattern]]] = {}
    for slide, pattern in zip(slides, chosen):
        if slide.index not in splits:
            patterns[slide.index - 1] = pattern
            continue
        if slide.part == 1:
            patterns[slide.index - 1] = pattern
        # Stored as a slide of its own after delivery: its kind keeps it one.
        kind = slide.plan.kind or pattern.kind
        parts.setdefault(slide.index, []).append(
            (slide.plan.model_copy(update={"kind": kind}), pattern)
        )
    # The deck's own numbers: a split list's parts are slides of their own.
    at: Dict[int, int] = {}
    for number, slide in enumerate(slides, start=1):
        at.setdefault(slide.index, number)
    notes = [
        note
        for number, (slide, pattern) in enumerate(zip(slides, chosen), start=1)
        if (note := _substitution(slide, pattern, offered, has_cover, number))
    ]
    notes += [
        f"Slides {i - 1} to {i + 1} use the same template slide: "
        "no other one holds their content. Nothing to do, unless they must look different: "
        "then give one of them another content shape."
        for i in range(2, len(chosen))
        if chosen[i].id == chosen[i - 1].id == chosen[i - 2].id
        and slides[i].part == slides[i - 1].part == 1
    ]
    notes += [_split_note(split, at) for split in splits.values()]
    found = {s.index: p for s, p in zip(slides, chosen) if s.part == 1}
    repeats = _repeats(slides, found, pool, by_kind, caps)
    notes += [_repeat_note(r, at) for r in repeats]
    return Assignment(
        patterns=patterns,
        notes=notes,
        repeats=repeats,
        parts=parts,
        starts=[s.start for s in slides],
    )
