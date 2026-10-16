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

"""Storytelling checks of a deck plan, run before the assignment: a takeaway
per content slide, one measure per chart, sourced figures. Problems come in the
assigner's shape and join its ``needs_revision``; the speaker notes and the
plan outline are written here too.

The figures spot-check is lenient by design: one figure of a slide relating to
a number the model received is enough, and an ambiguous reading counts as found.
"""

from __future__ import annotations

import json
import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from fred_capability_ppt_filler.builder import charts, lexicon
from fred_capability_ppt_filler.builder.assign import (
    SlideProblem,
    _sequential,
    infer_kinds,
)
from fred_capability_ppt_filler.builder.notes import (
    FIGURES_UNVERIFIED,
    WIDE_RANGE_CHART,
)
from fred_capability_ppt_filler.builder.plan import (
    POINT_AXES,
    XY_TYPES,
    DeckPlan,
    PlanChart,
    SlidePlan,
    read_number,
    shown_charts,
    slide_charts,
)

_TAKEAWAY_MIN_WORDS = 4
_TITLE_FIGURES = 3
_SPREAD = 100.0
# One value axis each; a scatter's or bubble's axes are checked by unit only.
_SPREAD_TYPES = (
    "column",
    "bar",
    "line",
    "area",
    "stacked_column",
    "stacked_bar",
    "radar",
)

# Bounds of the per-call scan: text read from the conversation, distinct numbers
# kept, and derived-value lookups per slide (past it, a figure counts as found).
_MAX_SOURCE_CHARS = 100_000
_MAX_TOTAL_CHARS = 1_500_000
_MAX_NUMBERS = 4_000
_MAX_GROUP = 400
_DERIVED_BUDGET = 20_000

_SCALES = {
    "k": 1e3,
    "m": 1e6,
    "million": 1e6,
    "millions": 1e6,
    "md": 1e9,
    "mds": 1e9,
    "mrd": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "milliard": 1e9,
    "milliards": 1e9,
    "billion": 1e9,
    "billions": 1e9,
}
_TOKEN = re.compile(
    r"(?<![\w.,])[+\-\u2212]?(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*)"
    r"(?:\s?(milliards?|millions?|billions?|mds|md|mrd|bn|[kmb])(?![a-zà-ÿ]))?",
    re.IGNORECASE,
)


# --- numbers ------------------------------------------------------------------------------

Reading = Tuple[float, int]  # value, decimals written


def _readings(digits: str, scale: Optional[str]) -> List[Reading]:
    """Every value a written number may mean: ``1.234`` both ways, a scaled
    figure both as written and scaled (``2,8 M`` → 2.8 and 2 800 000)."""
    digits = re.sub(r"[ \u00a0\u202f]", "", digits)
    seps = [c for c in digits if c in ".,"]
    found: List[Reading] = []
    if not seps:
        found.append((float(digits), 0))
    elif len(set(seps)) > 1 or len(seps) > 1:
        last = max(digits.rfind("."), digits.rfind(","))
        whole = re.sub(r"[.,]", "", digits[:last])
        tail = digits[last + 1 :]
        if len(set(seps)) == 1 and len(tail) == 3:  # 1.234.567
            found.append((float(whole + tail), 0))
        else:
            found.append((float(f"{whole}.{tail}"), len(tail)))
    else:
        head, tail = re.split(r"[.,]", digits)
        found.append((float(f"{head}.{tail}"), len(tail)))
        if len(tail) == 3:  # 1.234 or 1,234: a thousands separator too
            found.append((float(head + tail), 0))
    factor = _SCALES.get((scale or "").lower())
    if factor:
        found += [(v * factor, 0) for v, _ in found]
    return [(abs(v), d) for v, d in found if math.isfinite(v)]


def numbers_in(text: str) -> List[List[Reading]]:
    """The numbers written in ``text``, each with its possible readings."""
    return [_readings(m.group(1), m.group(2)) for m in _TOKEN.finditer(text)]


