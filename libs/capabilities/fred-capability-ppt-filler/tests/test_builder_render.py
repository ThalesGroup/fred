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
import os
from typing import Any, cast

import pytest
from builder_decks import FOOTER, build_showcase_template
from deck_builders import png_bytes
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.lexicon import is_sample_text
from fred_capability_ppt_filler.builder.models import PatternOverride, TemplateInventory
from fred_capability_ppt_filler.builder.overrides import apply_overrides
from fred_capability_ppt_filler.builder.plan import (
    DeckPlan,
    PlanColumn,
    PlanItem,
    SlidePlan,
)
from fred_capability_ppt_filler.builder.render import RenderError, render_deck
from fred_capability_ppt_filler.images import prepare_picture
from fred_capability_ppt_filler.traversal import walk_shapes
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

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
    autofit = body.text_frame._txBody.find(qn("a:bodyPr")).find(qn("a:normAutofit"))
    assert autofit is not None and int(autofit.get("fontScale")) < 100000

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

    with pytest.raises(RenderError, match="doc-missing"):
        _render(
            SlidePlan(pattern=photo.id, title="Site", image="doc-missing"),
            images=prepared,
        )


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


def test_unknown_or_excluded_patterns_are_refused():
    with pytest.raises(RenderError, match="Unknown pattern"):
        _render(SlidePlan(pattern="slide:999", title="x"))
    chart = next(p for p in INVENTORY.patterns if p.exclusion_reason == "chart")
    with pytest.raises(RenderError, match="excluded"):
        _render(SlidePlan(pattern=chart.id, title="x"))


def test_fixed_pattern_is_copied_verbatim_and_notes_are_written():
    divider = _pattern("Motif")
    _, deck = _render(SlidePlan(pattern=divider.id, title="ignored", notes="Say hello"))
    slide = deck.slides[0]
    assert _title(slide) == "Motif"
    assert cast(Any, slide.notes_slide.notes_text_frame).text == "Say hello"


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
