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

"""Rendering a plan on the synthetic showcase template (and on the reference
corporate template when `PPT_BUILDER_REFERENCE_TEMPLATE` points at it)."""

from __future__ import annotations

import io
import math
import os
from typing import Any, cast

import pytest
from builder_decks import (
    FOOTER,
    add_cover_photo_slide,
    build_showcase_template,
    build_slides,
    build_spaced_template,
)
from deck_builders import png_bytes
from fred_capability_ppt_filler import text_metrics
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.lexicon import is_sample_text
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
    best_for_intent,
)
from fred_capability_ppt_filler.builder.render import (
    MIN_FONT_SCALE,
    RenderError,
    _assign_text,
    _covered,
    _fit,
    _Line,
    _unused_item_fields,
    render_deck,
)
from fred_capability_ppt_filler.builder.tools import catalogue
from fred_capability_ppt_filler.images import prepare_picture
from fred_capability_ppt_filler.traversal import walk_shapes
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

TEMPLATE = build_showcase_template()
_analysed = analyze_template(TEMPLATE).inventory
assert _analysed is not None
INVENTORY: TemplateInventory = _analysed


def _pattern(label: str):
    return next(p for p in INVENTORY.patterns if p.label == label)


def _title(slide) -> str:
    return cast(Any, slide.shapes.title).text


def _texts(slide) -> list[str]:
    out = []
    for placed in walk_shapes(slide.shapes):
        shape = cast(Any, placed.shape)
        if getattr(shape, "has_text_frame", False):
            text = shape.text_frame.text.strip()
            if text and text != FOOTER:
                out.append(text)
    return out


def _pictures(slide) -> int:
    return sum(
        1
        for p in walk_shapes(slide.shapes)
        if cast(Any, p.shape).shape_type == MSO_SHAPE_TYPE.PICTURE
    )


def _render(*slides: SlidePlan, images=None):
    result = render_deck(TEMPLATE, INVENTORY, DeckPlan(slides=list(slides)), images)
    return result, Presentation(io.BytesIO(result.pptx))


def test_layout_pattern_fills_title_and_levelled_bullets():
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Title and Content").id,
            title="Quarterly results",
            bullets=[
                "Revenue up **12 %**",
                "- Europe +8 %",
                "- Asia +20 %",
                "Costs flat",
            ],
        )
    )
    assert result.warnings == []
    (slide,) = deck.slides
    assert _title(slide) == "Quarterly results"
    body = cast(Any, slide.placeholders[1]).text_frame
    assert [p.text for p in body.paragraphs] == [
        "Revenue up 12 %",
        "Europe +8 %",
        "Asia +20 %",
        "Costs flat",
    ]
    assert [p.level for p in body.paragraphs] == [0, 1, 1, 0]
    bold_runs = [r for p in body.paragraphs for r in p.runs if r.font.bold]
    assert [r.text for r in bold_runs] == ["12 %"]


def test_example_slides_are_duplicated_in_plan_order_and_originals_dropped():
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Key figures").id,
            title="KPIs",
            items=[
                PlanItem(number="42%", label="Margin"),
                PlanItem(number="7", label="Sites"),
            ],
        ),
        SlidePlan(
            pattern=_pattern("Agenda").id,
            title="Agenda",
            items=[
                PlanItem(heading="Context"),
                PlanItem(heading="Plan"),
                PlanItem(heading="Next steps"),
            ],
        ),
        SlidePlan(
            pattern=_pattern("Title and Content").id,
            title="Closing",
            bullets=["Thanks"],
        ),
    )
    assert result.slide_count == 3
    assert len(deck.slides) == 3
    kpi, agenda, closing = deck.slides
    assert _title(kpi) == "KPIs"
    assert set(_texts(kpi)) == {"KPIs", "42%", "Margin", "7", "Sites"}
    # Two of the four cards were not used: their groups are gone, and so are the
    # loose icons drawn over them; the icons of the used cards stay.
    assert sum(1 for s in kpi.shapes if s.shape_type == MSO_SHAPE_TYPE.GROUP) == 2
    assert _pictures(kpi) == 2
    assert set(_texts(agenda)) == {
        "Agenda",
        "01",
        "Context",
        "02",
        "Plan",
        "03",
        "Next steps",
    }
    assert _title(closing) == "Closing"


def test_no_sample_text_survives_rendering():
    _, deck = _render(
        SlidePlan(
            pattern=_pattern("Process").id,
            title="How",
            items=[PlanItem(heading="Discover")],
        ),
        SlidePlan(pattern=_pattern("Free text").id, title="Notes"),
        SlidePlan(
            pattern=_pattern("Team").id,
            title="Who",
            items=[PlanItem(heading="CTO", label="Ada")],
        ),
    )
    for slide in deck.slides:
        for text in _texts(slide):
            assert not is_sample_text(text), text


def test_shared_image_parts_keep_the_file_small():
    plan = DeckPlan(
        slides=[
            SlidePlan(
                pattern=_pattern("Key figures").id,
                title=f"KPI {i}",
                items=[PlanItem(number="1", label="x")] * 4,
            )
            for i in range(10)
        ]
    )
    result = render_deck(TEMPLATE, INVENTORY, plan)
    assert len(result.pptx) < len(TEMPLATE) * 1.2
    deck = Presentation(io.BytesIO(result.pptx))
    assert len(deck.slides) == 10
    assert all(_pictures(slide) == 4 for slide in deck.slides)


