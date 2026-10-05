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

"""What shape is this content, and what expresses it (design.md D5, D9).

The rule these tests pin down: the SHAPE of the content decides what has to be
shown, and the template stays first in line to show it. A designer's own cards
beat a composition every time; composing happens when the template has nothing
that carries the shape without losing content. Prose is never restructured.
"""

from __future__ import annotations

import io

import pytest
from fred_capability_ppt_filler.builder.analysis import analyze_presentation
from fred_capability_ppt_filler.builder.compose import (
    STRUCTURED_SHAPES,
    choose,
    composed_patterns,
    composition_for,
    content_shape,
    named_explicitly,
    reshape,
)
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanColumn,
    PlanItem,
    SlidePlan,
    resolve,
)
from fred_capability_ppt_filler.builder.render import _Renderer
from fred_capability_ppt_filler.builder.theme import default_theme
from pptx import Presentation

LONG = (
    "Une phrase longue qui developpe un raisonnement suivi, avec ses nuances, "
    "et qui ne ressemble en rien a une liste d'elements paralleles courts."
)


@pytest.fixture(scope="module")
def rich():
    raw, inventory = default_theme()
    return raw, inventory.model_copy(
        update={
            "patterns": inventory.patterns + composed_patterns(inventory.design_system)
        }
    )


@pytest.fixture(scope="module")
def stripped():
    source = Presentation()
    cover = source.slides.add_slide(source.slide_layouts[0])
    cover.shapes.title.text = "Cover"
    source.slides.add_slide(source.slide_layouts[6])
    buffer = io.BytesIO()
    source.save(buffer)
    raw = buffer.getvalue()
    inventory = analyze_presentation(Presentation(io.BytesIO(raw)))
    return raw, inventory.model_copy(
        update={
            "patterns": inventory.patterns + composed_patterns(inventory.design_system)
        }
    )


def _render(fixture, *slides):
    raw, inventory = fixture
    presentation = Presentation(io.BytesIO(raw))
    result = _Renderer(presentation, inventory, {}).render(
        DeckPlan(slides=list(slides))
    )
    return presentation, result


def _composed(slide) -> bool:
    return any(shape.name.startswith("composed-") for shape in slide.shapes)


# -- classification (D9) -------------------------------------------------------


@pytest.mark.parametrize(
    "slide,expected",
    [
        (SlidePlan(bullets=["Fast", "Safe", "Plain", "Open"]), "parallel_items"),
        (SlidePlan(bullets=["We double capacity."]), "sentence"),
        (SlidePlan(bullets=[LONG]), "prose"),
        (SlidePlan(bullets=[LONG, LONG]), "prose"),
        (
            SlidePlan(
                items=[
                    PlanItem(number="62", heading="A"),
                    PlanItem(number="1 200", heading="B"),
                ]
            ),
            "figures",
        ),
        (
            SlidePlan(
                items=[
                    PlanItem(number="62%", heading="A"),
                    PlanItem(number="31%", heading="B"),
                ]
            ),
            "quantities",
        ),
        (
            SlidePlan(
                items=[
                    PlanItem(heading="1. Frame"),
                    PlanItem(heading="2. Build"),
                    PlanItem(heading="3. Ship"),
                ]
            ),
            "sequence",
        ),
        (
            SlidePlan(
                columns=[
                    PlanColumn(heading="Before", bullets=["x"]),
                    PlanColumn(heading="After", bullets=["y"]),
                ]
            ),
            "opposed_sets",
        ),
        (SlidePlan(), "empty"),
        # One thing is not parallel to anything.
        (SlidePlan(items=[PlanItem(heading="Alone")]), "sentence"),
    ],
)
def test_content_is_classified_by_its_shape(slide, expected):
    assert content_shape(slide) == expected


def test_prose_is_not_structured_and_never_becomes_cards():
    """The failure mode of this rule is a paragraph broken into cards that
    carry no parallel meaning: it looks designed and reads worse."""
    assert content_shape(SlidePlan(bullets=[LONG])) == "prose"
    assert "prose" not in STRUCTURED_SHAPES
    assert composition_for("prose", 1) == "prose"


def test_bullets_move_into_the_fields_the_composition_reads():
    slide = SlidePlan(bullets=["Fast", "Safe", "Plain"])

    reshaped = reshape(slide, "card_row")

    assert [item.heading for item in reshaped.items] == ["Fast", "Safe", "Plain"]
    assert reshaped.bullets == []


def test_reshaping_invents_nothing_and_drops_nothing():
    slide = SlidePlan(
        columns=[
            PlanColumn(heading="Before", bullets=["a", "b"]),
            PlanColumn(heading="After", bullets=["c"]),
        ]
    )

    reshaped = reshape(slide, "comparison")

    assert [item.heading for item in reshaped.items] == ["Before", "After"]
    assert [item.text for item in reshaped.items] == ["a\nb", "c"]


# -- the shape decides, the template shows (D5, D9) ---------------------------


def test_a_bullet_list_of_parallel_items_becomes_cards(stripped):
    """The deck this whole change exists to stop: four short parallel things
    rendered as yet another bullet list."""
    presentation, result = _render(
        stripped,
        SlidePlan(
            pattern="content",
            title="Context",
            bullets=["Fast", "Safe", "Plain", "Open"],
        ),
    )

    assert result.warnings == []
    assert _composed(presentation.slides[0])
    texts = {
        s.text_frame.text for s in presentation.slides[0].shapes if s.has_text_frame
    }
    assert {"Fast", "Safe", "Plain", "Open"} <= texts


