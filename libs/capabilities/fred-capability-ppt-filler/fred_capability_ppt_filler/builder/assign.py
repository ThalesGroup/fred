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

from fred_capability_ppt_filler.builder import charts, lexicon, table_intents
from fred_capability_ppt_filler.builder.models import (
    SLIDE_KINDS,
    Pattern,
    SlideKind,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import (
    DECK_FIELDS,
    ITEM_FIELDS,
    SLIDE_FIELDS,
    DeckPlan,
    PlanItem,
    PlanTable,
    SlidePlan,
    _limit,
    capacity_text,
    chart_headings,
    entries_text,
    group_summary,
    has_content,
    max_entries,
    named_charts,
    shown_charts,
    slide_charts,
    takeaway_aside,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import (
    _assign_group,
    _assign_text,
    _fit,
    _Line,
    _only_names_the_slide,
    _takeaway_zone,
    _unused_item_fields,
    chart_hosts,
    fit_table,
    floor_lines,
    zone_capacity,
)

# Costs of a fitting pattern; lower wins. A kind further down the list costs
# more than any plainness of fit, so content shape decides first.
_KIND_STEP = 10.0
_LAYOUT = 5.0  # an example slide the designer built outranks a bare layout
_EMPTY_ZONE = 1.5  # an unfilled text zone is swept away
_UNUSED_ITEM = 0.5
_SHRUNK = 1.0
_HEADING_LEAD = 1.0  # a heading in bold atop the text: a heading zone reads better
# Per earlier use in the section: above the fit costs, so an unused slide
# of the same kind wins, but below _KIND_STEP until the second reuse.
_REUSE = 8.0
_REPEAT = 3.0  # the same slide twice in a row
_TRIPLE = 1000.0  # three in a row: taken only when nothing else fits
# A `repeat_layout` slide off the previous slide's template slide: taken only
# when that one does not hold its content.
_NOT_REPEATED = 1000.0
# Per content use of a template slide beyond the author's max:
# another variant of the tier wins while one fits.
_OVER_MAX = 100.0
_BEAM = 32
_OR_OTHER_KIND = ", or use another kind"
_NOTE_USES = 3  # the passive note when the variety check is off
# Slides a deck legitimately repeats: never a reason to ask for variety.
_STRUCTURAL = ("cover", "section", "agenda", "closing")
# What a variety ask counts: one template slide, one kind, or nothing.
VarietyCheck = Literal["template_slide", "kind", "off"]
# Told wherever variety is limited or asked: `_sections` and the runs of `_repeats`.
SECTION_RULE = (
    "The limit counts within each section (from one section slide, or agenda part, to the "
    "next): a later section may reuse an earlier one's slides, in any order. Never three "
    "identical slides in a row, unless the user explicitly asked for it (`repeat_layout`)."
)
# What each content kind is for, on its catalogue line.
SHAPE_HINTS: Dict[str, str] = {
    "bullets": "short points with no other shape",
    "two_columns": "two groups of points",
    "comparison": "two options side by side",
    "cards": "parallel items, each 'heading: explanation'",
    "figures": "a few big numbers, each with a short label",
    "process": "ordered steps or a causal chain",
    "timeline": "a dated sequence",
    "team": "people",
    "quote": "one strong sentence",
    "image_text": "a point with its picture",
    "table": "a comparison across criteria, not restated as columns",
    "chart": "numbers compared across categories or over time",
}
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
    suggested: List[str]  # "slides 9, 10 → cards holds … (why)"
    structural: bool = False  # cover/section/agenda/closing slides: never asked
    at_most: int = _NOTE_USES - 1  # the slides this group may hold
    in_a_row: bool = False  # three identical slides or more in a row

    @property
    def revisable(self) -> bool:
        return not self.structural and bool(self.suggested)


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
    # Per 1-based plan index of a `repeat_layout` slide: whether it kept the
    # previous slide's template slide.
    repeated: Dict[int, bool] = field(default_factory=dict)

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
    if slide_charts(slide):
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
    listed = next((line.source for line in lines if not line.heading), "")
    name = _list_name(listed) if listed else what
    count = f"{len(lines)} entries" + (
        " (heading included)" if any(line.heading for line in lines) else ""
    )
    most = max_entries(rows)
    if len(lines) > most:
        held = (
            f"{rows} lines (≈{per_line} chars each)"
            if rows > 1
            else (f"1 line (≈{per_line} chars)")
        )
        return Misfit(
            f"{name}: {count}; this zone holds {held}: at most {entries_text(most)}",
            f"merge {name} into at most {entries_text(most)}{_OR_OTHER_KIND}",
        )
    # Few enough entries, but some wrap: each one-line entry would fit.
    costs = floor_lines(zone, lines, *size)
    worst = max(range(len(lines)), key=lambda i: (costs[i], len(lines[i].text)))
    return Misfit(
        f"{name}: {count} wrap to {sum(costs)} lines; this zone holds {most} "
        f"(longest: {lines[worst].source or name}, {len(lines[worst].text)} chars)",
        f"keep each {name} entry to one line (≈{per_line} chars), or drop entries",
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
_TWO_COLUMNS = ("two_columns", "comparison")


def _no_place(what: str, pattern: Pattern, columns: int = 0) -> Misfit:
    """``columns``: the columns a two-column design takes, when none were sent."""
    option = f"drop {what}"
    if what == "chart":
        option = "give the chart a slide of its own (title and chart)"
    elif what == "charts":
        option = "give the charts a slide of their own (title and charts)"
    elif what == "title":
        option = "use another kind: this design shows no title"
    if what == "bullets" and columns:
        option = (
            f"give the points as `columns` [{{heading, bullets}}], at most {columns}"
        )
    elif what == "bullets" and pattern.groups:
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
    reasons, cost, _ = _weigh(pattern, slide, size)
    return reasons, cost


def _weigh(
    pattern: Pattern, slide: SlidePlan, size: Tuple[int, int]
) -> Tuple[List[Misfit], float, int]:
    """``misfit``, with the zones a fitting pattern leaves unfilled."""
    if not pattern.fillable:
        if not has_content(slide) or _only_names_the_slide(slide, pattern):
            return [], 0.0, 0
        return (
            [
                Misfit(
                    "this slide is shown as is and takes no content",
                    f"send only the title '{pattern.label}'",
                )
            ],
            0.0,
            0,
        )
    reasons: List[Misfit] = []
    lost: List[str] = []
    text = _assign_text(pattern, slide, lost, size)
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
    figures = pattern.kind == "figures"
    lost.extend(_unused_item_fields(pattern.groups, slide, size, figures))
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
    shown = shown_charts(slide)
    hosts = chart_hosts(pattern, text) if shown else []
    frames = sum(1 for z in pattern.zones if z.role == "chart")
    if shown and not hosts:
        lost.append("charts" if slide.charts else "chart")
    elif shown and len(hosts) != len(shown):
        reasons.append(_chart_count(len(shown), len(hosts)))
    elif shown:
        headings = chart_headings(pattern)
        for host, (at, chart) in zip(hosts, shown):
            # A title shown in the heading box above is measured as its text.
            drawn = (
                chart.model_copy(update={"title": None})
                if host.key in headings
                else chart
            )
            problems = charts.named(charts.fit_problems(host, drawn, size), at)
            reasons.extend(Misfit(*p) for p in problems)
    elif frames > 1:
        reasons.append(
            Misfit(
                f"this slide shows {frames} charts and needs `charts` with {frames}",
                f"give `charts` with {frames} charts, or another kind",
            )
        )
    elif frames:
        reasons.append(
            Misfit(
                "this slide shows a chart and needs `chart` {type, categories, series}",
                "give the content as `chart`, or another kind",
            )
        )
    aside = takeaway_aside(pattern)
    bodies = sum(z.role == "body" and z not in aside for z in pattern.zones)
    columns = 0 if slide.columns or pattern.kind not in _TWO_COLUMNS else bodies
    reasons[:0] = [
        _no_place(what, pattern, columns) for what in lost if what not in held
    ]

    # A picture zone left empty shows its frame or leaves a hole: it needs a picture.
    unpictured = image_zones > len(images)
    zones = {z.key: z for z in pattern.zones}
    for key, lines in text.items():
        zone = zones[key]
        cost += _check_zone(
            zone, lines, SLIDE_FIELDS.get(zone.role, "bullets"), size, reasons
        )
    for group in pattern.groups:
        group_text, pictures, used = _assign_group(
            group, slide, size, figures=pattern.kind == "figures"
        )
        unpictured |= any(
            z.role == "image" and not pictures.get(z.key)
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
    if unpictured:
        reasons.append(
            Misfit(
                "images: this design shows a picture the slide does not have, so its "
                "picture area would stay empty",
                f"give a picture from list_images_in_folder for each{_OR_OTHER_KIND}",
            )
        )
    if reasons:
        return reasons, 0.0, 0

    empty = 0
    for zone in pattern.zones:
        if (
            zone.role not in ("keep", "table", "image")
            and zone.key not in text
            and zone not in hosts
        ):
            # A takeaway card swept away leaves its side of the slide blank:
            # it weighs as two, so a slide whose content spans that side wins.
            holes = 2 if zone.takeaway else 1
            empty += holes
            cost += _EMPTY_ZONE * holes
    for group in pattern.groups:
        if not slide.items:
            # No items: the list is removed whole, its zones unfilled like any other.
            holes = sum(len(zones) for zones in group.items)
            empty += holes
            cost += _EMPTY_ZONE * holes
    cost += _UNUSED_ITEM * max(0, capacity - len(slide.items)) if slide.items else 0.0
    if pattern.source == "layout":
        cost += _LAYOUT
    return reasons, cost, empty


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


SINGLE_COLUMNS_FIX = (
    "write columns as a list, one {heading, bullets} per column: "
    '[{"heading": ..., "bullets": [...]}, {"heading": ..., "bullets": [...]}]'
)


def _dropped_text(index: int, slide: SlidePlan) -> Optional[SlideProblem]:
    """Plan text the coercion could not map, or a half-written column or item."""
    found: List[str] = []
    options: List[str] = []
    deck = [f for f in slide.ignored_fields if f.split(" ", 1)[0] in DECK_FIELDS]
    other = [f for f in slide.ignored_fields if f not in deck]
    if deck:
        found.append(f"{', '.join(deck)}: a deck field, not a slide field")
        options.append("send it once, next to `slides`, not inside a slide")
    if other:
        found.append(f"{', '.join(other)}: not a slide field")
        options.append(
            "put that text in title, subtitle, bullets, columns, items or notes"
        )
    lone = (
        ["columns sent as one object, not a list: it cannot tell one column from two"]
        if slide.single_columns
        else []
    )
    if lone:
        options.append(SINGLE_COLUMNS_FIX)
    for n, column in enumerate(slide.columns):
        if column.ignored_fields:
            found.append(
                f"columns[{n}]: {', '.join(column.ignored_fields)} is not a column field"
            )
            options.append("write columns as a list, one {heading, bullets} per column")
    for at, chart in named_charts(slide):
        if chart.ignored_fields:
            found.append(
                f"{at}: {', '.join(chart.ignored_fields)} is not a chart field"
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
    if not found and not halves and not lone:
        return None
    parts = (
        lone
        + (["this text would be lost: " + "; ".join(found)] if found else [])
        + (["incomplete entries: " + "; ".join(halves)] if halves else [])
    )
    if halves:
        options.append("complete each entry, or drop the half-written one")
    return SlideProblem(
        index, "; ".join(parts), list(dict.fromkeys(options)), slide.kind
    )


def _chart_count(given: int, shown: int) -> Misfit:
    sent = "chart: 1 given" if given == 1 else f"charts: {given} given"
    field = "`chart`" if shown == 1 else f"`charts` with {shown} charts"
    return Misfit(
        f"{sent}; this slide shows {shown}", f"give {field}, or use another slide"
    )


def _chart_data(index: int, slide: SlidePlan) -> Optional[SlideProblem]:
    """The charts' data, checked once whatever slide will show them."""
    found: List[Tuple[str, str]] = []
    if slide.chart is not None and slide.charts:
        found.append(
            (
                "both `chart` and `charts` sent",
                "send `chart` for one chart or `charts` for several, not both",
            )
        )
    for at, chart in named_charts(slide):
        found += charts.named(charts.data_problems(chart), at)
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
    # Per pattern id, the zones it leaves unfilled.
    empty: Dict[str, int] = field(default_factory=dict)
    # The pattern ids that show the takeaway the user asked to see.
    shows: set[str] = field(default_factory=set)
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
    design, a kind the template replaced included. Otherwise the fullest fits."""
    shown = _shown(slide, candidates)
    kept = [c for c in shown if c[0].id == slide.plan.built_on]
    return kept or _fullest(slide, candidates)


def _asked(slide: _Slide) -> Optional[SlideProblem]:
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
    if not _allowed(pattern, slide):
        where = "first" if pattern.kind == "cover" else "last"
        return SlideProblem(
            slide.index,
            f"{named} can only be the {where} slide",
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


def _allowed(pattern: Pattern, slide: _Slide) -> bool:
    if pattern.kind == "cover":
        return slide.first
    if pattern.kind == "closing":
        return slide.last
    return True


def _tiers(slide: _Slide, offered: set[str]) -> List[List[SlideKind]]:
    """The requested kind, then its close kinds; with no kind (or one with no
    close kinds), the kinds the content suggests, then any kind. A title slide
    with no kind opening the deck is the cover, as the description states."""
    asked = slide.plan.kind
    if asked and asked in CLOSE_KINDS:
        return [[asked], list(CLOSE_KINDS[asked])]
    inferred = infer_kinds(slide.plan)
    if slide.first and not asked and inferred[0] == "section" and "cover" in offered:
        return [["cover"]]
    tiers: List[List[SlideKind]] = [[asked]] if asked else []
    # A chart has one natural form: a content area only when no chart slide holds it.
    first: List[SlideKind] = (
        [] if asked or not slide_charts(slide.plan) else [inferred[0]]
    )
    if first:
        tiers.append(first)
    tiers.append([k for k in inferred if k != asked and k not in first])
    seen = set(inferred) | {asked}
    tiers.append([k for k in SLIDE_KINDS if k not in seen])
    return tiers


def _close(slide: _Slide) -> Optional[Tuple[SlideKind, ...]]:
    """The close kinds of the requested kind; None when the fallback is open."""
    asked = slide.plan.kind
    return CLOSE_KINDS.get(asked) if asked else None


def _candidates(slide: _Slide) -> List[Tuple[Pattern, float]]:
    for tier in slide.tiers:
        found = [
            (p, cost + _KIND_STEP * tier.index(p.kind))
            for p, reasons, cost in slide.checked
            if not reasons and p.kind in tier and _allowed(p, slide)
        ]
        if found:
            return found
    return []


def _shown(
    slide: _Slide, found: List[Tuple[Pattern, float]]
) -> List[Tuple[Pattern, float]]:
    """Without the fits that cannot show the takeaway the user asked to see
    when one of their kind can."""
    showing = {p.kind for p, _ in found if p.id in slide.shows}
    return [c for c in found if c[0].id in slide.shows or c[0].kind not in showing]


def _fullest(
    slide: _Slide, found: List[Tuple[Pattern, float]]
) -> List[Tuple[Pattern, float]]:
    """Without the fits one of their kind beats on unfilled zones at no higher
    cost, or that cannot show a takeaway the user asked to see when one of
    their kind can: reuse and variety only choose between equally filled slides."""
    shown = _shown(slide, found)
    kept = [
        (p, cost)
        for p, cost in shown
        if not any(
            q.kind == p.kind and slide.empty[q.id] < slide.empty[p.id] and other <= cost
            for q, other in shown
        )
    ]
    return kept


def _check(slide: _Slide, pool: List[Pattern], size: Tuple[int, int]) -> None:
    for p in pool:
        reasons, cost, empty = _weigh(p, slide.plan, size)
        slide.checked.append((p, reasons, cost))
        slide.empty[p.id] = empty
        if _takeaway_zone(p, slide.plan, size) is not None:
            slide.shows.add(p.id)


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
                header=table.header,
                rows=rows[start : start + size],
                total_row=table.total_row and k == count,
                highlight_row=table_intents.part_row(table, start, size, k == 1),
                highlight_column=table.highlight_column,
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
    slide: _Slide, pool: List[Pattern], size: Tuple[int, int]
) -> Optional[_Split]:
    """The slide's list over at most ``_MAX_PARTS`` slides of its own kind (the
    requested one, or the first inferred one that holds it), when its entry
    count alone keeps it off that kind; None otherwise. Bullets never split."""
    plan, entries = slide.plan, _entries(slide.plan)
    if entries < 2:
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
            _check(part, mine, size)
            part.candidates = _fullest(
                part,
                [
                    (p, cost)
                    for p, reasons, cost in part.checked
                    if not reasons and _allowed(p, part)
                ],
            )
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


def _own(slide: _Slide) -> List[Tuple[Pattern, List[Misfit]]]:
    """Patterns the position allows, of a kind the slide's tiers rank."""
    kinds = {k for tier in slide.tiers for k in tier}
    return [
        (p, r) for p, r, _ in slide.checked if p.kind in kinds and _allowed(p, slide)
    ]


def _tableless(slide: _Slide) -> bool:
    table = slide.plan.table
    return (
        table is not None
        and table.has_content()
        and not any(z.role == "table" for p, _, _ in slide.checked for z in p.zones)
    )


def _chart_counts(slide: _Slide) -> List[int]:
    """How many charts the template's slides hold, one count per slide."""
    found = {len(chart_hosts(p, ())) for p, _, _ in slide.checked}
    return sorted(found - {0})


def _chartless(slide: _Slide) -> bool:
    """No template slide holds as many charts as the slide has."""
    given = len(slide_charts(slide.plan))
    return bool(given) and given not in _chart_counts(slide)


def _or(counts: Sequence[int]) -> str:
    words = [str(c) for c in counts]
    return ", ".join(words[:-1]) + " or " + words[-1] if len(words) > 1 else words[0]


def _chartless_problem(slide: _Slide) -> SlideProblem:
    """No slide for this many charts: the counts offered and how to reach one."""
    given, counts = len(slide_charts(slide.plan)), _chart_counts(slide)
    if not counts:
        problem = "chart: this template has no slide for a chart"
    elif given == 1:
        problem = (
            f"chart: this template has no slide for one chart, only for {_or(counts)}"
        )
    else:
        problem = (
            f"charts: {given} given; this template offers slides with {_or(counts)} "
            "charts"
        )
    options = []
    if given > 1 and counts:
        options.append(
            f"split the slide into slides of {_or(counts)} charts (one chart per "
            "measure), each with its own title"
        )
        fewer = [c for c in counts if c < given]
        if fewer:
            options.append(f"or merge or drop charts to send {_or(fewer)}")
    return SlideProblem(
        slide.index,
        problem,
        options if given > 1 else _chart_options(slide),
        slide.plan.kind,
    )


def _chart_options(slide: _Slide) -> List[str]:
    """What the chart's data can become on this template, best first."""
    shown = slide_charts(slide.plan)
    chart = shown[0] if shown else None
    kinds = {p.kind for p, _, _ in slide.checked}
    options = []
    if "table" in kinds:
        options.append(
            "give the data as `table` (a row per category, a column per series)"
        )
    values = len(chart.categories) * len(chart.series) if chart is not None else 0
    most = max(
        (g.count for p, _, _ in slide.checked if p.kind == "figures" for g in p.groups),
        default=0,
    )
    if most and values <= most:
        options.append(
            f"give the {values} values as items of a 'figures' slide "
            "(number: the value, label: the category)"
        )
    options.append("keep the key numbers as bullets")
    return options


def _closest(slide: _Slide) -> Optional[Tuple[Pattern, List[Misfit]]]:
    """The kind closest to the content, then fewest problems, then the roomiest;
    None when no slide can take the position or a table must be rewritten."""
    # The asked kind (or, with none, the inferred kinds) ranks first: the advice
    # should be about that shape, not about an unrelated kind that happens to fit.
    rank = {k: 0 for tier in slide.tiers[:-1] for k in tier}
    rank.update({k: 1 for k in slide.tiers[-1]})
    own = _own(slide)
    if not own or _tableless(slide) or _chartless(slide):
        return None
    # A chart's advice is about a slide that can show as many.
    given = len(slide_charts(slide.plan))
    return min(
        own,
        key=lambda pr: (
            rank[pr[0].kind],
            bool(given) and len([z for z in pr[0].zones if z.role == "chart"]) != given,
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


def _once_fixed(slide: _Slide) -> List[Tuple[Pattern, float]]:
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
        and _allowed(p, slide)
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


def _problem(slide: _Slide, offered: set[str]) -> SlideProblem:
    """The closest pattern's misfits, named down to the element, with fixes."""
    own = _own(slide)
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
        return _chartless_problem(slide)
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
        lead = "closest fit"
        if close is not None and closest.kind != asked:
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
    return SlideProblem(
        slide.index, problem, list(dict.fromkeys(options)), slide.plan.kind
    )


def _close_options(
    slide: _Slide, own: List[Tuple[Pattern, List[Misfit]]], named: str
) -> List[str]:
    """The close kinds the template offers here, each with what it takes."""
    found = []
    for kind in _close(slide) or ():
        mine = [
            pr
            for pr in own
            if pr[0].kind == kind and not _wants_picture(pr[0], [slide.plan])
        ]
        if kind != named and mine:
            best = min(mine, key=_fewest)[0]
            found.append(
                f"or rewrite it as kind '{kind}', which takes: {zone_summary(best)}"
            )
    return found[:_MAX_KIND_OPTIONS]


def _substitution(
    slide: _Slide, chosen: Pattern, offered: set[str], number: int
) -> Optional[str]:
    """What was built instead of the requested kind, why, and the edit that
    would give the requested kind."""
    # A chart in a content area is a substitution even when no kind was asked.
    asked = slide.plan.kind or ("chart" if slide_charts(slide.plan) else None)
    if not asked or chosen.kind == asked:
        return None
    head = f"Slide {number}: built as '{chosen.kind}' instead of '{asked}'"
    if asked == "chart" and chosen.kind != "chart":
        head += ", the chart in its content area"
    why = _why_not(slide, offered, asked)
    if why is not None:
        if asked == "closing" and not slide.last:
            remedy = "To make it the closing slide, move it to the end."
        elif asked == "cover" and not slide.first:
            remedy = "To make it the cover, move it to the start."
        else:
            remedy = "Nothing to do."
        return f"{head}: {why}. {remedy}"
    mine = [
        (p, r) for p, r, _ in slide.checked if p.kind == asked and _allowed(p, slide)
    ]
    if not mine:  # pragma: no cover - _why_not covers every absent kind
        return f"{head}. Nothing to do."
    _, reasons = min(mine, key=_fewest)
    # It already is another kind: only the fix is left to say, never an exit.
    fixes = list(
        dict.fromkeys(
            r.option.removesuffix(_OR_OTHER_KIND) for r in reasons if r.option
        )
    )
    remedy = (
        f"To get the '{asked}' slide, call again and {'; '.join(fixes)}."
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


def _exempt(slide: _Slide) -> bool:
    """Asked by the user to look like another slide: outside the variety limits."""
    return slide.plan.asked_design is not None or slide.plan.repeat_layout


def _caps(
    slides: List[_Slide],
    pool: List[Pattern],
    max_uses: int,
    sections: Optional[Dict[int, int]] = None,
) -> _Caps:
    """The author's max, raised to what the largest section forces."""
    per: Dict[int, int] = {}
    for s in slides:
        if s.candidates and _content(s) and s.part == 1:
            at = (sections or {}).get(s.index, 0)
            per[at] = per.get(at, 0) + 1
    content = max(per.values(), default=0)
    designs = {p.design_key: p.kind for p in pool if p.kind not in _STRUCTURAL}

    def cap(distinct: int) -> int:
        return max(max_uses, math.ceil(content / distinct)) if distinct else max_uses

    return _Caps(cap(len(designs)), cap(len(set(designs.values()))))


_NUMBERED = re.compile(r"^\s*\d+\s*[.)\-:]?\s+")


def _entry(text: str) -> str:
    """An agenda entry or a title, compared without its number or case."""
    return " ".join(_NUMBERED.sub("", text).casefold().split()).strip(" .:;-")


def _sections(slides: List[_Slide]) -> Dict[int, int]:
    """Per slide (plan index), its section: one starts at each `section` slide
    or, with none, at a content slide titled as an agenda entry; slides before
    the first are a section of their own. Empty unless the deck has two."""
    split = any(_wanted(s) == "section" for s in slides)
    entries: set[str] = set()
    for s in slides:
        if not split and _wanted(s) == "agenda":
            texts = list(s.plan.bullets) + [i.heading or i.text for i in s.plan.items]
            entries |= {_entry(t) for t in texts if t} - {""}
    found: Dict[int, int] = {}
    section = 0
    for s in slides:
        if s.part == 1 and (
            _wanted(s) == "section"
            or (entries and _content(s) and _entry(s.plan.title or "") in entries)
        ):
            section += 1
        found[s.index] = section
    return found if section > 1 else {}


def _wants_picture(pattern: Pattern, plans: Sequence[SlidePlan]) -> bool:
    """The pattern needs a picture none of ``plans`` has: never offered to
    recast them, as the model cannot invent one."""
    zones = pattern.zones + [
        z for g in pattern.groups for item in g.items for z in item
    ]
    return any(z.role == "image" for z in zones) and not any(
        p.image or p.images or any(i.image for i in p.items) for p in plans
    )


@dataclass
class _Path:
    cost: float
    chosen: Tuple[int, ...]  # candidate index per slide so far
    uses: Dict[str, int]
    content: Dict[str, int]  # uses by content slides, priced against the caps


def _beam(
    slides: List[_Slide],
    caps: Optional[_Caps] = None,
    sections: Optional[Dict[int, int]] = None,
) -> List[Pattern]:
    """Cheapest pattern sequence under a per-section reuse cost. The use counts
    make the cost non-local, so a bounded beam replaces exact dynamic
    programming; paths with the same last two choices and uses are merged."""
    at = sections or {}
    structural = {
        p.design_key for s in slides for p, _ in s.candidates if p.kind in _STRUCTURAL
    }
    paths = [_Path(0.0, (), {}, {})]
    for i, slide in enumerate(slides):
        if i and at.get(slide.index) != at.get(slides[i - 1].index):
            # A new section counts its content slides from zero.
            for path in paths:
                path.uses = {k: v for k, v in path.uses.items() if k in structural}
                path.content = {}
        free = _exempt(slide)
        steps: List[Tuple[float, int, int]] = []
        for n, path in enumerate(paths):
            last_pattern = slides[i - 1].candidates[path.chosen[-1]][0] if i else None
            last = last_pattern.design_key if last_pattern else None
            before = (
                slides[i - 2].candidates[path.chosen[-2]][0].design_key
                if i >= 2
                else None
            )
            # Asked to keep the previous slide's layout, and its content fits it.
            keep = slide.plan.repeat_layout and any(
                p.design_key == last for p, _ in slide.candidates
            )
            for c, (pattern, cost) in enumerate(slide.candidates):
                design = pattern.design_key
                step = path.cost + cost + _REUSE * path.uses.get(design, 0)
                if slide.part > 1:
                    # A list's continuation: its first part's slide again is free.
                    if last_pattern is None or pattern.id != last_pattern.id:
                        step += _SPLIT_SWITCH
                    else:
                        step = path.cost + cost
                elif keep:
                    step += 0.0 if design == last else _NOT_REPEATED
                elif design == last:
                    step += _REPEAT + (_TRIPLE if design == before else 0.0)
                if (
                    caps is not None
                    and slide.part == 1
                    and not free
                    and _content(slide, pattern)
                    and path.content.get(design, 0) >= caps.slide
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
            # A split list counts as one slide, a slide asked alike not against the cap.
            design = pattern.design_key
            if slide.part == 1:
                uses[design] = uses.get(design, 0) + 1
            if slide.part == 1 and not free and _content(slide, pattern):
                content[design] = content.get(design, 0) + 1
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
        hint = f"exactly 2 columns [{heading}bullets{_limit(bodies, True)}]"
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
        shape = None if slide_charts(slide.plan) else content_shape(slide.plan)
        if shape is None:
            continue
        blocked = _same_problem(slide)
        holds = [
            p
            for p in pool
            if p.id not in blocked and not _wants_picture(p, [slide.plan])
        ]
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


def _runs(
    slides: List[_Slide], chosen: Dict[int, Pattern]
) -> List[List[Tuple[_Slide, Pattern]]]:
    """Three identical content template slides or more in a row. A slide asked
    to look alike starts a new run, so it never ends one; a split part breaks it."""
    runs: List[List[Tuple[_Slide, Pattern]]] = []
    run: List[Tuple[_Slide, Pattern]] = []
    for slide in slides:
        pattern = chosen.get(slide.index) if slide.part == 1 else None
        if pattern is None or not _content(slide, pattern):
            run = []
        elif run and run[-1][1].design_key == pattern.design_key and not _exempt(slide):
            run.append((slide, pattern))
            if len(run) == 3:
                runs.append(run)  # the same list: later slides of the run join it
        else:
            run = [(slide, pattern)]
    return runs


def _budget(
    slides: List[_Slide], chosen: Dict[int, Pattern], variants: Dict[str, set[str]]
) -> Dict[str, int]:
    """Per kind, the variants ``slides`` leave unused: what may still be suggested."""
    budget = {k: len(v) for k, v in variants.items()}
    for slide in slides:
        k = chosen[slide.index].kind if slide.index in chosen else _wanted(slide)
        if k in budget:
            budget[k] -= 1
    return budget


def _repeats(
    slides: List[_Slide],
    chosen: Dict[int, Pattern],
    pool: List[Pattern],
    by_kind: bool,
    caps: Optional[_Caps],
    sections: Optional[Dict[int, int]] = None,
) -> List[Repeat]:
    """Template slides (or, ``by_kind``, content kinds) on more slides of one
    section than their cap, or on three slides or more without caps; with caps,
    also three identical template slides in a row. Slides asked alike are left
    out; structural slides count apart, deck-wide. Alternatives are read from
    the sections concerned. Full rule: design.md D27."""
    at = sections or {}
    named: Dict[str, str] = {}
    variants: Dict[str, set[str]] = {}
    for p in pool:
        named.setdefault(p.design_key, p.label)
        variants.setdefault(p.kind, set()).add(zone_summary(p))
    groups: Dict[Tuple[str, int, str], List[Tuple[_Slide, Pattern]]] = {}
    for slide in slides:
        pattern = chosen.get(slide.index)
        if pattern is None or slide.part > 1 or _exempt(slide):
            continue
        if not _content(slide, pattern):
            key = ("structural", 0, pattern.design_key)
        elif by_kind:
            key = ("kind", at.get(slide.index, 0), pattern.kind)
        else:
            key = ("slide", at.get(slide.index, 0), pattern.design_key)
        groups.setdefault(key, []).append((slide, pattern))
    found = [(key[0] == "structural", False, g) for key, g in groups.items()]
    if caps is not None:
        found += [(False, True, run) for run in _runs(slides, chosen)]
    budgets: Dict[frozenset, Dict[str, int]] = {}
    given: Dict[str, int] = {}
    repeats: List[Repeat] = []
    # A run already listed as over its cap is asked once.
    listed: set[int] = set()
    for structural, in_a_row, group in found:
        kind = group[0][1].kind
        # Chart slides may only vary among chart designs.
        recast = not structural and kind != "chart"
        at_most = _NOTE_USES - 1
        if caps is not None and not structural and not in_a_row:
            at_most = caps.kind if by_kind else caps.slide
        if not in_a_row and len(group) <= at_most:
            continue
        if in_a_row and {s.index for s, _ in group} <= listed:
            continue
        if not structural:
            listed |= {s.index for s, _ in group}
        scope = {at.get(s.index, 0) for s, _ in group}
        within = [
            s
            for s in slides
            if s.part == 1 and (structural or at.get(s.index, 0) in scope)
        ]
        budget = budgets.setdefault(
            frozenset(at.get(s.index, 0) for s in within),
            _budget(within, chosen, variants),
        )
        suggested = (
            _suggested([s for s, _ in group], kind, pool, budget, given)
            if recast
            else []
        )
        repeats.append(
            Repeat(
                kind,
                [s.index for s, _ in group],
                list(dict.fromkeys(named.get(p.design_key, p.label) for _, p in group)),
                suggested,
                structural,
                at_most,
                in_a_row,
            )
        )
    return repeats


def _repeat_note(repeat: Repeat, at: Dict[int, int]) -> str:
    """The passive note: the slides and the kinds their content suits."""
    at_text = ", ".join(str(at[n]) for n in repeat.slides)
    if repeat.in_a_row:
        note = f"Slides {at_text} use the template slide '{repeat.labels[0]}' in a row."
    elif len(repeat.labels) == 1:
        note = f"Slides {at_text} all use the template slide '{repeat.labels[0]}'."
    else:
        note = (
            f"Slides {at_text} are all '{repeat.kind}' slides (template slides "
            + ", ".join(f"'{label}'" for label in repeat.labels)
            + ")."
        )
    if repeat.suggested:
        note += " Their content suits: " + "; ".join(repeat.suggested) + "."
        return note + " To vary them, recast one as above; otherwise nothing to do."
    return note + " Nothing to do: no other slide of this template suits them."


def _repeated_note(number: int, kept: bool) -> str:
    """Never silent: a slide built alike on the user's word, or one that could not be."""
    if kept:
        return (
            f"Slide {number} keeps slide {number - 1}'s template slide, as the user asked "
            "(`repeat_layout`): left out of the variety limits."
        )
    return (
        f"Slide {number} has `repeat_layout`, but its content does not fit slide "
        f"{number - 1}'s template slide, so it was built on another one. To keep that "
        f"layout, shape its content like slide {number - 1}'s."
    )


_PART_TITLE = re.compile(r"^(.*) \((\d+)/(\d+)\)$")


def renumber_parts(plan: DeckPlan) -> DeckPlan:
    """The "(k/n)" of a list split by an earlier build, recounted on the deck as
    it now stands: a part left alone (moved, removed, a slide put between) drops it."""
    slides = list(plan.slides)
    runs: List[List[int]] = []
    for i, slide in enumerate(slides):
        found = _PART_TITLE.match(slide.title or "") if slide.built_on else None
        if found is None or int(found[3]) > _MAX_PARTS:
            continue
        before = _PART_TITLE.match(slides[i - 1].title or "") if i else None
        if runs and runs[-1][-1] == i - 1 and before and before[1] == found[1]:
            runs[-1].append(i)
        else:
            runs.append([i])
    for run in runs:
        name = _PART_TITLE.match(slides[run[0]].title or "")[1]  # type: ignore[index]
        for k, i in enumerate(run, start=1):
            title = f"{name} ({k}/{len(run)})" if len(run) > 1 else name
            if title != slides[i].title:
                slides[i] = slides[i].model_copy(update={"title": title})
    return plan.model_copy(update={"slides": slides})


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
        slide.tiers = _tiers(slide, offered)
        _check(slide, pool, size)
        if slide.plan.asked_design is not None:
            asked = _asked(slide)
            if asked is not None:
                problems.append(asked)
            continue
        slide.candidates = _kept(slide, _candidates(slide))
        own_kind = (
            bool(slide.candidates) and slide.candidates[0][0].kind in slide.tiers[0]
        )
        # Its own kind over two slides before a close kind, before a revision.
        split = None if own_kind or slide.parts > 1 else _split(slide, pool, size)
        if split is not None:
            splits[slide.index] = split
        elif not slide.candidates:
            slide.closest = _closest(slide)
            problems.append(_problem(slide, offered))
            # Counted for variety where it lands once fixed: the ask joins this round.
            slide.candidates = _once_fixed(slide)
    if not slides:
        return Assignment(problems=problems)
    slides = [
        part
        for slide in slides
        for part in (splits[slide.index].slides if slide.index in splits else [slide])
    ]
    by_kind = variety != "template_slide"
    # Sections only shape a limit: with the check off, the deck is one.
    sections = {} if variety == "off" else _sections(slides)
    caps = None if variety == "off" else _caps(slides, pool, max_uses, sections)
    if problems:
        placed = [s for s in slides if s.candidates]
        found = {
            s.index: p
            for s, p in zip(placed, _beam(placed, caps, sections))
            if s.part == 1
        }
        return Assignment(
            problems=problems,
            repeats=_repeats(slides, found, pool, by_kind, caps, sections),
        )

    chosen = _beam(slides, caps, sections)
    patterns: List[Optional[Pattern]] = [None] * len(plan.slides)
    parts: Dict[int, List[Tuple[SlidePlan, Pattern]]] = {}
    for slide, pattern in zip(slides, chosen):
        if slide.index not in splits:
            patterns[slide.index - 1] = pattern
            continue
        if slide.part == 1:
            patterns[slide.index - 1] = pattern
        # Stored as a slide of its own after delivery: its kind keeps it one,
        # and only its first part keeps the slide before it.
        kind = slide.plan.kind or pattern.kind
        first = slide.plan.repeat_layout and slide.part == 1
        parts.setdefault(slide.index, []).append(
            (
                slide.plan.model_copy(update={"kind": kind, "repeat_layout": first}),
                pattern,
            )
        )
    # The deck's own numbers: a split list's parts are slides of their own.
    at: Dict[int, int] = {}
    for number, slide in enumerate(slides, start=1):
        at.setdefault(slide.index, number)
    notes = [
        note
        for number, (slide, pattern) in enumerate(zip(slides, chosen), start=1)
        if (note := _substitution(slide, pattern, offered, number))
    ]
    # With a limit, a run is a repeat and noted as one.
    notes += [
        f"Slides {i - 1} to {i + 1} use the same template slide: "
        "no other one holds their content. Nothing to do, unless they must look different: "
        "then give one of them another content shape."
        for i in range(2, len(chosen))
        if caps is None
        and chosen[i].design_key == chosen[i - 1].design_key == chosen[i - 2].design_key
        and slides[i].part == slides[i - 1].part == 1
        and not _exempt(slides[i])
    ]
    repeated = {
        slide.index: chosen[k].design_key == chosen[k - 1].design_key
        for k, slide in enumerate(slides)
        if k and slide.part == 1 and slide.plan.repeat_layout
    }
    notes += [_repeated_note(at[n], kept) for n, kept in repeated.items()]
    notes += [_split_note(split, at) for split in splits.values()]
    found = {s.index: p for s, p in zip(slides, chosen) if s.part == 1}
    repeats = _repeats(slides, found, pool, by_kind, caps, sections)
    notes += [_repeat_note(r, at) for r in repeats]
    return Assignment(
        patterns=patterns,
        notes=notes,
        repeats=repeats,
        parts=parts,
        starts=[s.start for s in slides],
        repeated=repeated,
    )