def test_narrow_item_box_is_widened_in_group_units():
    scaled = _pattern("Scaled figures")
    _, deck = _render(
        SlidePlan(
            pattern=scaled.id,
            title="Scaled",
            items=[PlanItem(number="1%", label="Wide label now")] * 3,
        )
    )
    labels = [
        p
        for p in walk_shapes(deck.slides[0].shapes)
        if cast(Any, p.shape).has_text_frame
        and cast(Any, p.shape).text_frame.text == "Wide label now"
    ]
    assert len(labels) == 3
    widths = sorted(p.width for p in labels)
    # Absolute widths within 5 % of each other: the narrow box caught up.
    assert widths[-1] - widths[0] < widths[-1] * 0.05


def test_notes_are_skipped_when_the_notes_slide_has_no_body():
    silent = _pattern("Silent notes")
    result, deck = _render(
        SlidePlan(pattern=silent.id, title="Quiet", bullets=["a"], notes="ignored")
    )
    assert len(deck.slides) == 1
    assert result.warnings == []


def test_columns_without_enough_bodies_are_reported():
    result, _ = _render(
        SlidePlan(
            pattern=_pattern("Title and Content").id,
            title="Three columns",
            columns=[
                PlanColumn(bullets=["a"]),
                PlanColumn(bullets=["b"]),
                PlanColumn(bullets=["c"]),
            ],
        )
    )
    assert any("no place for column 2, column 3" in w for w in result.warnings)


def test_columns_fill_two_content_and_comparison_headings():
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Comparison").id,
            title="Before / after",
            columns=[
                PlanColumn(heading="Before", bullets=["slow"]),
                PlanColumn(heading="After", bullets=["fast"]),
            ],
        ),
        SlidePlan(
            pattern=_pattern("Two Content").id,
            title="Options",
            bullets=["a", "b", "c", "d"],
        ),
    )
    comparison, two = deck.slides
    texts = _texts(comparison)
    assert {"Before", "After", "slow", "fast", "Before / after"} <= set(texts)
    bodies = [
        cast(Any, s) for s in two.placeholders if s.placeholder_format.idx in (1, 2)
    ]
    assert sorted(len(b.text_frame.paragraphs) for b in bodies) == [2, 2]


def test_overflow_shrinks_then_truncates_with_a_warning():
    long_bullets = [
        "This is a deliberately verbose bullet that keeps going on and on " * 3
    ] * 8
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Title and Content").id, title="Long", bullets=long_bullets
        )
    )
    body = cast(Any, deck.slides[0].placeholders[1])
    # The body inherits 32 pt; the shrink is written as explicit run sizes.
    sizes = {run.font.size.pt for p in body.text_frame.paragraphs for run in p.runs}
    assert sizes and max(sizes) < 32

    very_long = ["word " * 200] * 40
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Title and Content").id,
            title="Very long",
            bullets=very_long,
        )
    )
    assert any("truncated" in w for w in result.warnings)
    body = cast(Any, deck.slides[0].placeholders[1])
    assert len(body.text_frame.paragraphs) < 40


def test_image_zone_filled_from_prepared_bytes_or_removed_when_empty():
    photo = _pattern("Photo")
    prepared = {"doc-1": prepare_picture(png_bytes(30, 20, "blue"))}
    result, deck = _render(
        SlidePlan(pattern=photo.id, title="Site", image="doc-1"), images=prepared
    )
    assert result.warnings == []
    assert _pictures(deck.slides[0]) == 1

    caption = _pattern("Picture with Caption")
    _, deck = _render(
        SlidePlan(pattern=caption.id, title="No picture", bullets=["text only"])
    )
    slide = deck.slides[0]
    assert all(p.placeholder_format.type.name != "PICTURE" for p in slide.placeholders)

    result, deck = _render(
        SlidePlan(pattern=photo.id, title="Site", image="doc-missing"),
        images=prepared,
    )
    assert any("'doc-missing' is not a usable image" in w for w in result.warnings)
    assert _pictures(deck.slides[0]) == 1  # the template's own picture stays


def test_intent_names_resolve_and_degrade_with_a_warning():
    excluded = [
        PatternOverride(pattern_id=p.id, included=False)
        for p in INVENTORY.patterns
        if p.intent in ("two_columns", "comparison")
    ]
    effective, _ = apply_overrides(INVENTORY, excluded)
    result = render_deck(
        TEMPLATE,
        effective,
        DeckPlan(
            slides=[SlidePlan(pattern="two_columns", title="T", bullets=["a", "b"])]
        ),
    )
    assert (
        len(result.warnings) == 1 and "no 'two_columns' pattern" in result.warnings[0]
    )
    deck = Presentation(io.BytesIO(result.pptx))
    assert _title(deck.slides[0]) == "T"

    result = render_deck(
        TEMPLATE,
        INVENTORY,
        DeckPlan(slides=[SlidePlan(pattern="agenda", items=[PlanItem(heading="One")])]),
    )
    assert result.warnings == []


def test_unknown_or_excluded_patterns_fall_back_on_the_slide_content():
    result, deck = _render(
        SlidePlan(pattern="slide:999", title="x", bullets=["a", "b"])
    )
    assert len(deck.slides) == 1
    assert "'slide:999' is not a pattern of this template" in result.warnings[0]
    assert "(content)" in result.warnings[0] or "content" in result.warnings[0]

    chart = next(p for p in INVENTORY.patterns if p.exclusion_reason == "chart")
    result, _ = _render(SlidePlan(pattern=chart.id, title="x", bullets=["a"]))
    assert "is excluded from this template" in result.warnings[0]

    # A slide number the model mistook for an id is honoured when it fits.
    agenda = _pattern("Agenda")
    result, _ = _render(
        SlidePlan(
            pattern=f"slide:{agenda.source_index}", items=[PlanItem(heading="One")]
        )
    )
    assert f"used '{agenda.id}'" in result.warnings[0]