def _is_year(readings: List[Reading]) -> bool:
    return len(readings) == 1 and readings[0][1] == 0 and 1900 <= readings[0][0] <= 2099


def _decimals(value: float) -> int:
    text = repr(float(value))
    return 0 if text.endswith(".0") or "e" in text else len(text.split(".")[1])


def _unit_scale(unit: Optional[str]) -> Optional[float]:
    match = re.match(r"^\s*([a-z]+)", (unit or "").lower())
    return _SCALES.get(match.group(1)) if match else None


class Found:
    """The numbers the model received, sorted for bisection, and per source
    message or tool result for sums and differences."""

    def __init__(self, groups: List[List[Reading]]) -> None:
        # The latest sources first: past the cap, the oldest numbers go.
        latest = dict.fromkeys(r for g in groups for r in g if r[0] > 0)
        entries = sorted(list(latest)[:_MAX_NUMBERS])
        self.values = [v for v, _ in entries]
        self.decimals = [d for _, d in entries]
        self.groups = [
            sorted({v for v, _ in g if v > 0})[:_MAX_GROUP] for g in groups if g
        ]
        self.budget = _DERIVED_BUDGET

    def _any(self, values: List[float], lo: float, hi: float) -> bool:
        return bisect_right(values, hi) > bisect_left(values, lo)

    def has(self, value: float, decimals: int) -> bool:
        """Equal once rounded to the less precise one's decimals, or within 1 %."""
        reach = max(0.0102 * value, 0.5)
        start = bisect_left(self.values, value - reach)
        for i in range(start, bisect_right(self.values, value + reach)):
            found, found_decimals = self.values[i], self.decimals[i]
            room = 0.5 * 10 ** -min(decimals, found_decimals)
            if abs(found - value) <= max(0.01 * max(found, value), room):
                return True
        return False

    def derived(self, value: float, decimals: int) -> bool:
        """A share or change (as a percentage) of two found numbers, or the sum
        or difference of two numbers of one source; past the budget, found."""
        tolerance = max(0.01 * value, 0.5 * 10**-decimals)
        if value <= 1000:
            for base in self.values:
                self.budget -= 1
                if self.budget < 0:
                    return True
                share = (
                    (value - tolerance) * base / 100,
                    (value + tolerance) * base / 100,
                )
                if self._any(self.values, *share):
                    return True
                for sign in (1, -1):
                    low = base * (1 + sign * (value - tolerance) / 100)
                    high = base * (1 + sign * (value + tolerance) / 100)
                    if self._any(self.values, min(low, high), max(low, high)):
                        return True
        for group in self.groups:
            for first in group:
                self.budget -= 1
                if self.budget < 0:
                    return True
                for other in (value - first, first - value):
                    if other > 0 and self._any(
                        group, other - tolerance, other + tolerance
                    ):
                        return True
        return False


def found_numbers(sources: Sequence[str]) -> Found:
    """Numbers of the user's messages and the tool results, latest first
    within the scan's bounds."""
    groups: List[List[Reading]] = []
    seen: Set[float] = set()
    total = 0
    for text in reversed(sources):
        if total >= _MAX_TOTAL_CHARS or len(seen) >= _MAX_NUMBERS:
            break
        text = text[:_MAX_SOURCE_CHARS]
        total += len(text)
        groups.append([r for readings in numbers_in(text) for r in readings])
        seen.update(v for v, _ in groups[-1])
    return Found(groups)


# --- slide content ----------------------------------------------------------------------


def story_kind(slide: SlidePlan, index: int) -> Optional[str]:
    """The kind the checks treat the slide as: the first slide is the cover;
    a quote is exempt only when asked (bullets without a title infer one)."""
    if index == 1:
        return "cover"
    if slide.kind:
        return slide.kind
    inferred = next(iter(infer_kinds(slide)), None)
    return None if inferred == "quote" else inferred