def test_a_genuine_paragraph_still_renders_as_text(stripped):
    presentation, result = _render(
        stripped, SlidePlan(pattern="content", title="Analysis", bullets=[LONG])
    )

    assert result.warnings == []
    slide = presentation.slides[0]
    # Prose keeps one text block; it is not broken into cards.
    assert not any(s.name.startswith("composed-card-") for s in slide.shapes)


def test_a_rich_template_is_a_language_to_compose_in_not_a_stock_to_recycle(rich):
    """Even where the designer drew steps of their own, the slide is composed.

    The template supplies the tokens, the grid and the fixtures; the slide is
    built for the content it carries rather than fitted into the nearest thing
    already drawn (D5).
    """
    _, inventory = rich
    slide = SlidePlan(
        pattern="content",
        title="Steps",
        items=[PlanItem(heading=f"{n}. Phase {n}") for n in (1, 2, 3)],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    assert choice.composed
    assert choice.pattern.id.startswith("composed:steps:")


def test_naming_a_pattern_asks_for_that_slide_as_it_stands(rich):
    """The one way back to verbatim reuse: ask for it (D5)."""
    _, inventory = rich
    own = next(
        p
        for p in inventory.patterns
        if p.included and p.source != "composed" and p.intent == "steps"
    )
    slide = SlidePlan(
        pattern=own.id,
        title="Steps",
        items=[PlanItem(heading=f"{n}. Phase {n}") for n in (1, 2, 3)],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    assert not choice.composed
    assert choice.pattern.id == own.id


def test_composing_happens_only_when_the_template_has_nothing_that_fits(stripped):
    _, inventory = stripped
    slide = SlidePlan(
        pattern="content",
        title="Three",
        items=[
            PlanItem(heading=f"Axis {n}", text=f"What {n} changes.") for n in (1, 2, 3)
        ],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    assert choice.composed
    assert choice.pattern.id.startswith("composed:card_row")
    assert choice.note


def test_an_explicitly_named_pattern_is_never_overridden(rich):
    """Naming a pattern is the agent's decision; the classification only
    decides what the agent left unsaid."""
    _, inventory = rich
    named = next(p for p in inventory.patterns if p.included and p.intent == "content")
    slide = SlidePlan(pattern=named.id, title="Mine", bullets=["Fast", "Safe", "Plain"])

    assert named_explicitly(inventory, slide)
    choice = choose(inventory, slide, named)

    assert not choice.composed
    assert choice.pattern.id == named.id


def test_an_intent_name_is_not_naming_a_pattern(rich):
    _, inventory = rich

    assert not named_explicitly(inventory, SlidePlan(pattern="cards"))
    assert not named_explicitly(inventory, SlidePlan(pattern=""))


# -- the fallback rule reads the loss, not the ranking (D5) -------------------


def test_a_preferred_pattern_that_loses_content_does_not_suppress_composition(stripped):
    """`score_pattern` would rank it first on its preference bonus alone; the
    decision reads the share of content shown instead."""
    _, inventory = stripped
    slide = SlidePlan(
        pattern="cards",
        title="Three",
        items=[PlanItem(heading=f"A{n}", text=f"T{n}") for n in (1, 2, 3)],
    )
    chosen = resolve(inventory, slide).pattern

    choice = choose(inventory, slide, chosen)

    assert choice.composed


def test_dropping_items_counts_as_losing_content(rich):
    """A two-slot design is not the answer to three parallel things: it shows
    the same KINDS of field and silently drops the third."""
    _, inventory = rich
    slide = SlidePlan(
        pattern="cards",
        title="Three",
        items=[PlanItem(heading=f"A{n}", text=f"T{n}") for n in (1, 2, 3)],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    room = max(
        (group.count for group in choice.pattern.groups),
        default=len(choice.pattern.zones),
    )
    assert room >= 3


def test_a_template_with_no_design_system_never_composes(rich):
    raw, inventory = rich
    without = inventory.model_copy(
        update={
            "design_system": None,
            "patterns": [p for p in inventory.patterns if p.source != "composed"],
        }
    )
    slide = SlidePlan(pattern="content", title="T", bullets=["a", "b", "c"])

    choice = choose(without, slide, resolve(without, slide).pattern)

    assert not choice.composed


# -- an intent the content cannot express is honoured (D9) --------------------


def test_asking_for_an_agenda_gives_an_agenda(rich):
    """Nothing in four short lines says "agenda" rather than "card row", so the
    ask is the only thing that can. Without this the summary slide of every
    deck came out as cards — or, on a poor template, empty.
    """
    _, inventory = rich
    slide = SlidePlan(
        pattern="agenda",
        title="Sommaire",
        bullets=[f"Partie {n}" for n in range(1, 5)],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    assert choice.pattern.intent == "agenda"
    # The bullets are moved into the items the agenda reads, not dropped.
    assert len(choice.slide.items) == 4


def test_an_intent_the_content_can_express_is_still_decided_by_the_content(rich):
    """`cards` is inferable, so the content keeps the last word (D5)."""
    _, inventory = rich
    slide = SlidePlan(
        pattern="cards",
        title="Chiffres",
        items=[PlanItem(number=f"{n} 200", heading=f"Axe {n}") for n in (1, 2, 3)],
    )

    choice = choose(inventory, slide, resolve(inventory, slide).pattern)

    assert choice.composed
    # Bare figures are a stat band; the same slide written in percentages
    # would be progress bars. Either way the CONTENT decided, not the ask.
    assert "stat_band" in choice.pattern.id
