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

A slide's candidates are the patterns of its kind (given, else inferred from its
content) that hold all of its content; a second-order Viterbi pass picks one per
slide under the deck rules. A slide with no candidate is a problem the model
must fix: nothing is ever substituted (design.md D7, D8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fred_capability_ppt_filler.builder import lexicon
from fred_capability_ppt_filler.builder.models import (
    Pattern,
    SlideKind,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.plan import (
    ITEM_FIELDS,
    SLIDE_FIELDS,
    DeckPlan,
    SlidePlan,
    has_content,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import (
    _assign_group,
    _assign_text,
    _fit,
    _Line,
    _only_names_the_slide,
    _unused_item_fields,
)

# Costs of a fitting pattern; lower wins. A kind further down the inferred list
# costs more than any plainness of fit, so content shape decides first.
_KIND_STEP = 10.0
_LAYOUT = 5.0  # an example slide the designer built outranks a bare layout
_IMAGE_HOLE = 4.0  # an empty picture zone is removed, leaving a gap
_EMPTY_ZONE = 1.5  # an unfilled text zone is swept away
_UNUSED_ITEM = 0.5
_SHRUNK = 1.0
_REPEAT = 3.0  # the same slide twice in a row
_TRIPLE = 1000.0  # three in a row: taken only when nothing else fits

_MAX_KIND_OPTIONS = 3


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
class Assignment:
    # Aligned with the plan's slides; None for an entry that is not a slide.
    patterns: List[Optional[Pattern]] = field(default_factory=list)
    problems: List[SlideProblem] = field(default_factory=list)
    # Repetitions the rules allowed because nothing else fitted.
    notes: List[str] = field(default_factory=list)


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


# --- fit check ----------------------------------------------------------------------------


def _check_zone(
    zone: Zone,
    lines: List[_Line],
    what: str,
    size: Tuple[int, int],
    reasons: List[str],
) -> float:
    if zone.grows or not lines:
        return 0.0
    _, scale, truncated = _fit(zone, lines, size[0], size[1])
    if truncated:
        limit = f" (≤{zone.max_chars} chars)" if zone.max_chars else ""
        reasons.append(f"{what} too long{limit}")
        return 0.0
    return _SHRUNK if scale is not None else 0.0


def misfit(
    pattern: Pattern, slide: SlidePlan, size: Tuple[int, int]
) -> Tuple[List[str], float]:
    """Why ``pattern`` cannot hold all of ``slide`` (empty when it can), and the
    cost of the fit. Uses the renderer's own placement, so a fitting pattern
    loses nothing when rendered."""
    if not pattern.fillable:
        if not has_content(slide) or _only_names_the_slide(slide, pattern):
            return [], 0.0
        return ["it is shown as is and takes no content"], 0.0
    reasons: List[str] = []
    lost: List[str] = []
    text = _assign_text(pattern, slide, lost)
    images = list(dict.fromkeys(([slide.image] if slide.image else []) + slide.images))
    image_zones = sum(1 for z in pattern.zones if z.role == "image")
    if len(images) > image_zones:
        lost.append(f"{len(images) - image_zones} image(s)")
    capacity = max((g.count for g in pattern.groups), default=0)
    if slide.items and not capacity:
        lost.append("items")
    elif len(slide.items) > capacity:
        reasons.append(f"{len(slide.items)} items, holds at most {capacity}")
    lost.extend(_unused_item_fields(pattern.groups, slide))
    if lost:
        reasons.insert(0, "no place for " + ", ".join(lost))

    cost = 0.0
    zones = {z.key: z for z in pattern.zones}
    for key, lines in text.items():
        zone = zones[key]
        cost += _check_zone(
            zone, lines, SLIDE_FIELDS.get(zone.role, "bullets"), size, reasons
        )
    for group in pattern.groups:
        group_text, _, _ = _assign_group(group, slide)
        item_zones = {z.key: z for item in group.items for z in item}
        for key, lines in group_text.items():
            zone = item_zones[key]
            what = f"items' {ITEM_FIELDS.get(zone.role, zone.role)}"
            cost += _check_zone(zone, lines, what, size, reasons)
    if reasons:
        return reasons, 0.0

    for zone in pattern.zones:
        if zone.role == "image":
            cost += 0.0 if images else _IMAGE_HOLE
        elif zone.role != "keep" and zone.key not in text:
            cost += _EMPTY_ZONE
    cost += _UNUSED_ITEM * max(0, capacity - len(slide.items)) if slide.items else 0.0
    if pattern.source == "layout":
        cost += _LAYOUT
    return reasons, cost


# --- deck assignment ----------------------------------------------------------------------


@dataclass
class _Slide:
    index: int  # 1-based position in the plan
    plan: SlidePlan
    first: bool
    last: bool
    kinds: List[SlideKind] = field(default_factory=list)
    # Every assignable pattern, with its misfit reasons and cost.
    checked: List[Tuple[Pattern, List[str], float]] = field(default_factory=list)
    candidates: List[Tuple[Pattern, float]] = field(default_factory=list)


def _allowed(pattern: Pattern, slide: _Slide, has_cover: bool) -> bool:
    if pattern.kind == "cover":
        return slide.first
    if slide.first and has_cover:
        return False
    if pattern.kind == "closing":
        return slide.last
    return True


def _kinds(slide: _Slide, has_cover: bool) -> List[SlideKind]:
    if slide.first and has_cover:
        return ["cover"]
    if slide.plan.kind:
        return [slide.plan.kind]
    return infer_kinds(slide.plan)


def _position_problem(slide: _Slide, has_cover: bool) -> Optional[SlideProblem]:
    kind = slide.plan.kind
    if kind == "cover" and not slide.first and has_cover:
        return SlideProblem(
            slide.index,
            "only the first slide can be the cover",
            ["kind 'section' for a divider", "move it to the start of the deck"],
            kind,
        )
    if kind == "closing" and not slide.last:
        return SlideProblem(
            slide.index,
            "a closing slide can only end the deck",
            ["move it to the end", "another kind for this content"],
            kind,
        )
    if not has_content(slide.plan) and not slide.last and kind != "closing":
        return SlideProblem(
            slide.index, "the slide is empty", ["remove it", "give it content"], kind
        )
    return None


def _problem(slide: _Slide, has_cover: bool) -> SlideProblem:
    kinds = slide.kinds
    own = [
        (p, r)
        for p, r, _ in slide.checked
        if p.kind in kinds and _allowed(p, slide, has_cover)
    ]
    label = "' or '".join(kinds)
    options: List[str] = []
    if not own:
        problem = f"this template has no '{label}' slide"
    else:
        # Fewest problems, then the roomiest: the slide a revision would land on.
        closest, reasons = min(
            own,
            key=lambda pr: (len(pr[1]), -sum(z.max_chars or 0 for z in pr[0].zones)),
        )
        problem = f"the closest '{closest.kind}' slide: " + "; ".join(reasons)
        most = max((g.count for p, _ in own for g in p.groups), default=0)
        if slide.plan.items and most and len(slide.plan.items) > most:
            problem = f"{len(slide.plan.items)} items; the largest '{label}' slide holds {most}"
            options += [f"trim to {most} items", "split the items over two slides"]
        if any("too long" in r for r in reasons):
            options.append("shorten the text")
        options.append(f"a '{closest.kind}' slide takes: {zone_summary(closest)}")
    if slide.first and has_cover:
        problem = "the first slide is always the template's cover; " + problem
        options.insert(0, "add a cover slide (title, subtitle) before it")
    fitting = [
        p.kind
        for p, reasons, _ in slide.checked
        if not reasons and p.kind not in kinds and _allowed(p, slide, has_cover)
    ]
    for kind in list(dict.fromkeys(fitting))[:_MAX_KIND_OPTIONS]:
        options.append(f"kind '{kind}' holds this content as written")
    return SlideProblem(slide.index, problem, options, slide.plan.kind)


# (candidate at slide i-1, or -1 before the first; candidate at slide i)
_State = Tuple[int, int]


def _viterbi(slides: List[_Slide]) -> List[Pattern]:
    """Cheapest pattern sequence, penalising repeats; the state is the pair of
    the last two choices so three in a row can be priced."""
    best: Dict[_State, float] = {
        (-1, b): cost for b, (_, cost) in enumerate(slides[0].candidates)
    }
    back: List[Dict[_State, _State]] = [{}]
    for i in range(1, len(slides)):
        prev, here = slides[i - 1].candidates, slides[i].candidates
        before = slides[i - 2].candidates if i >= 2 else []
        nxt: Dict[_State, float] = {}
        ptr: Dict[_State, _State] = {}
        for (a, b), total in best.items():
            for c, (pattern, cost) in enumerate(here):
                step = total + cost
                if prev[b][0].id == pattern.id:
                    step += _REPEAT
                    if a >= 0 and before[a][0].id == pattern.id:
                        step += _TRIPLE
                if step < nxt.get((b, c), float("inf")):
                    nxt[(b, c)] = step
                    ptr[(b, c)] = (a, b)
        best = nxt
        back.append(ptr)
    state = min(best, key=lambda s: best[s])
    chosen = [state[1]]
    for i in range(len(slides) - 1, 0, -1):
        state = back[i][state]
        chosen.append(state[1])
    chosen.reverse()
    return [slides[i].candidates[c][0] for i, c in enumerate(chosen)]


def assign(inventory: TemplateInventory, plan: DeckPlan) -> Assignment:
    """One pattern per slide of ``plan``, or the problems that prevent it."""
    pool = assignable(inventory)
    has_cover = any(p.kind == "cover" for p in pool)
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
    problems: List[SlideProblem] = []
    for slide in slides:
        slide.kinds = _kinds(slide, has_cover)
        position = _position_problem(slide, has_cover)
        if position is not None:
            problems.append(position)
            continue
        slide.checked = [(p, *misfit(p, slide.plan, size)) for p in pool]
        slide.candidates = [
            (p, cost + _KIND_STEP * slide.kinds.index(p.kind))
            for p, reasons, cost in slide.checked
            if not reasons and p.kind in slide.kinds and _allowed(p, slide, has_cover)
        ]
        if not slide.candidates:
            problems.append(_problem(slide, has_cover))
    if problems or not slides:
        return Assignment(problems=problems)

    chosen = _viterbi(slides)
    patterns: List[Optional[Pattern]] = [None] * len(plan.slides)
    for slide, pattern in zip(slides, chosen):
        patterns[slide.index - 1] = pattern
    notes = [
        f"Slides {slides[i - 2].index} to {slides[i].index} use the same template slide: "
        "no other one holds their content."
        for i in range(2, len(chosen))
        if chosen[i].id == chosen[i - 1].id == chosen[i - 2].id
    ]
    return Assignment(patterns=patterns, notes=notes)