def _figure_items(slide: SlidePlan) -> List[str]:
    """Item numbers that are figures: not years, not step numbers."""
    numbers = [i.number for i in slide.items if i.number and i.number.strip()]
    if not numbers or all(lexicon.is_year(n) for n in numbers):
        return []
    return [] if _sequential(numbers) else numbers


def _numeric_cells(slide: SlidePlan) -> List[str]:
    if slide.table is None:
        return []
    return [
        cell
        for row in slide.table.rows
        for cell in row
        if read_number(cell)[0] is not None and not lexicon.is_year(cell)
    ]


def has_figures(slide: SlidePlan) -> bool:
    return bool(slide_charts(slide) or _numeric_cells(slide) or _figure_items(slide))


def slide_figures(slide: SlidePlan) -> List[List[Reading]]:
    """Each figure of the slide with its readings; zeros and years left out."""
    figures: List[List[Reading]] = []
    for chart in slide_charts(slide):
        scale = _unit_scale(chart.unit)
        values = [(v, scale) for s in chart.series for v in s.values]
        scales = {
            "x": _unit_scale(chart.x_unit),
            "y": scale,
            "size": _unit_scale(chart.size_unit),
        }
        values += [
            (getattr(p, axis), scales[axis])
            for p in chart.points()
            for axis in POINT_AXES
        ]
        for value, factor in values:
            if value:
                reading = (abs(value), _decimals(value))
                figures.append(
                    [reading] + ([(abs(value) * factor, 0)] if factor else [])
                )
    for text in _numeric_cells(slide) + _figure_items(slide):
        for readings in numbers_in(text):
            if not _is_year(readings) and any(v for v, _ in readings):
                figures.append(readings)
    return figures


