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

A slide's candidates are the patterns that hold all of its content, of the
requested kind first, then of the kinds its content suggests, then of any kind
(each substitution is reported). A second-order Viterbi pass picks one per
slide under the deck rules. A slide that fits nothing is a problem the model
must fix, named down to the element (design.md D7, D8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fred_capability_ppt_filler.builder import lexicon
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
    SlidePlan,
    capacity_text,
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
_REPEAT = 3.0  # the same slide twice in a row
_TRIPLE = 1000.0  # three in a row: taken only when nothing else fits

_MAX_KIND_OPTIONS = 3


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
class Assignment:
    # Aligned with the plan's slides; None for an entry that is not a slide.
    patterns: List[Optional[Pattern]] = field(default_factory=list)
    problems: List[SlideProblem] = field(default_factory=list)
    # Substitutions and repetitions the agent should hear about.
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
            f"shorten {source} to ≈{target} chars",
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
        f"keep {name} within {rows} line(s) of ≈{per_line} chars: shorten or drop entries",
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


def _no_place(what: str) -> Misfit:
    return Misfit(f"{what}: this slide has no place for it", f"drop {what}")


def misfit(
    pattern: Pattern, slide: SlidePlan, size: Tuple[int, int]
) -> Tuple[List[Misfit], float]:
    """Why ``pattern`` cannot hold all of ``slide`` (empty when it can), and the
    cost of the fit. Uses the renderer's own placement, so a fitting pattern
    loses nothing when rendered."""
    if not pattern.fillable:
        if not has_content(slide) or _only_names_the_slide(slide, pattern):
            return [], 0.0
        return [Misfit("this slide is shown as is and takes no content")], 0.0
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
    lost.extend(_unused_item_fields(pattern.groups, slide))
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
    reasons[:0] = [_no_place(what) for what in lost if what not in held]

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
        long_items: Dict[str, List[Misfit]] = {}
        for key, lines in group_text.items():
            zone = item_zones[key]
            what = f"items[].{ITEM_FIELDS.get(zone.role, zone.role)}"
            found: List[Misfit] = []
            cost += _check_zone(zone, lines, what, size, found)
            for reason in found:
                long_items.setdefault(what, []).append(reason)
        # One line per item field: six cards too long are one fix, not six.
        for what, found in long_items.items():
            reasons.append(found[0] if len(found) == 1 else _many(found))
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


def _many(found: List[Misfit]) -> Misfit:
    """``items[0].text is 150 chars; …`` ×N folded into one reason."""
    if any(not f.source for f in found):
        return Misfit("; ".join(f.text for f in found), found[0].option)
    return Misfit(
        f"{', '.join(f.source for f in found)} are "
        f"{', '.join(str(f.length) for f in found)} chars; each zone holds {found[0].room}",
        f"shorten every {re.sub(r'\[\d+\]', '[]', found[0].source)} to "
        f"≈{min(f.target for f in found)} chars",
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


def _allowed(pattern: Pattern, slide: _Slide, has_cover: bool) -> bool:
    if pattern.kind == "cover":
        return slide.first
    if slide.first and has_cover:
        return False
    if pattern.kind == "closing":
        return slide.last
    return True


def _tiers(slide: _Slide, has_cover: bool) -> List[List[SlideKind]]:
    """The requested kind, then the kinds the content suggests, then any kind."""
    if slide.first and has_cover:
        return [["cover"]]
    inferred = infer_kinds(slide.plan)
    asked = slide.plan.kind
    tiers: List[List[SlideKind]] = [[asked]] if asked else []
    tiers.append([k for k in inferred if k != asked])
    seen = set(inferred) | {asked}
    tiers.append([k for k in SLIDE_KINDS if k not in seen])
    return tiers


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


def _problem(slide: _Slide, has_cover: bool) -> SlideProblem:
    """The closest pattern's misfits, named down to the element, with fixes."""
    # The asked and the inferred kinds rank together: the advice should be about
    # the shape the content has, not about an unrelated kind that happens to fit.
    rank = {k: 0 for tier in slide.tiers[:-1] for k in tier}
    rank.update({k: 1 for k in slide.tiers[-1]})
    own = [
        (p, r)
        for p, r, _ in slide.checked
        if p.kind in rank and _allowed(p, slide, has_cover)
    ]
    options: List[str] = []
    if not own:
        problem = "this template has no slide that can take this position"
    else:
        # The kind closest to the content, then fewest problems, then the roomiest.
        closest, reasons = min(
            own,
            key=lambda pr: (
                rank[pr[0].kind],
                len(pr[1]),
                -sum((z.chars_per_line or 0) * (z.max_lines or 0) for z in pr[0].zones),
            ),
        )
        problem = f"closest fit, a '{closest.kind}' slide: " + "; ".join(
            r.text for r in reasons
        )
        most = max((g.count for p, _ in own for g in p.groups), default=0)
        if slide.plan.items and most and len(slide.plan.items) > most:
            problem = (
                f"items: {len(slide.plan.items)} given; the largest slide of this "
                f"template holds {most}"
            )
            options += [f"trim to {most} items", "split the items over two slides"]
            reasons = [r for r in reasons if not r.text.startswith("items:")]
        options += [r.option for r in reasons if r.option]
        options.append(f"a '{closest.kind}' slide takes: {zone_summary(closest)}")
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


def _substitution(slide: _Slide, chosen: Pattern, offered: set[str]) -> Optional[str]:
    asked = slide.plan.kind
    # The first slide is the cover by rule, and the description says so.
    if not asked or chosen.kind == asked or (slide.first and chosen.kind == "cover"):
        return None
    if asked == "cover" and not slide.first:
        why = "only the first slide can be the cover"
    elif asked == "closing" and not slide.last:
        why = "a closing slide can only end the deck"
    elif asked not in offered:
        why = f"this template has no '{asked}' slide"
    else:
        why = f"no '{asked}' slide holds this content"
    return (
        f"Slide {slide.index}: built as '{chosen.kind}' instead of '{asked}' ({why})."
    )


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
    problems: List[SlideProblem] = []
    for slide in slides:
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
        slide.candidates = _candidates(slide, has_cover)
        if not slide.candidates:
            problems.append(_problem(slide, has_cover))
    if problems or not slides:
        return Assignment(problems=problems)

    chosen = _viterbi(slides)
    patterns: List[Optional[Pattern]] = [None] * len(plan.slides)
    for slide, pattern in zip(slides, chosen):
        patterns[slide.index - 1] = pattern
    notes = [
        note
        for slide, pattern in zip(slides, chosen)
        if (note := _substitution(slide, pattern, offered))
    ]
    notes += [
        f"Slides {slides[i - 2].index} to {slides[i].index} use the same template slide: "
        "no other one holds their content."
        for i in range(2, len(chosen))
        if chosen[i].id == chosen[i - 1].id == chosen[i - 2].id
    ]
    return Assignment(patterns=patterns, notes=notes)