def test_non_slide_entries_are_skipped_and_an_all_invalid_plan_is_an_error():
    result, deck = _render(
        SlidePlan(pattern="content", title="Kept"), SlidePlan.model_validate("junk")
    )
    assert len(deck.slides) == 1
    assert "not a slide object" in result.warnings[0]
    with pytest.raises(RenderError, match="no usable slide"):
        _render(SlidePlan.model_validate("junk"))


def test_figures_never_break_and_long_words_shrink_instead_of_splitting():
    kpi = _pattern("Key figures")
    _, deck = _render(
        SlidePlan(
            pattern=kpi.id,
            title="KPIs",
            items=[PlanItem(number="1 200", label="Collaborateurs")],
        )
    )
    figures = [
        cast(Any, p.shape).text_frame.text
        for p in walk_shapes(deck.slides[0].shapes)
        if cast(Any, p.shape).has_text_frame
        and "200" in cast(Any, p.shape).text_frame.text
    ]
    assert figures == ["1\u00a0200"]


def test_fixed_pattern_is_copied_verbatim_and_notes_are_written():
    divider = _pattern("Motif")
    _, deck = _render(SlidePlan(pattern=divider.id, title="ignored", notes="Say hello"))
    slide = deck.slides[0]
    assert _title(slide) == "Motif"
    assert cast(Any, slide.notes_slide.notes_text_frame).text == "Say hello"


def test_content_the_pattern_cannot_show_is_reported():
    # The agent only learns what the deck lost from these warnings.
    result, _ = _render(
        SlidePlan(
            pattern=_pattern("Title Only").id, title="Spain", bullets=["55 years"]
        ),
        SlidePlan(
            pattern=_pattern("Key figures").id,
            title="Figures",
            items=[PlanItem(number="1 600", label="People", text="Across 5 sites")],
        ),
        SlidePlan(pattern=_pattern("Motif").id, title="Merci"),
        SlidePlan(pattern=_pattern("Motif").id, title="Motif"),
        SlidePlan(
            pattern=_pattern("Free text").id,
            title="No list",
            items=[PlanItem(heading="x")],
        ),
    )
    warnings = " ".join(result.warnings)
    assert "Slide 1: 'Title Only' has no place for bullets" in warnings
    assert "Slide 2: 'Key figures' has no place for items' text" in warnings
    assert "Slide 3: 'Motif' is a fixed slide used as is" in warnings
    assert (
        "Slide 4:" not in warnings
    )  # a fixed slide named by its own title lost nothing
    assert "Slide 5: 'Free text' has no place for items" in warnings


def test_zone_role_names_used_as_plan_keys_still_fill_the_zones():
    steps = SlidePlan.model_validate(
        {
            "pattern": _pattern("Process").id,
            "title": "Plan",
            "items": [{"number": "1", "heading": "Start", "body": "Kick-off meeting"}],
        }
    )
    content = SlidePlan.model_validate(
        {
            "pattern": _pattern("Title and Content").id,
            "title": "Plan",
            "body": ["one", "two"],
        }
    )
    result, deck = _render(steps, content)
    assert result.warnings == []
    assert "Kick-off meeting" in _texts(deck.slides[0])
    assert any("one" in text and "two" in text for text in _texts(deck.slides[1]))
    assert PlanItem.model_validate({"text": "kept", "body": "alias"}).text == "kept"


def test_one_line_heading_shrinks_then_asks_to_be_shortened():
    process = _pattern("Process")
    result, deck = _render(
        SlidePlan(
            pattern=process.id,
            title="Plan",
            items=[
                PlanItem(heading="Kick-off", text="a"),
                PlanItem(heading="A heading far too long for its one line", text="b"),
            ],
        )
    )
    long_heading = [w for w in result.warnings if "does not fit on one line" in w]
    assert len(long_heading) == 1 and "A heading far too long" in long_heading[0]

    # A label with nothing under it may take a second line.
    figures, _ = _render(
        SlidePlan(
            pattern=_pattern("Key figures").id,
            title="Figures",
            items=[
                PlanItem(number="12", label="A label far too long for its one line")
            ],
        )
    )
    assert not [w for w in figures.warnings if "one line" in w]


def test_truncation_drops_the_lines_the_measured_capacity_cannot_hold():
    # Capitals run ~20 % wider than the average character: costing the kept
    # lines in characters shipped a slide with twice its text in it.
    shouting = ["MODERNISATION DES SYSTEMES DE COMMANDEMENT"] * 12
    result, deck = _render(
        SlidePlan(
            pattern=_pattern("Title and Content").id, title="Overflow", bullets=shouting
        )
    )
    assert any("truncated" in w for w in result.warnings)
    body = cast(Any, deck.slides[0].placeholders[1]).text_frame
    kept = [p.text for p in body.paragraphs if p.text.strip()]
    assert 0 < len(kept) < len(shouting)

    # What is left must fit the box at the smallest font the renderer uses,
    # measured here rather than counted in characters.
    zone = next(z for z in _pattern("Title and Content").zones if z.role == "body")
    assert zone.font_pt and zone.max_lines
    line_pt = zone.box.w / 1000 * INVENTORY.slide_width / 914400 * 72
    em_per_line = line_pt / (zone.font_pt * MIN_FONT_SCALE)
    rows = sum(math.ceil(text_metrics.width_em(text) / em_per_line) for text in kept)
    assert rows <= zone.max_lines / MIN_FONT_SCALE


