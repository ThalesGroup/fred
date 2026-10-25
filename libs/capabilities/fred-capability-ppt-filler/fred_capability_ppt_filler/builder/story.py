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

"""The one-measure check of a deck plan's charts (amounts in k€ and M€ are
first put in one scale, large amounts of the text shortened), run before the assignment
(problems in the assigner's shape join its ``needs_revision``), and the plan
outline shown for validation. Whether a slide makes a point, cites a source or
needs a cover is the model's call (working rules), never refused here.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar

from pydantic import BaseModel

from fred_capability_ppt_filler.builder import charts, notes
from fred_capability_ppt_filler.builder.assign import SlideProblem
from fred_capability_ppt_filler.builder.plan import (
    XY_TYPES,
    DeckPlan,
    PlanChart,
    SlidePlan,
    read_number,
    shown_charts,
)


def _quoted(text: str, room: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= room else text[: room - 1] + "…"


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


# --- scale prefixes of one unit (k€, M€, Md€) ---------------------------------------

_BASES = {"€": "€", "EUR": "€", "$": "$", "USD": "$", "£": "£", "GBP": "£"}
_PREFIXES = {
    **dict.fromkeys(("k", "K"), 1e3),
    "M": 1e6,
    **dict.fromkeys(("Md", "Mds", "Mrd", "Mrds", "B", "bn", "Bn"), 1e9),
}
# English finance writes the symbol first: €m, $bn.
_AFTER_SYMBOL = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "bn": 1e9, "B": 1e9}
_PREFIX_OF = {
    "fr": {1e3: "k", 1e6: "M", 1e9: "Md"},
    "en": {1e3: "k", 1e6: "M", 1e9: "bn"},
}
# A single unit is rescaled only past this: 1 500 € stays as written.
_LARGE = 1e4


def _scale(unit: str) -> Optional[Tuple[str, float]]:
    """``"M€"`` → ``("€", 1e6)``; None for a unit that is no scaled amount."""
    text = re.sub(r"\s", "", unit)
    if text.upper() in _BASES:
        return _BASES[text.upper()], 1.0
    match = re.fullmatch(r"(Mrds?|Mds?|bn|Bn|[kKMB])(€|\$|£|EUR|USD|GBP)?", text)
    if match:
        return _BASES.get((match.group(2) or "").upper(), ""), _PREFIXES[match.group(1)]
    match = re.fullmatch(r"(€|\$|£)(bn|[kKmMB])", text)
    if match:
        return match.group(1), _AFTER_SYMBOL[match.group(2)]
    return None


def _magnitude(amounts: Sequence[float], least: float = 1.0) -> float:
    """The scale that puts the largest amount in [1, 1000): 2 450 000 → 1e6."""
    top = max(map(abs, amounts), default=0.0)
    return max(
        (f for f in (1.0, 1e3, 1e6, 1e9) if f >= least and top >= f), default=least
    )


def rescaled_chart(chart: PlanChart, language: str) -> Optional[PlanChart]:
    """The chart in one scale of its amounts' unit: written in several (500 k€,
    2 M€), or one leaving large figures (1 250 000 €). None when unchanged."""
    if chart.type in XY_TYPES:
        return None
    given = _scale(chart.unit) if chart.unit else None
    scales: Dict[str, Tuple[str, float]] = {}
    for unit in {u for s in chart.series for u in s.units if u.strip()}:
        scale = _scale(unit)
        if scale is None:
            return None
        scales[unit] = scale
    bases = {b for b, _ in scales.values()} | ({given[0]} if given else set())
    factors = {f for _, f in scales.values()}
    if len(bases) != 1:
        return None
    mixed = len(factors) > 1
    amounts: List[Optional[float]] = []
    for series in chart.series:
        units = list(series.units) + [""] * (len(series.values) - len(series.units))
        for value, unit in zip(series.values, units):
            scale = scales.get(unit) or (None if mixed else given)
            if value is not None and scale is None:
                return None  # a bare number beside several scales: no way to tell
            amounts.append(None if value is None or scale is None else value * scale[1])
    known = [a for a in amounts if a is not None]
    current = next(iter(factors)) if factors else given[1] if given else 1.0
    if not mixed and (not known or max(map(abs, known)) / current < _LARGE):
        return None
    if mixed and given:
        target = given[1]
    else:
        target = _magnitude(known)
    if not mixed and target == current:
        return None
    (base,) = bases
    spelled = Counter(u for s in chart.series for u in s.units if u in scales)
    label: Optional[str] = next(
        (u for u, _ in spelled.most_common() if scales[u][1] == target),
        (_PREFIX_OF["fr" if language == "fr" else "en"].get(target, "") + base) or None,
    )
    if given and given[1] == target:
        label = chart.unit
    values = iter(None if a is None else round(a / target, 9) for a in amounts)
    series = [
        s.model_copy(
            update={
                "values": [next(values) for _ in s.values],
                "units": [label or "" for _ in s.values],
            }
        )
        for s in chart.series
    ]
    return chart.model_copy(update={"series": series, "unit": label})


# A large amount written in text, its currency after (1 250 000 €) or before
# ($1,250,000); "450 k€" or "$500k" already carry a scale and do not match.
_FIGURE = r"\d{1,3}(?:[ \u00a0\u202f,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_TEXT_AMOUNT = re.compile(
    rf"(?<![\d.,])(?:(?P<after>{_FIGURE})(?P<space>[ \u00a0\u202f]?)(?P<sign>[€$£])"
    rf"|(?P<lead>[€$£])(?P<before>{_FIGURE})(?![\d.,]|\s?(?:bn|Md|[kKmMB])(?![^\W\d_])))"
)
_Model = TypeVar("_Model", bound=BaseModel)


def rescaled_text(text: str, language: str) -> str:
    """Amounts of ``text`` past `_LARGE` in the scale that keeps them short:
    ``520 000 €`` → ``520 k€``, ``$1,250,000`` → ``$1.25M``."""
    mark = "," if language == "fr" else "."

    def amount(match: re.Match[str]) -> str:
        value, _ = read_number(match["after"] or match["before"], mark)
        if value is None or abs(value) < _LARGE:
            return match.group()
        target = _magnitude([value], 1e3)
        shown = f"{round(value / target, 2):g}".replace(".", mark)
        prefix = _PREFIX_OF["fr" if language == "fr" else "en"][target]
        if match["after"]:
            return f"{shown}{match['space']}{prefix}{match['sign']}"
        return f"{match['lead']}{shown}{prefix}"

    return _TEXT_AMOUNT.sub(amount, text)


def _rewritten(
    model: _Model, names: Sequence[str], text: Callable[[str], str]
) -> _Model:
    """``model`` with the text of its fields ``names`` rewritten; itself when unchanged."""

    def deep(value: Any) -> Any:
        if isinstance(value, str):
            return text(value)
        return [deep(v) for v in value] if isinstance(value, list) else value

    update = {n: deep(getattr(model, n)) for n in names}
    update = {n: v for n, v in update.items() if v != getattr(model, n)}
    return model.model_copy(update=update) if update else model


def _slide_text(slide: SlidePlan, language: str) -> SlidePlan:
    def text(value: str) -> str:
        return rescaled_text(value, language)

    slide = _rewritten(
        slide, ("title", "subtitle", "takeaway", "number", "bullets"), text
    )
    update: Dict[str, Any] = {}
    columns = [_rewritten(c, ("heading", "bullets"), text) for c in slide.columns]
    if any(n is not c for n, c in zip(columns, slide.columns)):
        update["columns"] = columns
    names = ("number", "heading", "text", "label")
    items = [_rewritten(i, names, text) for i in slide.items]
    if any(n is not i for n, i in zip(items, slide.items)):
        update["items"] = items
    if slide.table is not None:
        table = _rewritten(slide.table, ("header", "rows"), text)
        if table is not slide.table:
            update["table"] = table
    return slide.model_copy(update=update) if update else slide


def rescaled(plan: DeckPlan) -> DeckPlan:
    """Every chart of the plan in one scale of its unit (see `rescaled_chart`),
    and every large amount of its text too (see `rescaled_text`)."""
    language = notes.plan_language(plan)

    def slide_of(slide: SlidePlan) -> SlidePlan:
        slide = _slide_text(slide, language)
        update = {}
        if slide.chart is not None:
            chart = rescaled_chart(slide.chart, language)
            if chart is not None:
                update["chart"] = chart
        if slide.charts:
            redone = [rescaled_chart(c, language) for c in slide.charts]
            if any(redone):
                update["charts"] = [n or c for n, c in zip(redone, slide.charts)]
        return slide.model_copy(update=update) if update else slide

    slides = [slide_of(s) for s in plan.slides]
    if all(a is b for a, b in zip(slides, plan.slides)):
        return plan
    return plan.model_copy(update={"slides": slides})


def check(plan: DeckPlan, indices: Sequence[int]) -> List[SlideProblem]:
    """The chart-unit problems of the slides at ``indices`` (1-based)."""
    problems = []
    for index in indices:
        slide = plan.slides[index - 1]
        if slide.invalid_entry is not None:
            continue
        found = [
            problem
            for at, chart in shown_charts(slide)
            for problem in charts.named(_units(chart), at)
        ]
        if found:
            problems.append(
                SlideProblem(
                    index,
                    "; ".join(p for p, _ in found),
                    list(dict.fromkeys(o for _, o in found)),
                    slide.kind,
                )
            )
    return problems


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
