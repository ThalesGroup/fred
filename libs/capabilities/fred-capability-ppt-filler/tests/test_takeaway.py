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

"""The slide takeaway on the slide: only in a zone the template designed for
it, and only when the user asked to show the key messages; otherwise in the
speaker notes, the slide filled as before."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from builder_decks import build_slides
from fred_capability_ppt_filler.builder import tools
from fred_capability_ppt_filler.builder.analysis import analyze_template, mark_takeaway
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.labelling import SlideLabel, _merge
from fred_capability_ppt_filler.builder.models import Box, Pattern, Zone
from fred_capability_ppt_filler.builder.plan import zone_summary
from fred_capability_ppt_filler.fill import PptPreviewPart
from langchain_core.messages import HumanMessage
from port_fakes import FakeWorkspace
from pptx.util import Inches, Pt
from story_tools import COVER, answered, build_tool, deck, notes, texts

ASK = "Fais une présentation des ventes, et affiche les messages clés sur les slides."
PLAIN = "Fais une présentation des ventes : Q1 12, Q2 21, Q3 30, Q4 15."
TAKEAWAY = "Le troisième trimestre est notre meilleur trimestre de l'année"
CHART: Dict[str, Any] = {
    "takeaway": TAKEAWAY,
    "title": "Ventes 2025",
    "chart": {
        "type": "column",
        "categories": ["Q1", "Q2", "Q3", "Q4"],
        "series": [{"name": "Ventes", "values": [12, 21, 30, 15]}],
    },
    "source": "user",
}
WITH_BULLET = {**CHART, "bullets": ["Q3 porté par l'export"]}


@pytest.fixture(autouse=True)
def preview_union():
    from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union

    rebuild_ui_part_union([PptPreviewPart])
    yield
    rebuild_ui_part_union(())


async def _built(monkeypatch, slides, user: str, workspace=None, **kwargs: Any):
    workspace = workspace or FakeWorkspace()
    build = await build_tool(
        monkeypatch, [HumanMessage(content=f"{user} {PLAIN}")], workspace=workspace
    )
    text, result = await build(slides=slides, **kwargs)
    return text, result, workspace


def _card(slide: Any) -> List[str]:
    """The text of the slide's placeholder its layout names `takeaway`."""
    named = {
        ph.placeholder_format.idx
        for ph in slide.slide_layout.placeholders
        if ph.name == "takeaway"
    }
    return [
        s.text_frame.text
        for s in slide.placeholders
        if s.placeholder_format.idx in named
    ]


# --- analysis and labelling ------------------------------------------------------------


def _zone(key: str, role: Any, y: int) -> Zone:
    return Zone(key=key, role=role, box=Box(x=0, y=y, w=500, h=100))


def _pattern(kind: Any, *zones: Zone) -> Pattern:
    return Pattern(
        id="slide:1",
        source="slide",
        source_index=1,
        name="",
        label="x",
        kind=kind,
        zones=list(zones),
    )


def test_the_builtin_chart_slide_s_card_is_its_takeaway_zone():
    _, inventory = builtin_template()
    flagged = [(p.id, z.key) for p in inventory.patterns for z in p.zones if z.takeaway]
    assert flagged == [("slide:284", "ph:103"), ("slide:293", "ph:111")]
    summary = zone_summary(inventory.pattern("slide:284") or _pattern("chart"))
    assert "takeaway zone ≤" in summary and "bullets" in summary


def test_a_zone_named_for_a_key_message_is_flagged_first_in_reading_order():
    pattern = _pattern(
        "chart",
        _zone("ph:1", "title", 0),
        _zone("ph:3", "body", 600),
        _zone("ph:2", "body", 300),
        _zone("ph:4", "body", 800),
    )
    mark_takeaway(
        pattern,
        {
            "ph:2": ["Text Placeholder 2", "Key message"],
            "ph:3": ["À retenir"],
            "ph:4": [""],
        },
    )
    assert [z.key for z in pattern.zones if z.takeaway] == ["ph:2"]


def test_no_takeaway_zone_by_geometry_or_on_a_kind_without_takeaway():
    beside = _pattern("chart", _zone("ph:1", "title", 0), _zone("ph:2", "body", 300))
    mark_takeaway(beside, {"ph:2": ["Text Placeholder 2"]})
    assert not any(z.takeaway for z in beside.zones)
    quote = _pattern("quote", _zone("ph:2", "subtitle", 300))
    mark_takeaway(quote, {"ph:2": ["key message"]})
    assert not any(z.takeaway for z in quote.zones)
    title = _pattern("chart", _zone("ph:1", "title", 0))
    mark_takeaway(title, {"ph:1": ["Conclusion"]})
    assert not any(z.takeaway for z in title.zones)