def test_long_item_text_in_a_one_line_box_wraps_without_a_warning():
    # Only headings and labels are held to one line; a description may wrap.
    process = _pattern("Process")
    one_line = process.model_copy(deep=True)
    for item in one_line.groups[0].items:
        for zone in item:
            if zone.role == "body":
                zone.max_lines = 1
    inventory = INVENTORY.model_copy(
        update={
            "patterns": [
                one_line if p.id == process.id else p for p in INVENTORY.patterns
            ]
        }
    )
    result = render_deck(
        TEMPLATE,
        inventory,
        DeckPlan(
            slides=[
                SlidePlan(
                    pattern=process.id,
                    title="Plan",
                    items=[
                        PlanItem(
                            heading="Start",
                            text="A description written in full sentences, " * 2,
                        )
                    ],
                )
            ]
        ),
    )
    assert not [w for w in result.warnings if "one line" in w]


def _zone(key: str, role: str, y: int) -> Zone:
    return Zone(key=key, role=role, box=Box(x=50, y=y, w=900, h=60))  # type: ignore[arg-type]


def test_contact_bullets_skip_zones_already_filled():
    contact = Pattern(
        id="layout:0",
        source="layout",
        source_index=0,
        name="Contact",
        label="Contact",
        intent="contact",
        zones=[
            _zone("ph:0", "title", 50),
            _zone("ph:1", "subtitle", 150),
            _zone("ph:2", "body", 250),
            _zone("ph:3", "body", 350),
        ],
    )
    lost: list[str] = []
    out = _assign_text(
        contact,
        SlidePlan(title="Jane", subtitle="CEO", bullets=["jane@x.io", "+33 1"]),
        lost,
    )
    assert lost == []
    assert [out[k][0].text for k in ("ph:1", "ph:2", "ph:3")] == [
        "CEO",
        "jane@x.io",
        "+33 1",
    ]


def test_a_lost_subtitle_is_reported_as_the_subtitle():
    lost: list[str] = []
    _assign_text(
        _pattern("Two columns"),
        SlidePlan(
            title="T",
            subtitle="S",
            columns=[PlanColumn(bullets=["a"]), PlanColumn(bullets=["b"])],
        ),
        lost,
    )
    assert lost == ["subtitle"]


def test_items_shown_by_another_group_of_the_slide_are_not_reported():
    figures = _pattern("Key figures").groups[0]  # number, label
    steps = _pattern("Process").groups[0]  # number, heading, body
    item = PlanItem(number="1", label="People", heading="Start", text="Kick-off")
    plan = SlidePlan(items=[item])
    assert _unused_item_fields([figures, steps], plan) == []
    assert _unused_item_fields([figures], plan) == ["items' heading", "items' text"]


def test_catalogue_names_plan_fields_and_offers_nothing_on_fixed_slides():
    lines = {line.split(" ")[1]: line for line in catalogue(INVENTORY).splitlines()}
    assert "items up to 3 [number, heading, text]" in lines[_pattern("Process").id]
    assert "bullets" in lines[_pattern("Title and Content").id]
    assert "no editable zone" in lines[_pattern("Motif").id]
    assert "(preferred)" not in catalogue(
        INVENTORY.model_copy(
            update={
                "patterns": [_pattern("Motif").model_copy(update={"preferred": True})]
            }
        )
    )
    assert "title" not in lines[_pattern("Motif").id].split(":", 1)[1]


def test_fixed_intent_closes_on_a_closing_slide_before_a_preferred_decoration():
    decoration = _pattern("Motif").model_copy(update={"preferred": True})
    closing = decoration.model_copy(
        update={
            "id": "layout:99",
            "label": "Merci",
            "name": "Merci",
            "preferred": False,
        }
    )
    inventory = INVENTORY.model_copy(update={"patterns": [decoration, closing]})
    found = best_for_intent(inventory, "fixed")
    assert found is not None and found.label == "Merci"


def test_preview_copy_widens_one_line_text_the_delivered_deck_keeps():
    # LibreOffice breaks a "do not wrap" box once its substitute font runs wide.
    template = Presentation(io.BytesIO(TEMPLATE))
    layout = next(lay for lay in template.slide_layouts if lay.name == "Title Only")
    scratch = template.slides.add_slide(layout)
    box = scratch.shapes.add_textbox(Inches(4), Inches(3), Inches(2), Inches(1))
    box.text_frame.text = "Merci"
    box.text_frame.paragraphs[0].runs[0].font.size = Pt(60)
    body = box.text_frame._txBody.find(qn("a:bodyPr"))
    body.set("wrap", "none")
    box.text_frame.paragraphs[0]._p.get_or_add_pPr().set("algn", "ctr")
    layout.shapes._spTree.append(box._element)
    buffer = io.BytesIO()
    template.save(buffer)

    result = render_deck(
        buffer.getvalue(),
        INVENTORY,
        DeckPlan(slides=[SlidePlan(pattern=_pattern("Title Only").id, title="End")]),
    )

    def merci_box(pptx: bytes):
        deck = Presentation(io.BytesIO(pptx))
        shape = next(
            s
            for s in deck.slides[0].slide_layout.shapes
            if s.has_text_frame and cast(Any, s).text_frame.text == "Merci"
        )
        return shape.left, shape.width

    assert merci_box(result.pptx) == (Inches(4), Inches(2))
    left, width = merci_box(result.preview_pptx)
    assert width > Inches(2)
    assert left + width // 2 == Inches(5)  # still centred where the designer put it


