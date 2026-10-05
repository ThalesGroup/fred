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

"""The deck assigner: kind inference, the fit check, the deck rules and the
problems it reports instead of substituting a slide."""

from __future__ import annotations

from typing import Any, List

from builder_decks import build_showcase_template
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.assign import assign, infer_kinds, misfit
from fred_capability_ppt_filler.builder.models import (
    Box,
    Pattern,
    PatternOverride,
    RepeatGroup,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.overrides import apply_overrides
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanColumn,
    PlanItem,
    SlidePlan,
    zone_summary,
)
from fred_capability_ppt_filler.builder.render import _assign_text
from pptx.util import Inches

_analysed = analyze_template(build_showcase_template()).inventory
assert _analysed is not None
INVENTORY: TemplateInventory = _analysed
COVER = SlidePlan(title="Kick-off", subtitle="Team")


def _pattern(label: str) -> Pattern:
    return next(p for p in INVENTORY.patterns if p.label == label)


def _plan(*slides: Any) -> DeckPlan:
    return DeckPlan(
        slides=[
            s if isinstance(s, SlidePlan) else SlidePlan.model_validate(s)
            for s in slides
        ]
    )


def _labels(inventory: TemplateInventory, *slides: Any) -> List[str]:
    assignment = assign(inventory, _plan(*slides))
    assert not assignment.problems, [p.as_dict() for p in assignment.problems]
    return [p.label if p else "-" for p in assignment.patterns]


def _title_zone() -> Zone:
    return Zone(
        key="ph:0",
        role="title",
        box=Box(x=0, y=0, w=900, h=100),
        font_pt=32.0,
        chars_per_line=60,
        max_lines=1,
    )


def _body_zone(key: str = "ph:1", chars: int = 300) -> Zone:
    return Zone(
        key=key,
        role="body",
        box=Box(x=0, y=200, w=900, h=600),
        font_pt=18.0,
        chars_per_line=chars // 8,
        max_lines=8,
    )


def _inventory(*patterns: Pattern) -> TemplateInventory:
    return TemplateInventory(
        slide_width=Inches(13.333).emu,
        slide_height=Inches(7.5).emu,
        patterns=list(patterns),
    )


def _bullets(pid: str, label: str, source: str = "layout") -> Pattern:
    return Pattern(
        id=pid,
        source=source,  # type: ignore[arg-type]
        source_index=int(pid.split(":")[1]),
        name=label,
        label=label,
        kind="bullets",
        zones=[_title_zone(), _body_zone()],
    )


# --- kind inference -------------------------------------------------------------------------


def test_kind_is_inferred_from_the_shape_of_the_content():
    def first(**fields: Any) -> str:
        return infer_kinds(SlidePlan(**fields))[0]

    assert (
        first(title="KPIs", items=[PlanItem(number="42%", label="Margin")]) == "figures"
    )
    assert (
        first(title="Plan", items=[PlanItem(number="1", heading="Go", text="x")])
        == "process"
    )
    assert (
        first(title="History", items=[PlanItem(number="2024", heading="x")])
        == "timeline"
    )
    assert (
        first(title="Topics", items=[PlanItem(heading="A"), PlanItem(heading="B")])
        == "agenda"
    )
    assert (
        first(title="Options", columns=[PlanColumn(bullets=["a"])] * 2) == "two_columns"
    )
    assert (
        first(
            title="A vs B", columns=[PlanColumn(heading="A"), PlanColumn(heading="B")]
        )
        == "comparison"
    )
    assert first(title="Site", image="doc-1") == "image_text"
    assert first(title="Points", bullets=["a"]) == "bullets"
    assert first(title="Part one") == "section"
    assert first(title="Merci") == "closing"
    # A title naming a kind breaks the tie when the content suits it.
    assert first(title="Sommaire", bullets=["a"]) == "bullets"


# --- fit check: the pattern is chosen for the content it is given ---------------------------