def test_a_layout_placeholder_named_takeaway_is_found_through_the_slide():
    def bullets_with_card(presentation):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "Ventes"
        slide.placeholders[1].text_frame.text = "Q3 porté par l'export"
        # Named on the layout only: the slide's own shape keeps PowerPoint's name.
        presentation.slide_layouts[1].placeholders[1].name = "Key takeaway"

    inventory = analyze_template(build_slides([bullets_with_card])).inventory
    assert inventory is not None
    slides = [p for p in inventory.patterns if p.source == "slide"]
    assert [[z.role for z in p.zones if z.takeaway] for p in slides] == [["body"]]


def test_a_large_box_named_for_the_key_message_stays_the_takeaway():
    def chart_with_panel(presentation):
        slide = presentation.slides.add_slide(presentation.slide_layouts[5])
        slide.shapes.title.text = "Ventes"
        body = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(5), Inches(4))
        body.text_frame.text = "Cliquez ici pour ajouter du texte"
        panel = slide.shapes.add_textbox(Inches(6), Inches(1.5), Inches(3), Inches(1))
        panel.name = "Message clé"
        panel.text_frame.text = "Le message clé"
        panel.text_frame.paragraphs[0].runs[0].font.size = Pt(24)

    inventory = analyze_template(build_slides([chart_with_panel])).inventory
    assert inventory is not None
    slide = next(p for p in inventory.patterns if p.source == "slide")
    # Failed before: 24 pt on one line read it as a heading, which loses the flag.
    assert [z.role for z in slide.zones if z.takeaway] == ["body"]


def test_a_vision_purpose_naming_a_key_message_flags_the_zone():
    pattern = _pattern("chart", _zone("ph:1", "title", 0), _zone("ph:2", "body", 300))
    answer = SlideLabel(
        kind="chart",
        label="Chart and message",
        slots={1: "slide title", 2: "key message"},
        reusable=True,
    )
    merged = _merge(pattern, answer, (False, False))
    assert [z.key for z in merged.zones if z.takeaway] == ["ph:2"]


# --- the tool --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_by_default_the_card_holds_the_bullets_and_the_takeaway_the_notes(
    monkeypatch,
):
    text, _, workspace = await _built(monkeypatch, [COVER, WITH_BULLET], "")
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert _card(slide) == ["Q3 porté par l'export"]
    assert notes(slide).split("\n")[0] == TAKEAWAY
    assert not any(TAKEAWAY in t for t in texts(slide))


@pytest.mark.asyncio
async def test_on_request_the_takeaway_fills_the_card_of_the_chart_slide(monkeypatch):
    text, _, workspace = await _built(
        monkeypatch, [COVER, CHART], ASK, show_takeaways=True
    )
    assert text.startswith("Delivered"), text
    assert "show_takeaways" not in text
    slide = deck(workspace).slides[1]
    # The card counts as filled: the chart slide with a card is still chosen.
    assert _card(slide) == [TAKEAWAY]
    assert notes(slide).split("\n")[0] == TAKEAWAY


@pytest.mark.asyncio
async def test_the_flag_is_applied_whatever_the_user_s_language(monkeypatch):
    """The model judges the request: no word list overrides the flag."""
    text, _, workspace = await _built(
        monkeypatch,
        [COVER, CHART],
        "Zeig die Kernaussagen auf den Folien",
        show_takeaways="yes",
    )
    assert text.startswith("Delivered"), text
    assert _card(deck(workspace).slides[1]) == [TAKEAWAY]


@pytest.mark.asyncio
async def test_on_request_bullets_no_longer_fall_into_the_card(monkeypatch):
    text, _, workspace = await _built(
        monkeypatch, [COVER, WITH_BULLET], ASK, show_takeaways=True
    )
    # The built-in full chart slide holds the bullet in its caption; no chart
    # slide shows both, so the takeaway stays in the notes and that is told.
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert _card(slide) == []
    assert "Q3 porté par l'export" in texts(slide)
    assert notes(slide).split("\n")[0] == TAKEAWAY
    assert "has no key-message zone, so the takeaway is only" in text


@pytest.mark.asyncio
async def test_a_takeaway_longer_than_the_card_stays_in_the_notes(monkeypatch):
    long = " ".join(["Le troisième trimestre dépasse tous les autres"] * 12)
    slides = [COVER, {**WITH_BULLET, "takeaway": long}]
    text, _, workspace = await _built(monkeypatch, slides, ASK, show_takeaways=True)
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert _card(slide) == ["Q3 porté par l'export"]
    assert notes(slide).split("\n")[0] == long
    assert "Slide 2: the takeaway is too long" in text