REFERENCE = os.environ.get("PPT_BUILDER_REFERENCE_TEMPLATE")


@pytest.mark.skipif(
    not REFERENCE or not os.path.exists(REFERENCE or ""),
    reason="reference template not provided",
)
def test_reference_template_renders_a_full_deck():
    template = open(REFERENCE, "rb").read()  # type: ignore[arg-type]
    inventory = analyze_template(template).inventory
    assert inventory is not None
    by_label: dict[str, Any] = {}
    for pattern in inventory.patterns:
        by_label.setdefault(pattern.label, pattern)
    plan = DeckPlan(
        slides=[
            SlidePlan(
                pattern="title",
                title="Plan de transformation",
                subtitle="Comité de direction",
            ),
            SlidePlan(
                pattern=by_label["SOMMAIRE"].id,
                title="Sommaire",
                items=[
                    PlanItem(heading=h)
                    for h in ("Contexte", "Ambition", "Feuille de route")
                ],
            ),
            SlidePlan(pattern="section", title="Contexte"),
            SlidePlan(
                pattern="content",
                title="Constats",
                bullets=["Coûts en hausse", "- +8 % sur un an", "Délais stables"],
            ),
            SlidePlan(
                pattern=by_label["Indicateurs de performance / chiffres clés"].id,
                title="Chiffres clés",
                items=[
                    PlanItem(number="60%", label="Marge"),
                    PlanItem(number="3", label="Sites"),
                ],
            ),
            SlidePlan(
                pattern=by_label["Planche de processus"].id,
                title="Démarche",
                items=[
                    PlanItem(heading="Cadrer", text="Deux semaines"),
                    PlanItem(heading="Construire", text="Un trimestre"),
                    PlanItem(heading="Déployer", text="Progressif"),
                ],
            ),
            SlidePlan(
                pattern="two_columns",
                title="Options",
                columns=[
                    PlanColumn(heading="A", bullets=["rapide"]),
                    PlanColumn(heading="B", bullets=["robuste"]),
                ],
            ),
            SlidePlan(
                pattern="contact",
                title="Nous contacter",
                bullets=[
                    "Jane Doe",
                    "Directrice",
                    "+33 1 00 00 00 00",
                    "jane@example.com",
                ],
            ),
            SlidePlan(pattern="fixed"),
        ]
    )
    result = render_deck(template, inventory, plan)
    deck = Presentation(io.BytesIO(result.pptx))
    assert len(deck.slides) == 9
    contact = deck.slides[7]
    assert {"Jane Doe", "Directrice", "+33 1 00 00 00 00", "jane@example.com"} <= set(
        _texts(contact)
    )
    for slide in deck.slides:
        for text in _texts(slide):
            assert not is_sample_text(text), text
    assert len(result.pptx) < len(template) * 1.1


# --- the room quoted to the agent is the room the renderer enforces ---


def _two_body_pattern(first: int, second: int) -> Pattern:
    return Pattern(
        id="layout:9",
        source="layout",
        source_index=9,
        name="Contact",
        label="Contact",
        intent="contact",
        zones=[
            Zone(
                key=f"ph:{index}",
                role="body",
                box=Box(x=index * 300, y=400, w=280, h=100),
                font_pt=14.0,
                max_chars=chars,
                max_lines=2,
            )
            for index, chars in enumerate((first, second))
        ],
    )


def test_catalogue_quotes_the_tightest_zone_not_the_first():
    """Told the roomiest zone's limit, an agent writes text the narrow ones cut."""
    pattern = _two_body_pattern(36, 22)
    line = catalogue(
        TemplateInventory(slide_width=1, slide_height=1, patterns=[pattern])
    )
    assert "≤22 chars" in line
    assert "≤36 chars" not in line


def test_catalogue_names_columns_when_a_pattern_has_several_bodies():
    """`bullets` fills only the first: naming it that way loses the rest."""
    line = catalogue(
        TemplateInventory(
            slide_width=1, slide_height=1, patterns=[_two_body_pattern(40, 40)]
        )
    )
    assert "columns.bullets×2" in line


def test_catalogue_quotes_no_limit_for_a_box_that_grows_with_its_text():
    pattern = _two_body_pattern(2, 2)
    for zone in pattern.zones:
        zone.grows = True
    line = catalogue(
        TemplateInventory(slide_width=1, slide_height=1, patterns=[pattern])
    )
    assert "chars" not in line


def test_shrinking_text_to_the_floor_is_not_reported_as_truncated():
    """A zone that had to shrink still holds every word: telling the agent it
    was cut sends it rewriting content the reader can see in full."""
    zone = Zone(
        key="ph:1",
        role="body",
        box=Box(x=0, y=0, w=400, h=300),
        font_pt=18.0,
        max_chars=180,
        max_lines=9,
    )
    lines = [
        _Line(
            "Une ligne de texte nettement plus longue que ce que la zone affiche "
            "sans rétrécir la police au plancher"
        )
    ] * 3
    kept, scale, truncated = _fit(zone, lines, Inches(13.333).emu, Inches(7.5).emu)
    assert [line.text for line in kept] == [line.text for line in lines]
    assert not truncated
    assert scale == MIN_FONT_SCALE