def _cards_inventory() -> TemplateInventory:
    """Two cards patterns: the first shows only a description, the second a
    heading too - the shape of the real corporate template."""

    def group(roles, key) -> RepeatGroup:
        return RepeatGroup(
            key=key,
            count=3,
            item_zones=roles,
            item_keys=[f"{key}/{i}" for i in range(3)],
            items=[
                [
                    Zone(
                        key=f"{key}/{i}/{role}",
                        role=role,
                        box=Box(x=i * 300, y=300, w=280, h=200),
                        font_pt=14.0,
                        chars_per_line=26,
                        max_lines=3,
                    )
                    for role in roles
                ]
                for i in range(3)
            ],
        )

    def cards(pid: str, label: str, roles: list) -> Pattern:
        return Pattern(
            id=pid,
            source="slide",
            source_index=int(pid.split(":")[1]),
            name=label,
            label=label,
            kind="cards",
            zones=[_title_zone()],
            groups=[group(roles, f"g{pid}")],
        )

    return _inventory(
        cards("slide:1", "Text cards", ["body"]),
        cards("slide:2", "Titled cards", ["heading", "body"]),
    )


def test_cards_with_headings_skip_the_pattern_that_cannot_show_them():
    slide = SlidePlan(
        title="Three axes",
        kind="cards",
        items=[PlanItem(heading="Near", text="Close to clients")] * 3,
    )
    assert _labels(_cards_inventory(), slide) == ["Titled cards"]


def test_a_pattern_without_headings_still_wins_when_the_plan_has_none():
    slide = SlidePlan(
        title="Three axes", kind="cards", items=[PlanItem(text="Close")] * 3
    )
    assert _labels(_cards_inventory(), slide) == ["Text cards"]


def test_an_image_pattern_is_not_chosen_for_a_plan_without_images():
    """Every unfilled picture zone is a hole on the finished slide."""
    plain = _bullets("layout:1", "Plain")
    imaged = plain.model_copy(
        update={
            "id": "slide:99",
            "source": "slide",
            "label": "Photos",
            "zones": plain.zones
            + [
                Zone(
                    key=f"sp:{i}", role="image", box=Box(x=i * 300, y=400, w=280, h=300)
                )
                for i in range(4)
            ],
        }
    )
    inventory = _inventory(imaged, plain)
    slide = SlidePlan(
        title="Method", bullets=["Frame", "Build", "Measure"], kind="bullets"
    )
    assert _labels(inventory, slide) == ["Plain"]
    assert _labels(inventory, slide.model_copy(update={"image": "doc-1"})) == ["Photos"]


def test_a_pattern_that_would_truncate_is_not_a_candidate():
    plain = _bullets("layout:1", "Plain")
    narrow = _bullets("slide:98", "Narrow", source="slide")
    narrow.zones[1].chars_per_line = 3
    slide = SlidePlan(title="Detail", bullets=["A sentence far longer than twenty"] * 4)
    # The example slide would win on preference, but it would cut the text.
    assert _labels(_inventory(narrow, plain), slide) == ["Plain"]


def test_an_example_slide_is_preferred_over_a_layout_that_fits_as_well():
    slide = SlidePlan(title="Points", bullets=["a", "b"], kind="bullets")
    layout = _bullets("layout:1", "Layout")
    example = _bullets("slide:7", "Example", source="slide")
    assert _labels(_inventory(layout, example), slide) == ["Example"]


# --- deck rules -------------------------------------------------------------------------------


def test_the_cover_is_used_once_and_only_first():
    labels = _labels(
        INVENTORY,
        COVER,
        {"title": "Part one", "subtitle": "Why"},
        {"title": "Points", "bullets": ["a"]},
    )
    assert labels[0] == "Title Slide"
    assert "Title Slide" not in labels[1:]


def test_the_first_slide_must_fit_the_cover():
    assignment = assign(
        INVENTORY,
        _plan(
            {"title": "Topics", "items": [{"heading": "A"}, {"heading": "B"}]}, COVER
        ),
    )
    (problem,) = assignment.problems
    assert problem.index == 1 and assignment.patterns == []
    assert "always the template's cover" in problem.problem
    assert any("add a cover slide" in o for o in problem.options)


def test_a_later_cover_is_built_from_its_content_and_the_swap_is_named():
    assignment = assign(INVENTORY, _plan(COVER, {"title": "Again", "kind": "cover"}))
    assert not assignment.problems
    assert [p.kind for p in assignment.patterns if p] == ["cover", "section"]
    assert (
        "instead of 'cover' (only the first slide can be the cover)"
        in (assignment.notes[0])
    )