@pytest.mark.asyncio
async def test_on_request_every_chart_takes_the_slide_with_a_card(monkeypatch):
    second = {
        **CHART,
        "takeaway": "Les marges suivent les ventes tout au long de l'année",
        "title": "Marges 2025",
    }
    slides = [COVER, CHART, second]
    text, _, workspace = await _built(monkeypatch, slides, ASK, show_takeaways=True)
    assert text.startswith("Delivered"), text
    built = deck(workspace).slides
    assert [_card(built[1]), _card(built[2])] == [[TAKEAWAY], [second["takeaway"]]]
    # Without the request the card would stay empty: the wide chart slide, as before.
    text, _, workspace = await _built(monkeypatch, slides, "")
    assert text.startswith("Delivered"), text
    assert [_card(s) for s in list(deck(workspace).slides)[1:]] == [[], []]


@pytest.mark.asyncio
async def test_a_bullets_slide_without_a_zone_is_unchanged(monkeypatch):
    points = {
        "takeaway": "Nos équipes se concentrent sur deux pays européens",
        "title": "Nos équipes",
        "bullets": ["Italie en tête", "Espagne en retrait"],
    }
    text, result, workspace = await _built(
        monkeypatch, [COVER, points], ASK, show_takeaways=True
    )
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert not any(points["takeaway"] in t for t in texts(slide))
    (part,) = result.ui_parts
    # The loss is told, not silent.
    assert [(n.code, n.field) for n in part.summary[1].notes] == [
        ("intent_not_shown", "takeaway")
    ]
    assert (
        "has no key-message zone, so the takeaway is only in the speaker notes" in text
    )


@pytest.mark.asyncio
async def test_an_edit_keeps_the_flag_and_refills_the_card(monkeypatch):
    workspace = FakeWorkspace()
    delivered, _, _ = await _built(
        monkeypatch, [COVER, CHART], ASK, workspace=workspace, show_takeaways=True
    )
    build = await build_tool(
        monkeypatch,
        answered(delivered, f"{ASK} {PLAIN}") + [HumanMessage(content="Reformule")],
        workspace=workspace,
    )
    new = "Le troisième trimestre double presque le premier"
    text, _ = await build(
        changes=[{"op": "edit", "slide": 2, "field": "takeaway", "value": new}]
    )
    assert text.startswith("Delivered"), text
    assert _card(deck(workspace).slides[1]) == [new]


def test_the_flag_is_offered_only_with_a_takeaway_zone():
    _, inventory = builtin_template()
    schema = tools._args_schema(inventory).model_json_schema()
    assert "show_takeaways" in schema["properties"]
    assert "show_takeaways: true only when" in tools._description(inventory, "off", 2)

    def bullets(presentation):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "Constats"
        slide.placeholders[1].text_frame.text = "Un point"

    plain = analyze_template(build_slides([bullets])).inventory
    assert plain is not None
    assert (
        "show_takeaways"
        not in tools._args_schema(plain).model_json_schema()["properties"]
    )


async def _edited(monkeypatch, slides, changes_sent):
    """A deck delivered without show_takeaways, then each list of changes."""
    workspace = FakeWorkspace()
    delivered, _, _ = await _built(monkeypatch, slides, "", workspace=workspace)
    texts_back = []
    for changes in changes_sent:
        build = await build_tool(
            monkeypatch,
            answered(delivered, PLAIN) + [HumanMessage(content="Change")],
            workspace=workspace,
        )
        text, _ = await build(changes=changes)
        assert text.startswith("Delivered"), text
        texts_back.append(text)
    return texts_back, workspace


@pytest.mark.asyncio
async def test_an_edited_takeaway_goes_on_a_design_of_its_kind_that_shows_it(
    monkeypatch,
):
    """Changing one slide's key message is about what the slide shows: a design of
    its kind with a key-message zone takes it, and keeps it on the next edit."""
    new = "Le troisième trimestre double presque le premier"
    texts_back, workspace = await _edited(
        monkeypatch,
        [COVER, CHART],
        [
            [{"op": "edit", "slide": 2, "field": "takeaway", "value": new}],
            [{"op": "edit", "slide": 2, "field": "title", "value": "Ventes"}],
        ],
    )
    assert _card(deck(workspace).slides[1]) == [new]
    assert "speaker notes only" not in texts_back[0]


@pytest.mark.asyncio
async def test_an_edited_takeaway_no_design_of_its_kind_shows_names_those_that_do(
    monkeypatch,
):
    points = {
        "takeaway": "Nos équipes se concentrent sur deux pays européens",
        "title": "Nos équipes",
        "bullets": ["Italie en tête", "Espagne en retrait"],
    }
    new = "Nos équipes réduisent les coûts dans deux pays"
    (text,), workspace = await _edited(
        monkeypatch,
        [COVER, points],
        [[{"op": "edit", "slide": 2, "field": "takeaway", "value": new}]],
    )
    assert not any(new in t for t in texts(deck(workspace).slides[1]))
    assert (
        "so the takeaway is only in the speaker notes. Designs that show one: " in text
    )
    assert "'Charts stay native and editable' (chart)" in text
