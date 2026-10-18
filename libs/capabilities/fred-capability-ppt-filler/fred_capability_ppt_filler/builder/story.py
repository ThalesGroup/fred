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

"""The one-measure check of a deck plan's charts, run before the assignment
(problems in the assigner's shape join its ``needs_revision``), and the plan
outline shown for validation. Whether a slide makes a point, cites a source or
needs a cover is the model's call (working rules), never refused here.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from fred_capability_ppt_filler.builder import charts
from fred_capability_ppt_filler.builder.assign import SlideProblem
from fred_capability_ppt_filler.builder.plan import (
    XY_TYPES,
    DeckPlan,
    PlanChart,
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