def _with_closing() -> TemplateInventory:
    closing = Pattern(
        id="slide:90",
        source="slide",
        source_index=90,
        name="Merci",
        label="Merci",
        kind="closing",
    )
    return INVENTORY.model_copy(update={"patterns": INVENTORY.patterns + [closing]})


def test_closing_is_used_at_most_once_and_only_last():
    inventory = _with_closing()
    labels = _labels(
        inventory, COVER, {"title": "Points", "bullets": ["a"]}, {"title": "Merci"}
    )
    assert labels[-1] == "Merci"
    # A closing word in the middle of the deck is never the closing slide.
    labels = _labels(
        inventory, COVER, {"title": "Questions"}, {"title": "Points", "bullets": ["a"]}
    )
    assert "Merci" not in labels

    assignment = assign(
        inventory,
        _plan(
            COVER,
            {"kind": "closing", "title": "Merci"},
            {"title": "Points", "bullets": ["a"]},
        ),
    )
    assert not assignment.problems
    assert assignment.patterns[1] and assignment.patterns[1].label != "Merci"
    assert "a closing slide can only end the deck" in assignment.notes[0]


def test_a_fixed_closing_slide_takes_no_content_so_the_content_decides():
    assignment = assign(
        _with_closing(),
        _plan(
            COVER, {"kind": "closing", "title": "Contact", "bullets": ["jane@x.com"]}
        ),
    )
    assert not assignment.problems
    assert assignment.patterns[1] and assignment.patterns[1].kind == "bullets"
    assert "no 'closing' slide holds this content" in assignment.notes[0]


def test_no_three_identical_slides_in_a_row_when_an_alternative_fits():
    inventory = _inventory(_bullets("layout:1", "A"), _bullets("layout:2", "B"))
    slides = [SlidePlan(title=f"P{i}", bullets=["x"]) for i in range(5)]
    labels = _labels(inventory, *slides)
    assert all(not (labels[i] == labels[i + 1] == labels[i + 2]) for i in range(3)), (
        labels
    )


def test_repetition_is_allowed_and_reported_on_a_one_archetype_template():
    inventory = _inventory(_bullets("layout:1", "Only"))
    assignment = assign(
        inventory, _plan(*[SlidePlan(title=f"P{i}", bullets=["x"]) for i in range(4)])
    )
    assert not assignment.problems
    assert [p.label for p in assignment.patterns if p] == ["Only"] * 4
    assert assignment.notes and "Slides 1 to 3" in assignment.notes[0]


def test_invalid_entries_get_no_pattern_and_do_not_shift_the_rules():
    plan = DeckPlan(
        slides=[
            SlidePlan.model_validate("junk"),
            COVER,
            SlidePlan(title="P", bullets=["x"]),
        ]
    )
    assignment = assign(INVENTORY, plan)
    assert not assignment.problems
    assert assignment.patterns[0] is None
    assert assignment.patterns[1] is not None and assignment.patterns[1].kind == "cover"


# --- no silent fallback -----------------------------------------------------------------------


def test_items_over_capacity_are_a_problem_with_trim_and_split_options():
    steps = [PlanItem(number=str(i), heading=f"S{i}", text="x") for i in range(7)]
    assignment = assign(
        INVENTORY, _plan(COVER, SlidePlan(title="How", kind="process", items=steps))
    )
    (problem,) = assignment.problems
    assert problem.as_dict()["slide"] == 2
    assert (
        problem.problem == "items: 7 given; the largest slide of this template holds 6"
    )
    assert problem.options[:2] == ["trim to 6 items", "split the items over two slides"]


def test_a_kind_the_template_lacks_is_replaced_by_the_content_shape():
    slide = SlidePlan(title="Points", bullets=["a", "b"], kind="timeline")
    assignment = assign(INVENTORY, _plan(COVER, slide))
    assert not assignment.problems
    assert assignment.patterns[1] and assignment.patterns[1].kind == "bullets"
    assert assignment.notes == [
        "Slide 2: built as 'bullets' instead of 'timeline' "
        "(this template has no 'timeline' slide)."
    ]


def test_a_requested_kind_that_fits_is_kept():
    slide = SlidePlan(title="Points", bullets=["a", "b"], kind="two_columns")
    assignment = assign(INVENTORY, _plan(COVER, slide))
    assert assignment.patterns[1] and assignment.patterns[1].kind == "two_columns"
    assert not assignment.notes


