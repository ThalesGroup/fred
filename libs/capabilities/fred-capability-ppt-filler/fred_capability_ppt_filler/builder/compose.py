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

"""Composition: what shape a slide's content has, and which composition says it.

Design layer (design.md D8) — no ``pptx`` here either. Two jobs:

* project every composition of the library into an ordinary ``Pattern``, so the
  catalogue, the scoring, the fill path and the review surface need no special
  case for a composed slide (D3);
* classify a slide's content by its SHAPE and pick the composition that
  expresses it (D9) — in the renderer, not as a hint to the agent, because
  ``bullets`` is the cheapest field in the plan to fill and a weaker model
  fills it whatever the content actually is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Sequence, Tuple

from fred_capability_ppt_filler.builder.components import (
    COMPOSITIONS,
    ComposedSlide,
    Piece,
    compose,
    variant_for,
)
from fred_capability_ppt_filler.builder.design_system import FIGURE_TEXT, DesignSystem

if TYPE_CHECKING:  # avoids the plan -> compose -> plan import cycle
    from fred_capability_ppt_filler.builder.plan import SlidePlan

from fred_capability_ppt_filler.builder.design_system import ZoneRole
from fred_capability_ppt_filler.builder.models import (
    Intent,
    Pattern,
    RepeatGroup,
    TemplateInventory,
    Zone,
)

#: Intent each composition answers, so a composed pattern sits in the catalogue
#: beside the template's own and the agent never learns a second vocabulary.
COMPOSITION_INTENT: Dict[str, Intent] = {
    "card_row": "cards",
    "stat_band": "cards",
    "comparison": "comparison",
    "steps": "steps",
    "agenda": "agenda",
    "progress": "cards",
    "statement": "statement",
    "figure_caption": "image_text",
    "prose": "content",
    "framed_cards": "cards",
    "lead_and_cards": "two_columns",
    "icon_cards": "cards",
    "rich_cards": "cards",
}

#: Shown in the review surface; the author may relabel any of them.
COMPOSITION_LABEL: Dict[str, str] = {
    "card_row": "Cards",
    "stat_band": "Key figures",
    "comparison": "Comparison",
    "steps": "Steps",
    "agenda": "Agenda",
    "progress": "Progress bars",
    "statement": "Statement",
    "figure_caption": "Image with caption",
    "prose": "Text",
    "framed_cards": "Framed cards",
    "lead_and_cards": "Lead and cards",
    "icon_cards": "Icon cards",
    "rich_cards": "Detailed cards",
}


def composed_pattern_id(composition: str, count: int) -> str:
    return f"composed:{composition}:{count}"


def _zone_of(piece: Piece) -> Zone:
    """One content piece as a fillable zone, addressed by its shape name.

    The key is rebound to the real shape once drawn (`composed_render`): the
    shape does not exist yet when the pattern is projected. The capacity is the
    piece's own, never the slide's: a number box and the paragraph beside it do
    not hold the same.
    """
    assert piece.role is not None
    return Zone(
        key=f"sp:{piece.name}",
        role=piece.role,
        box=piece.box,
        font_pt=piece.font_pt,
        max_chars=piece.max_chars or None,
        max_lines=piece.max_lines or None,
    )


def _project(slide: ComposedSlide) -> Tuple[List[Zone], List[RepeatGroup]]:
    """Split a composition into its standalone zones and its repeated group.

    Repeated items have to arrive as a `RepeatGroup`, not as flat zones: that
    is how the unchanged fill path reaches `plan.items`, and how it drops the
    items the plan did not fill.
    """
    singles: List[Zone] = []
    per_item: Dict[int, List[Piece]] = {}
    for piece in sorted(slide.pieces, key=lambda p: p.reading_order):
        if piece.decorative or not piece.slot or piece.role is None:
            continue
        if piece.slot.startswith("item:"):
            index = int(piece.slot.split(":")[1])
            per_item.setdefault(index, []).append(piece)
        else:
            singles.append(_zone_of(piece))
    if not per_item:
        return singles, []

    order = sorted(per_item)
    roles: List[ZoneRole] = [
        piece.role for piece in per_item[order[0]] if piece.role is not None
    ]
    items = [[_zone_of(piece) for piece in per_item[index]] for index in order]
    # The container to remove when an item goes unused: its Card when it has
    # one, else the item's own first shape.
    containers = []
    for index in order:
        card = next(
            (p for p in slide.pieces if p.decorative and p.name.endswith(f"-{index}")),
            None,
        )
        containers.append(f"sp:{(card or per_item[index][0]).name}")
    group = RepeatGroup(
        key="composed-items",
        count=len(order),
        item_zones=roles,
        items=items,
        item_keys=containers,
    )
    return singles, [group]


def composed_patterns(system: Optional[DesignSystem]) -> List[Pattern]:
    """Every composition this template can carry, as ordinary patterns (D3).

    A template with no design system yields none, and composition simply never
    happens on it — the capability behaves exactly as it did before.
    """
    if system is None or not system.complete:
        return []
    patterns: List[Pattern] = []
    for composition, counts in COMPOSITIONS.items():
        for count in counts:
            slide = compose(system, composition, items=count)
            if slide is None:
                continue
            zones, groups = _project(slide)
            label = COMPOSITION_LABEL.get(composition, composition)
            patterns.append(
                Pattern(
                    id=composed_pattern_id(composition, count),
                    source="composed",
                    source_index=count,
                    name=f"{composition}:{count}",
                    label=label if count <= 1 else f"{label} ({count})",
                    intent=COMPOSITION_INTENT.get(composition, "content"),
                    zones=zones,
                    groups=groups,
                    included=True,
                )
            )
    return patterns


def with_composed_patterns(inventory: TemplateInventory) -> List[Pattern]:
    """The template's own patterns, plus what composing adds.

    The template's come first: ordering is what a reader of the catalogue reads
    as preference, and naming one of them is how an author asks for that slide
    as it stands (D5).
    """
    return list(inventory.patterns) + composed_patterns(inventory.design_system)


def resolve(
    system: DesignSystem, pattern_id: str
) -> Optional[Tuple[str, int, ComposedSlide]]:
    """The composition behind a composed pattern id, resolved to pieces."""
    if not pattern_id.startswith("composed:"):
        return None
    _, composition, raw = pattern_id.split(":", 2)
    try:
        count = int(raw)
    except ValueError:
        return None
    slide = compose(system, composition, items=count)
    if slide is None:
        return None
    return composition, count, slide


def pieces_by_slot(slide: ComposedSlide) -> Dict[str, Piece]:
    return {piece.slot: piece for piece in slide.pieces if piece.slot}


def variants_of(composition: str) -> Sequence[int]:
    return COMPOSITIONS.get(composition, ())


__all__ = [
    "COMPOSITION_INTENT",
    "COMPOSITION_LABEL",
    "composed_pattern_id",
    "composed_patterns",
    "pieces_by_slot",
    "resolve",
    "variant_for",
    "variants_of",
    "with_composed_patterns",
]


# -- what shape is this content? (D9) -----------------------------------------
#
# Decided here, from the plan's content, and NOT from the intent the agent
# asked for. `SlidePlan.bullets` is the cheapest field in the schema to fill,
# so it is the one a weaker model fills whatever the content actually is; a
# hint in the tool description helps the strong models and does nothing for the
# weak ones, while a rule here helps both.

ContentShape = Literal[
    "parallel_items",
    "figures",
    "opposed_sets",
    "sequence",
    "sentence",
    "quantities",
    "prose",
    "empty",
]

#: Which composition expresses each shape.
SHAPE_COMPOSITION: Dict[str, str] = {
    "parallel_items": "card_row",
    "figures": "stat_band",
    "opposed_sets": "comparison",
    "sequence": "steps",
    "sentence": "statement",
    "quantities": "progress",
    "prose": "prose",
}

#: Above this, a "bullet" is a sentence and the slide is prose, not a list.
SHORT_ITEM_CHARS = 90

# "1." then a boundary never matches: "." and " " are both non-word, so the
# numeric branch ends on the punctuation instead.
_ORDINAL = __import__("re").compile(
    r"^\s*(?:\d+\s*[.)\u2013-]|(?:[ée]tape|step|phase|stage)\b)", 2
)


def _short(text: Optional[str]) -> bool:
    return bool(text) and len(text or "") <= SHORT_ITEM_CHARS


def _is_figure(text: Optional[str]) -> bool:
    return bool(text) and bool(FIGURE_TEXT.match((text or "").strip()))


def content_shape(slide: "SlidePlan") -> ContentShape:
    """The shape of what this slide carries, whatever the plan called it."""
    items = list(slide.items or [])
    bullets = [b for b in (slide.bullets or []) if b and b.strip()]
    columns = list(slide.columns or [])

    if columns and len(columns) == 2:
        return "opposed_sets"
    if items:
        # Parallelism needs at least two things to be parallel to. A lone item
        # is not a card row, and composing one would override the agent for no
        # gain — the template's own pattern carries it just as well.
        if len(items) < 2:
            return "prose" if not _short(items[0].heading) else "sentence"
        if all(_is_figure(item.number) for item in items if item.number) and any(
            item.number for item in items
        ):
            # A figure with a bar beside it is a quantity; a figure alone is a stat.
            if all(
                _is_figure(item.number) and "%" in (item.number or "")
                for item in items
                if item.number
            ):
                return "quantities"
            return "figures"
        if any(_ORDINAL.match(item.heading or "") for item in items):
            return "sequence"
        if all(_short(item.heading) for item in items):
            return "parallel_items"
        return "prose"
    if bullets:
        if len(bullets) == 1 and _short(bullets[0]):
            return "sentence"
        # Parallel means short AND alike: a list of sentences is prose that
        # someone typed with dashes, and breaking it into cards reads worse
        # than the bullet list it replaced.
        if 2 <= len(bullets) <= 6 and all(_short(b) for b in bullets):
            return "parallel_items"
        return "prose"
    return "empty"


def composition_for(shape: str, items: int) -> Optional[str]:
    """The composition that expresses `shape`, in a variant holding `items`."""
    composition = SHAPE_COMPOSITION.get(shape)
    if composition is None:
        return None
    if variant_for(composition, max(1, items)) is None:
        return None
    return composition


def reshape(slide: "SlidePlan", composition: str) -> "SlidePlan":
    """Move the content into the fields the chosen composition reads.

    A plan written as plain bullets still becomes a card row: the classification
    decided the shape, so the content has to arrive where that shape reads it.
    Nothing is invented and nothing is dropped.
    """
    from fred_capability_ppt_filler.builder.plan import PlanItem

    wants_items = composition in (
        "card_row",
        "stat_band",
        "comparison",
        "steps",
        "agenda",
        "progress",
    )
    if not wants_items or slide.items:
        return slide
    bullets = [b.strip() for b in (slide.bullets or []) if b and b.strip()]
    if slide.columns and composition == "comparison":
        items = [
            PlanItem(heading=column.heading, text="\n".join(column.bullets))
            for column in slide.columns
        ]
        return slide.model_copy(update={"items": items, "columns": [], "bullets": []})
    if not bullets:
        return slide
    return slide.model_copy(
        update={"items": [PlanItem(heading=text) for text in bullets], "bullets": []}
    )


# -- compose, or keep the template's pattern? (D5) ----------------------------


class Choice:
    """What to render for one planned slide, and why."""

    def __init__(
        self,
        pattern: Pattern,
        slide: "SlidePlan",
        *,
        composed: bool = False,
        note: Optional[str] = None,
    ) -> None:
        self.pattern = pattern
        self.slide = slide
        self.composed = composed
        self.note = note


def choose(inventory: TemplateInventory, slide: "SlidePlan", chosen: Pattern) -> Choice:
    """What to render for this slide: a composition, or the template's pattern.

    Composing is the normal path for structured content. The template is the
    design LANGUAGE — its tokens, its grid, its fixtures, the component style
    it demonstrates — not a stock of slides to recycle: a slide is built for
    the content it has to carry rather than fitted into the nearest thing the
    designer once drew. Reusing a pattern as it stands is the answer to an
    explicit request to fill that pattern, which `named_explicitly` is (D5).

    Prose is never restructured (D9): breaking a paragraph into cards looks
    designed and reads worse than the list it replaced. It keeps the loss
    comparison below, where the template's own text pattern usually wins.
    """
    system = inventory.design_system
    if system is None or not system.complete:
        return Choice(chosen, slide)

    # An exact pattern id is the agent's decision, and it is honoured: the
    # classification only decides what the agent left unsaid (D9). Without this
    # line a stray bullet on a KPI slide would silently turn it into something
    # else — a large change driven by a small mistake.
    if named_explicitly(inventory, slide):
        return Choice(chosen, slide)

    # Some intents cannot be read off the content: nothing distinguishes an
    # agenda from a list of parallel items, or a figure-and-caption from any
    # other image slide. Asking for one is then the ONLY way to get one, so
    # the ask stands — the classification decides what was left unsaid (D9).
    asked = _asked_intent(slide)
    if asked is not None and asked == chosen.intent:
        wanted = next(
            (name for name, intent in COMPOSITION_INTENT.items() if intent == asked),
            None,
        )
        return Choice(chosen, reshape(slide, wanted) if wanted else slide)

    shape = content_shape(slide)
    composition = composition_for(shape, _item_count(slide))
    if composition is None:
        return Choice(chosen, slide)

    reshaped = reshape(slide, composition)
    count = _item_count(reshaped)
    variant = variant_for(composition, count)
    if variant is None:
        return Choice(chosen, slide)

    candidate = next(
        (
            pattern
            for pattern in composed_patterns(system)
            if pattern.id == composed_pattern_id(composition, variant)
        ),
        None,
    )
    if candidate is None:
        return Choice(chosen, slide)

    # Structured content is composed outright. Falling back to the loss
    # comparison here would hand it to the bullet list, which shows the words
    # and loses the shape — the very deck this change exists to stop.
    if shape not in STRUCTURED_SHAPES and _lost_share(chosen, slide) <= _lost_share(
        candidate, reshaped
    ):
        return Choice(chosen, slide)
    return Choice(
        candidate,
        reshaped,
        composed=True,
        note=(
            f"composed as {COMPOSITION_LABEL.get(composition, composition)} — "
            f"the content is {shape.replace('_', ' ')}"
        ),
    )


#: Shapes whose expression is decided by the content, not by what the plan
#: happened to call the slide. Prose is deliberately absent: breaking a
#: paragraph into cards looks designed and reads worse than the list it
#: replaced (D9).
STRUCTURED_SHAPES: frozenset = frozenset(
    {"parallel_items", "figures", "quantities", "sequence", "opposed_sets"}
)


def _lost_share(pattern: Pattern, slide: "SlidePlan") -> float:
    """How much of the slide's content this pattern cannot show, 0..1.

    Reads `shown_fields` and NOT `score_pattern`: the score folds a preference
    bonus and an overflow penalty into the same number, so a preferred pattern
    that loses a field can outrank one that loses nothing (D5).
    """
    from fred_capability_ppt_filler.builder.plan import shown_fields

    shown, given = shown_fields(pattern, slide)
    # Dropping items is losing content too, and `shown_fields` weighs field
    # KINDS, not counts: without this a 2-up would look as good as a 3-up for
    # three items, and silently drop the third.
    wanted = len(slide.items or [])
    if wanted:
        room = max((group.count for group in pattern.groups), default=0)
        if room:
            given += wanted
            shown += min(room, wanted)
        else:
            given += wanted
    if given <= 0:
        return 0.0
    return max(0.0, 1.0 - shown / given)


#: Intents no content shape can produce. A slide of four short lines is a card
#: row by its content whether it is the agenda or not, so only the ask can say.
UNINFERABLE_INTENTS: frozenset = frozenset({"agenda", "image_text", "two_columns"})


def _asked_intent(slide: "SlidePlan") -> Optional[str]:
    """The intent the plan asked for by name, when the content cannot say it."""
    requested = (slide.pattern or "").strip().lower()
    return requested if requested in UNINFERABLE_INTENTS else None


def named_explicitly(inventory: TemplateInventory, slide: "SlidePlan") -> bool:
    """Did the plan name a real, usable pattern of this template?

    An intent name (`cards`, `content`) is not naming a pattern: it says what
    the slide is for and leaves the choice open.
    """
    requested = (slide.pattern or "").strip()
    if not requested:
        return False
    pattern = inventory.pattern(requested)
    return pattern is not None and pattern.included


def _item_count(slide: "SlidePlan") -> int:
    if slide.items:
        return len(slide.items)
    if slide.columns:
        return len(slide.columns)
    bullets = [b for b in (slide.bullets or []) if b and b.strip()]
    return len(bullets) or 1