def _fmt(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") if value == int(value) else f"{value:g}"


def _quoted(text: str, room: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= room else text[: room - 1] + "…"


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", lexicon.normalize(text)).split())


# --- checks ---------------------------------------------------------------------------------


@dataclass
class Conversation:
    """What the checks read from the messages the model was sent."""

    users: List[str] = field(default_factory=list)
    # User messages and tool results other than the build tool's own.
    sources: List[str] = field(default_factory=list)
    # The build tool's results, for a refusal already given.
    builds: List[str] = field(default_factory=list)
    # A user message follows the last plan proposal.
    answered: bool = False
    _found: Optional[Found] = None

    def numbers(self) -> Found:
        """Read once per conversation, only when a slide needs the spot-check."""
        if self._found is None:
            self._found = found_numbers(self.sources)
        return self._found

    def allows_illustrative(self) -> bool:
        return lexicon.says_any(self.users, lexicon.ILLUSTRATIVE_WORDS)

    def asks_skip_plan(self) -> bool:
        return bool(self.users) and lexicon.says_any(
            self.users[-1:], lexicon.SKIP_PLAN_WORDS
        )


@dataclass
class StoryResult:
    problems: List[SlideProblem] = field(default_factory=list)
    # Per plan index, the soft refusals resent unchanged, now built with a note.
    accepted: Dict[int, List[str]] = field(default_factory=dict)
    # Soft refusals given by this call: a resend of the same is built.
    refused_soft: Set[str] = field(default_factory=set)
    # Whether a problem is not a soft one (the same call is refused again).
    hard: bool = False


def _example(slide: SlidePlan) -> str:
    """A takeaway sketch from the slide's own content."""
    chart = next(iter(slide_charts(slide)), None)
    if chart is not None and chart.series and len(chart.categories) >= 2:
        pairs = [
            (v, c)
            for v, c in zip(chart.series[0].values, chart.categories)
            if v is not None
        ]
        if len(pairs) >= 2:
            (top, first), (_, second) = sorted(pairs, reverse=True)[:2]
            return f"{first} leads with {_fmt(top)}, ahead of {second}, so …"
    subject = slide.title or next(iter(slide.bullets), "") or "this slide"
    return f"{_quoted(subject, 40)}: <what it proves>, so <what follows>"


def _takeaway(slide: SlidePlan) -> List[Tuple[str, str]]:
    text = (slide.takeaway or "").strip()
    sentence = (
        f"a full sentence of what the audience concludes, e.g. '{_example(slide)}'"
    )
    if not text:
        return [("no takeaway", f"add `takeaway`: {sentence}")]
    if len(re.findall(r"\w+", text)) < _TAKEAWAY_MIN_WORDS:
        return [
            (
                f"takeaway '{_quoted(text)}' is a topic, not a conclusion",
                f"rewrite `takeaway` as {sentence}",
            )
        ]
    if text.endswith("?"):
        return [
            (
                f"takeaway '{_quoted(text)}' is a question",
                "write as `takeaway` the answer the slide gives, as a sentence",
            )
        ]
    if slide.title and _plain(slide.title) == _plain(text):
        return [
            (
                "takeaway repeats the title",
                "keep `title` a few words pointing to the point, and write `takeaway` as "
                "the conclusion the audience draws",
            )
        ]
    return []


def _crammed(slide: SlidePlan) -> List[Tuple[str, str]]:
    found = []
    for name in ("title", "subtitle"):
        text = getattr(slide, name) or ""
        figures = [
            m.group(0).strip()
            for m in _TOKEN.finditer(text)
            if not _is_year(_readings(m.group(1), m.group(2)))
        ]
        if len(figures) >= _TITLE_FIGURES:
            found.append(
                (
                    f"the {name} holds {len(figures)} figures ({', '.join(figures)})",
                    f"show them on a figures slide, one item per figure (its number, and "
                    f"what it counts in the field the catalogue lists), and keep the {name} "
                    "short (else a table)",
                )
            )
    return found


def _units(chart: PlanChart) -> List[Tuple[str, str]]:
    if chart.type in XY_TYPES:
        return _axis_units(chart)
    units = sorted(
        {u.strip().lower() for s in chart.series for u in s.units if u.strip()}
    )
    if len(units) < 2:
        return []
    return [
        (
            f"chart mixes units ({', '.join(units)}): a chart shows one measure",
            "show values of different measures on a figures slide, one item per figure; or "
            "keep one measure and set `unit`",
        )
    ]


def _axis_units(chart: PlanChart) -> List[Tuple[str, str]]:
    """A scatter or bubble relates measures, one per axis: each axis one unit."""
    found = []
    for axis, name in (("x", "x_unit"), ("y", "unit"), ("size", "size_unit")):
        units = sorted(
            {
                p.units[axis].strip().lower()
                for p in chart.points()
                if p.units.get(axis, "").strip()
            }
        )
        if len(units) >= 2:
            found.append(
                (
                    f"{axis} values mix units ({', '.join(units)}): a chart axis shows "
                    "one measure",
                    f"write the {axis} values in one unit and set chart.{name}",
                )
            )
    return found


def _spread(chart: PlanChart) -> List[Tuple[str, str]]:
    if chart.type not in _SPREAD_TYPES or (chart.unit or "").strip():
        return []
    values = [abs(v) for s in chart.series for v in s.values if v]
    if len(values) < 2 or max(values) < _SPREAD * min(values):
        return []
    return [
        (
            f"chart values range from {_fmt(min(values))} to {_fmt(max(values))} on one axis "
            "without a unit: do they measure the same thing?",
            "if they do, set chart.unit to that measure (e.g. 'employees'), or send this chart "
            "again unchanged: it is built with a note",
        )
    ]


def _sources(
    slide: SlidePlan, conversation: Conversation
) -> Tuple[List[Tuple[str, str]], Optional[Tuple[str, str]]]:
    """Hard problems, and the soft spot-check refusal."""
    if not has_figures(slide):
        return [], None
    if not (slide.source or "").strip():
        return [
            (
                "no `source` for the slide's figures",
                "set `source`: the document the figures come from, 'user' if the user "
                "typed them, or 'illustrative' only if the user asked for made-up data",
            )
        ], None
    if lexicon.source_kind(slide.source or "") == "illustrative":
        if conversation.allows_illustrative():
            return [], None
        return [
            (
                "the user did not ask for illustrative figures",
                "take the figures from the documents (read or search them) and set "
                "`source` to the document, or end your answer and ask the user for them",
            )
        ], None
    figures = slide_figures(slide)
    if not figures:
        return [], None
    numbers = conversation.numbers()
    numbers.budget = _DERIVED_BUDGET
    if any(numbers.has(v, d) for readings in figures for v, d in readings):
        return [], None
    values = sorted(v for readings in figures for v, _ in readings[:1])
    if len(values) >= 3 and abs(values[-1] - sum(values[:-1])) <= 0.01 * values[-1]:
        return [], None  # the largest is the total of the others
    if any(numbers.derived(v, d) for readings in figures for v, d in readings):
        return [], None
    shown = ", ".join(_fmt(v) for v in values[:6]) + ("…" if len(values) > 6 else "")
    return [], (
        f"none of the slide's figures ({shown}) appears in the documents read or the "
        "user's messages",
        "take the figures from a document (read or search it first) or from the user's "
        "messages; if they are right, send this slide again unchanged: it is built with "
        "a note",
    )


def _seen(problem: str, seen: Set[str], conversation: Conversation) -> bool:
    """A soft refusal already given, this turn or in an earlier build result."""
    if problem in seen:
        return True
    quoted = json.dumps(problem, ensure_ascii=False)[1:-1]
    return any(quoted in text for text in conversation.builds)


def check(
    plan: DeckPlan,
    indices: Sequence[int],
    conversation: Conversation,
    seen: Set[str],
) -> StoryResult:
    """The storytelling problems of the slides at ``indices`` (1-based)."""
    result = StoryResult()
    for index in indices:
        slide = plan.slides[index - 1]
        if slide.invalid_entry is not None:
            continue
        kind = story_kind(slide, index)
        hard = _crammed(slide)
        if kind not in lexicon.TAKEAWAY_EXEMPT_KINDS:
            hard += _takeaway(slide)
        soft: List[Tuple[str, str, str]] = []
        shown = shown_charts(slide)
        for at, chart in shown:
            hard += charts.named(_units(chart), at)
            if len(shown) > 1 and not (chart.title or "").strip():
                hard.append(
                    (
                        f"{at} has no title: with several charts, what does it show?",
                        f"give {at} a title naming its measure ('Revenue by region')",
                    )
                )
            for spread in charts.named(_spread(chart), at):
                soft.append((*spread, WIDE_RANGE_CHART))
        source_problems, unverified = _sources(slide, conversation)
        hard += source_problems
        if unverified is not None:
            soft.append((*unverified, FIGURES_UNVERIFIED))
        refused = []
        for problem, option, code in soft:
            if _seen(problem, seen, conversation):
                result.accepted.setdefault(index, []).append(code)
            else:
                refused.append((problem, option))
                result.refused_soft.add(problem)
        listed = hard + refused
        if listed:
            result.hard = result.hard or bool(hard)
            result.problems.append(
                SlideProblem(
                    index,
                    "; ".join(p for p, _ in listed),
                    list(dict.fromkeys(o for _, o in listed)),
                    slide.kind,
                )
            )
    return result


def outline(plan: DeckPlan, kinds: Sequence[Optional[str]]) -> str:
    """The plan as the user reviews it: audience, main message, one line per slide."""
    lines = [
        f"Audience: {plan.audience or '—'}",
        f"Main message: {plan.main_message or '—'}",
    ]
    for number, (slide, kind) in enumerate(zip(plan.slides, kinds), start=1):
        if slide.invalid_entry is not None:
            continue
        parts = [
            kind or slide.kind or "—",
            slide.title or "—",
            slide.takeaway or "—",
            slide.source or "—",
        ]
        lines.append(f"{number}. " + " — ".join(_quoted(p, 160) for p in parts))
    return "\n".join(lines)