def test_a_text_too_long_everywhere_names_the_element_and_its_measured_limit():
    slide = SlidePlan(title="Detail", bullets=["short", "word " * 199 + "word"])
    (problem,) = assign(
        _inventory(_bullets("layout:1", "Plain")), _plan(slide)
    ).problems
    assert problem.problem == (
        "closest fit, a 'bullets' slide: bullets: 2 entries, 1004 chars; this zone "
        "holds ≈37 chars × 8 lines (longest: bullets[1], 999 chars)"
    )
    assert any(o.startswith("keep bullets within") for o in problem.options)


def test_one_title_too_long_is_named_with_the_room_it_has():
    slide = SlidePlan(title="T" * 400, subtitle="Team")
    (problem,) = assign(INVENTORY, _plan(slide)).problems
    assert "title is 400 chars; this zone holds ≈" in problem.problem
    assert any(o.startswith("shorten title to ≈") for o in problem.options)


def test_columns_beyond_every_pattern_are_a_problem_not_a_lost_column():
    columns = [PlanColumn(heading=f"C{i}", bullets=["text"]) for i in range(9)]
    (problem,) = assign(
        INVENTORY, _plan(COVER, SlidePlan(title="T", columns=columns))
    ).problems
    assert "columns: 9 given, max 2" in problem.problem
    assert any("columns.bullets×2" in o for o in problem.options)


def test_excluded_and_rekinded_patterns_follow_the_overrides():
    process = _pattern("Process")
    effective, _ = apply_overrides(
        INVENTORY,
        [
            PatternOverride(pattern_id=process.id, included=False),
            PatternOverride(pattern_id=_pattern("Agenda").id, kind="process"),
        ],
    )
    steps = [PlanItem(number=str(i), heading=f"S{i}") for i in range(1, 4)]
    labels = _labels(
        effective, COVER, SlidePlan(title="How", kind="process", items=steps)
    )
    assert labels[1] == "Agenda"


def test_an_empty_slide_in_the_middle_is_a_problem():
    (problem,) = assign(
        INVENTORY, _plan(COVER, {}, {"title": "P", "bullets": ["x"]})
    ).problems
    assert problem.index == 2 and problem.problem == "the slide is empty"


def test_a_subtitle_without_its_zone_leads_the_body_instead_of_failing():
    inventory = _inventory(_bullets("layout:1", "Plain"))
    slide = SlidePlan(title="Why", subtitle="Three reasons", bullets=["a", "b"])
    assert _labels(inventory, slide) == ["Plain"]
    lines = _assign_text(inventory.patterns[0], slide)["ph:1"]
    assert lines[0].text == "Three reasons" and lines[0].heading
    assert [line.source for line in lines] == ["subtitle", "bullets[0]", "bullets[1]"]


def test_step_numbers_need_no_number_zone_but_figures_do():
    process = _pattern("Process")
    process = process.model_copy(
        update={
            "groups": [
                g.model_copy(
                    update={
                        "item_zones": [r for r in g.item_zones if r != "number"],
                        "items": [
                            [z for z in item if z.role != "number"] for item in g.items
                        ],
                    }
                )
                for g in process.groups
            ]
        }
    )
    steps = [PlanItem(number=f"0{i}", heading=f"S{i}") for i in range(1, 4)]
    assert not misfit(process, SlidePlan(title="How", items=steps), (1, 1))[0]
    figures = [PlanItem(number="42%", heading="Margin")] * 3
    reasons, _ = misfit(process, SlidePlan(title="KPIs", items=figures), (1, 1))
    assert [r.text for r in reasons] == [
        "items' number: this slide has no place for it"
    ]


def test_a_cover_with_only_a_heading_is_described_as_taking_the_title():
    """The renderer writes the title there: calling it `columns.heading` sent
    models sending columns to the cover."""
    heading = _title_zone().model_copy(update={"role": "heading"})
    cover = Pattern(
        id="slide:1",
        source="slide",
        source_index=1,
        name="Cover",
        label="Cover",
        kind="cover",
        zones=[heading],
    )
    assert zone_summary(cover) == "title ≈60 chars"
    assert _labels(_inventory(cover), SlidePlan(title="Kick-off")) == ["Cover"]