def test_a_truncated_zone_is_never_left_empty():
    """A narrow zone used to blank itself rather than keep a cut first line."""
    zone = Zone(
        key="ph:1",
        role="body",
        box=Box(x=0, y=0, w=30, h=20),
        font_pt=18.0,
        max_chars=4,
        max_lines=1,
    )
    kept, _, truncated = _fit(
        zone, [_Line("Innovation durable")], Inches(13.333).emu, Inches(7.5).emu
    )
    assert truncated
    assert kept and kept[0].text.strip()


def test_a_placeholder_that_does_not_wrap_on_its_layout_is_not_truncated():
    """A cloned placeholder carries a bare bodyPr but still draws with the
    layout's rule: reading only the slide's cut text the box grows to hold."""
    inventory = analyze_template(build_spaced_template(space_before_pt=0)).inventory
    assert inventory is not None
    pattern = next(p for p in inventory.patterns if any(z.grows for z in p.zones))
    long_title = "Plan de transformation numérique du groupe à l'horizon 2030"
    result = render_deck(
        build_spaced_template(space_before_pt=0),
        inventory,
        DeckPlan(slides=[SlidePlan(pattern=pattern.id, title=long_title)]),
    )
    deck = Presentation(io.BytesIO(result.pptx))
    assert long_title in _texts(deck.slides[0])
    assert not [w for w in result.warnings if "truncated" in w]


# --- a pattern is chosen for the content it is actually given ---


def _cards_inventory() -> TemplateInventory:
    """Two cards patterns: the first shows only a description, the second a
    heading too — the shape of the real corporate template."""

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
                        max_chars=80,
                        max_lines=3,
                    )
                    for role in roles
                ]
                for i in range(3)
            ],
        )

    title = Zone(
        key="ph:0",
        role="title",
        box=Box(x=0, y=0, w=900, h=100),
        font_pt=32.0,
        max_chars=60,
        max_lines=1,
    )
    return TemplateInventory(
        slide_width=Inches(13.333).emu,
        slide_height=Inches(7.5).emu,
        patterns=[
            Pattern(
                id="slide:1",
                source="slide",
                source_index=1,
                name="Text cards",
                label="Text cards",
                intent="cards",
                zones=[title],
                groups=[group(["body"], "g1")],
            ),
            Pattern(
                id="slide:2",
                source="slide",
                source_index=2,
                name="Titled cards",
                label="Titled cards",
                intent="cards",
                zones=[title],
                groups=[group(["heading", "body"], "g2")],
            ),
        ],
    )


def test_cards_with_headings_skip_the_pattern_that_cannot_show_them():
    """Taking the first pattern of the intent rendered cards with no heading —
    in the worst case, three empty boxes."""
    slide = SlidePlan(
        pattern="cards",
        title="Three axes",
        items=[PlanItem(heading="Near", text="Close to clients")] * 3,
    )
    chosen = best_for_intent(_cards_inventory(), "cards", slide)
    assert chosen is not None and chosen.id == "slide:2"


def test_a_pattern_without_headings_still_wins_when_the_plan_has_none():
    slide = SlidePlan(
        pattern="cards", title="Three axes", items=[PlanItem(text="Close")] * 3
    )
    chosen = best_for_intent(_cards_inventory(), "cards", slide)
    assert chosen is not None and chosen.id == "slide:1"


def test_an_image_pattern_is_not_chosen_for_a_plan_without_images():
    """Every unfilled picture zone is a white hole on the finished slide."""
    plain = _pattern("Title and Content")
    imaged = Pattern(
        id="slide:99",
        source="slide",
        source_index=99,
        name="Photos",
        label="Photos",
        intent=plain.intent,
        zones=plain.zones
        + [
            Zone(key=f"sp:{i}", role="image", box=Box(x=i * 300, y=400, w=280, h=300))
            for i in range(4)
        ],
        preferred=True,
    )
    inventory = TemplateInventory(
        slide_width=INVENTORY.slide_width,
        slide_height=INVENTORY.slide_height,
        patterns=[imaged, plain],
    )
    slide = SlidePlan(title="Method", bullets=["Frame", "Build", "Measure"])
    assert best_for_intent(inventory, plain.intent, slide) is plain
    with_image = slide.model_copy(update={"image": "doc-1"})
    assert best_for_intent(inventory, plain.intent, with_image) is imaged


def test_a_pattern_that_would_truncate_loses_to_one_that_holds_the_text():
    plain = _pattern("Title and Content")
    narrow = plain.model_copy(
        deep=True,
        update={"id": "slide:98", "label": "Narrow", "preferred": True},
    )
    for zone in narrow.zones:
        if zone.role == "body":
            zone.max_chars = 20
    inventory = TemplateInventory(
        slide_width=INVENTORY.slide_width,
        slide_height=INVENTORY.slide_height,
        patterns=[narrow, plain],
    )
    slide = SlidePlan(title="Detail", bullets=["A sentence far longer than twenty"] * 4)
    assert best_for_intent(inventory, plain.intent, slide) is plain


# --- unused item slots leave the slide clean ---


def test_a_group_pattern_given_no_items_keeps_the_slide_design():
    """Sweeping decoration by overlap with nothing kept took the slide's own
    background with it, silently."""
    kpi = _pattern("Key figures")
    result, deck = _render(SlidePlan(pattern=kpi.id, title="KPIs", bullets=["Stray"]))
    assert _title(deck.slides[0]) == "KPIs"
    assert any("gave none" in w for w in result.warnings)
    # The icons drawn beside the cards are gone with them, the title stays.
    assert _texts(deck.slides[0]) == ["KPIs"]


def test_a_connector_counts_as_inside_the_area_it_spans():
    """A connector is a line, zero-thick on one axis: every area ratio scores it
    nothing, so the org-chart stubs of dropped slots used to dangle on."""
    area = (0, 0, 1000, 1000)
    horizontal_rule = (100, 500, 900, 500)
    outside = (100, 1500, 900, 1500)
    assert _covered(horizontal_rule, area) == 1.0
    assert _covered(outside, area) == 0.0


def test_the_kept_items_are_recentred_on_the_room_the_group_had():
    kpi = _pattern("Key figures")
    _, deck = _render(
        SlidePlan(
            pattern=kpi.id, title="KPIs", items=[PlanItem(number="42%", label="Margin")]
        )
    )
    groups = [
        p
        for p in walk_shapes(deck.slides[0].shapes)
        if cast(Any, p.shape).shape_type == MSO_SHAPE_TYPE.GROUP
    ]
    assert len(groups) == 1
    centre = groups[0].left + groups[0].width // 2
    slide_centre = INVENTORY.slide_width // 2
    assert abs(centre - slide_centre) < Inches(0.6).emu


def test_an_unfilled_placeholder_is_removed_not_left_prompting():
    """An empty placeholder shows "Click to add text" as soon as the user opens
    the deck to edit it."""
    two = next(p for p in INVENTORY.patterns if p.label == "Two Content")
    _, deck = _render(
        SlidePlan(pattern=two.id, title="One side", bullets=["Only this"])
    )
    empty = [
        shape
        for shape in deck.slides[0].placeholders
        if not cast(Any, shape).text_frame.text.strip()
    ]
    assert not empty


# --- the remaining ways content or design was quietly lost ---


def test_a_replaced_picture_keeps_its_place_in_the_drawing_order():
    """Appending the new picture put it in front of everything, so a replaced
    cover photo hid the title drawn over it."""
    template = build_slides([add_cover_photo_slide])
    inventory = analyze_template(template).inventory
    assert inventory is not None
    pattern = next(p for p in inventory.patterns if p.source == "slide")
    plan = DeckPlan(
        slides=[SlidePlan(pattern=pattern.id, title="Cover", image="doc-1")]
    )
    result = render_deck(
        template, inventory, plan, {"doc-1": prepare_picture(png_bytes(400, 300))}
    )
    tree = list(Presentation(io.BytesIO(result.pptx)).slides[0].shapes._spTree)
    pictures = [i for i, el in enumerate(tree) if el.tag == qn("p:pic")]
    texts = [
        i
        for i, el in enumerate(tree)
        if el.tag == qn("p:sp")
        and "".join(t.text or "" for t in el.iter(qn("a:t"))).strip()
    ]
    assert pictures and texts
    assert max(pictures) < min(texts), "the replaced photo is in front of the title"


def test_the_hero_image_is_not_dropped_when_images_is_also_given():
    pattern = _pattern("Photo")
    result, deck = _render(
        SlidePlan(pattern=pattern.id, title="Cover", image="doc-1", images=["doc-2"]),
        images={
            "doc-1": prepare_picture(png_bytes(400, 300)),
            "doc-2": prepare_picture(png_bytes(300, 400)),
        },
    )
    assert _pictures(deck.slides[0]) >= 1
    assert not [w for w in result.warnings if "not a usable image" in w]


def test_a_field_the_model_invented_is_reported_not_swallowed():
    plan = DeckPlan.model_validate(
        {
            "slides": [
                {
                    "pattern": _pattern("Title and Content").id,
                    "title": "Results",
                    "bullets": ["Up"],
                    "footnote": "Source: internal",
                }
            ]
        }
    )
    result = render_deck(TEMPLATE, INVENTORY, plan)
    assert any("footnote" in w for w in result.warnings)


def test_a_bullet_wrapped_under_an_unknown_key_keeps_its_text():
    plan = DeckPlan.model_validate(
        {
            "slides": [
                {
                    "pattern": _pattern("Title and Content").id,
                    "title": "Results",
                    "bullets": [{"point": "Revenue up"}, "Costs flat"],
                }
            ]
        }
    )
    assert plan.slides[0].bullets == ["Revenue up", "Costs flat"]


def test_sibling_zones_of_one_slide_share_a_font_size():
    """Two headings of the same row at 24 pt and 13 pt read as a mistake, even
    when each was right on its own."""
    steps = _pattern("Process")
    _, deck = _render(
        SlidePlan(
            pattern=steps.id,
            title="How",
            items=[
                PlanItem(heading="Go", text="Start"),
                PlanItem(heading="A heading far longer than its siblings", text="Work"),
                PlanItem(heading="End", text="Close"),
            ],
        )
    )
    headings = ("Go", "A heading far longer than its siblings", "End")
    sizes = {}
    for placed in walk_shapes(deck.slides[0].shapes):
        shape = cast(Any, placed.shape)
        if not getattr(shape, "has_text_frame", False):
            continue
        text = shape.text_frame.text.strip()
        if text in headings:
            sizes[text] = {
                int(rPr.get("sz"))
                for rPr in shape.text_frame._txBody.iter(qn("a:rPr"))
                if rPr.get("sz")
            }
    assert set(sizes) == set(headings), sizes
    assert all(sizes.values()), "the shrunk sibling should carry an explicit size"
    assert len({frozenset(v) for v in sizes.values()}) == 1, sizes


def test_a_column_heading_written_into_the_body_drops_the_bullet():
    """Rendered as a bullet it is indistinguishable from the content below it."""
    content = _pattern("Title and Content")
    _, deck = _render(
        SlidePlan(
            pattern=content.id,
            title="Compare",
            columns=[PlanColumn(heading="Left", bullets=["a", "b"])],
        )
    )
    body = cast(Any, deck.slides[0].placeholders[1]).text_frame
    first = body.paragraphs[0]._p
    pPr = first.find(qn("a:pPr"))
    assert pPr is not None and pPr.find(qn("a:buNone")) is not None


def test_one_unbreakable_token_does_not_shrink_its_whole_zone_below_the_floor():
    """An e-mail address is one word: it used to set the size for the zone and
    took it down to 7 pt."""
    zone = Zone(
        key="ph:1",
        role="body",
        box=Box(x=0, y=0, w=200, h=300),
        font_pt=18.0,
        max_chars=60,
        max_lines=4,
    )
    _, scale, _ = _fit(
        zone,
        [_Line("marie.dupont@entreprise-exemple-tres-longue.fr")],
        Inches(13.333).emu,
        Inches(7.5).emu,
    )
    assert scale is None or scale >= MIN_FONT_SCALE


def test_a_title_that_auto_sizes_in_height_is_fitted_not_widened():
    """Such a box wraps inside its width and grows downwards. Widening it pushes
    a cover title over the photo beside it, and growing unchecked runs the text
    off the bottom of the slide - neither is reported unless it is fitted."""
    template = build_spaced_template(space_before_pt=0, no_wrap_title=False)
    inventory = analyze_template(template).inventory
    assert inventory is not None
    # The layout the fixture gives an auto-sizing title to.
    pattern = next(p for p in inventory.patterns if p.id == "layout:1" and p.zones)
    zone = next(z for z in pattern.zones if z.role == "title")
    assert not zone.grows
    designed = zone.box.w
    result = render_deck(
        template,
        inventory,
        DeckPlan(
            slides=[
                SlidePlan(
                    pattern=pattern.id,
                    title="Un titre de couverture nettement plus long que la zone que "
                    "le concepteur a dessinee pour lui, au point de sortir du cadre "
                    "prevu et de courir sur la photo placee juste a cote de lui",
                )
            ]
        ),
    )
    deck = Presentation(io.BytesIO(result.pptx))
    titles = [
        p
        for p in walk_shapes(deck.slides[0].shapes)
        if cast(Any, p.shape).has_text_frame
        and cast(Any, p.shape).text_frame.text.strip()
    ]
    assert titles
    widest = max(p.width for p in titles)
    assert widest <= designed / 1000 * inventory.slide_width * 1.02, (
        "the box was widened"
    )
    assert [w for w in result.warnings if "truncated" in w]


def test_an_agenda_announcing_more_than_the_deck_holds_is_reported():
    """A model can plan ten slides and write out two: the deck holds what was
    sent, and without this nothing says so."""
    result, _ = _render(
        SlidePlan(pattern=_pattern("Title and Content").id, title="Cover"),
        SlidePlan(
            pattern=_pattern("Agenda").id,
            title="Agenda",
            items=[PlanItem(heading=f"Topic {i}") for i in range(4)],
        ),
    )
    assert [w for w in result.warnings if "announces 4 topics" in w]


def test_an_agenda_matched_by_the_deck_is_not_reported():
    slides = [
        SlidePlan(
            pattern=_pattern("Agenda").id,
            title="Agenda",
            items=[PlanItem(heading="One"), PlanItem(heading="Two")],
        )
    ] + [
        SlidePlan(pattern=_pattern("Title and Content").id, title=t, bullets=["x"])
        for t in ("One", "Two")
    ]
    result, _ = _render(*slides)
    assert not [w for w in result.warnings if "announces" in w]


# --- advice an agent can act on when columns have nowhere to go ---


def _columns(count: int) -> list:
    return [
        PlanColumn(heading=f"C{i}", bullets=[f"Some text for column {i}"])
        for i in range(count)
    ]


def test_lost_columns_name_the_pattern_that_would_have_held_them():
    """ "Put it on a pattern that shows it" leaves the agent guessing which."""
    wide = _pattern("Title and Content").model_copy(deep=True)
    wide.id, wide.label, wide.intent = "layout:99", "Four columns", "two_columns"
    body = next(z for z in wide.zones if z.role == "body")
    wide.zones = [z for z in wide.zones if z.role != "body"] + [
        body.model_copy(update={"key": f"ph:{10 + i}"}) for i in range(4)
    ]
    inventory = TemplateInventory(
        slide_width=INVENTORY.slide_width,
        slide_height=INVENTORY.slide_height,
        patterns=[p for p in INVENTORY.patterns if p.included] + [wide],
    )
    narrow = next(
        p for p in inventory.patterns if p.intent == "two_columns" and p is not wide
    )
    result = render_deck(
        TEMPLATE,
        inventory,
        DeckPlan(slides=[SlidePlan(pattern=narrow.id, title="T", columns=_columns(4))]),
    )
    lost = [w for w in result.warnings if "no place for column" in w]
    assert lost and "layout:99" in lost[0], lost


def test_columns_beyond_every_pattern_say_so_instead_of_advising_a_rewrite():
    """The agent rewrites the same slide and loses the same columns again."""
    result = render_deck(
        TEMPLATE,
        INVENTORY,
        DeckPlan(
            slides=[SlidePlan(pattern="two_columns", title="T", columns=_columns(9))]
        ),
    )
    lost = [w for w in result.warnings if "no place for column" in w]
    assert lost, result.warnings
    assert "No pattern of this template shows more than" in lost[0]
    assert "Put it on a pattern that shows it" not in lost[0]
