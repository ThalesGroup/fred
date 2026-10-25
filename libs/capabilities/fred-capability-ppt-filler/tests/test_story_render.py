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

"""What a built deck says about its story: takeaway and source in the speaker
notes, never on the slide; illustrative figures said."""

from __future__ import annotations

import pytest
from fred_capability_ppt_filler.builder import notes as notes_mod
from fred_capability_ppt_filler.builder.plan import DeckPlan, PlanChart
from fred_capability_ppt_filler.fill import PptPreviewPart
from langchain_core.messages import HumanMessage
from port_fakes import FakeWorkspace
from story_tools import (
    CHART,
    COVER,
    DECK,
    POINTS,
    USER,
    answered,
    build_tool,
    deck,
    notes,
    summary_codes,
    texts,
)


@pytest.fixture(autouse=True)
def preview_union():
    from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union

    rebuild_ui_part_union([PptPreviewPart])
    yield
    rebuild_ui_part_union(())


async def _built(monkeypatch, slides, user: str = USER, workspace=None):
    workspace = workspace or FakeWorkspace()
    build = await build_tool(
        monkeypatch, [HumanMessage(content=user)], workspace=workspace
    )
    text, result = await build(slides=slides)
    return text, result, workspace


@pytest.mark.asyncio
async def test_the_takeaway_opens_the_notes_and_never_reaches_the_slide(monkeypatch):
    text, result, workspace = await _built(monkeypatch, DECK)
    assert text.startswith("Delivered"), text
    _, points, chart = deck(workspace).slides
    assert notes(points).split("\n") == [POINTS["takeaway"], "Insister sur l'Italie."]
    assert notes(chart).split("\n") == [CHART["takeaway"], "Source : rapport RH 2025"]
    for slide, sent in ((points, POINTS), (chart, CHART)):
        assert sent["title"] in texts(slide)
        assert not any(sent["takeaway"] in t for t in texts(slide))


@pytest.mark.asyncio
async def test_no_title_sent_leaves_the_title_unfilled(monkeypatch):
    untitled = {k: v for k, v in POINTS.items() if k != "title"}
    text, _, workspace = await _built(monkeypatch, [COVER, untitled, CHART])
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert notes(slide).startswith(POINTS["takeaway"])
    assert not any(POINTS["takeaway"] in t for t in texts(slide))


@pytest.mark.asyncio
async def test_illustrative_figures_are_said_in_caption_notes_and_summary(
    monkeypatch,
):
    pie = {
        "takeaway": "La majorité de nos ventes vient du canal direct",
        "title": "Ventes par canal",
        "chart": {
            "type": "pie",
            "title": "Répartition des ventes",
            "categories": ["Direct", "Partenaires"],
            "series": [{"name": "Ventes", "values": [70, 30]}],
        },
        "source": "illustratif",
    }
    text, result, workspace = await _built(
        monkeypatch,
        [COVER, pie],
        user="Erfinde Beispielzahlen für unsere Verkäufe",  # no FR/EN word list
    )
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    (frame,) = [s for s in slide.shapes if getattr(s, "has_chart", False)]
    assert (
        frame.chart.chart_title.text_frame.text
        == "Répartition des ventes (illustratif)"
    )
    assert "Chiffres illustratifs, non issus des documents." in notes(slide)
    assert "illustrative_data" in summary_codes(result)[2]


def test_caption_and_notes_follow_the_plans_language():
    english = DeckPlan.model_validate(
        {
            "slides": [
                {"title": "Sales by channel", "bullets": ["The direct channel leads"]}
            ]
        }
    )
    assert notes_mod.plan_language(english) == "en"
    chart = PlanChart.model_validate({"categories": ["A"], "series": [[1]]})
    assert notes_mod.caption(chart, "en") == "Illustrative data"
    titled = chart.model_copy(update={"title": "Sales"})
    assert notes_mod.caption(titled, "en") == "Sales (illustrative)"
    assert notes_mod.caption(titled, "fr") == "Sales (illustratif)"


@pytest.mark.parametrize(
    ("sent", "typeset"),
    [
        ("Effectif : 40 000 personnes", "Effectif\u00a0: 40\u202f000 personnes"),
        ("Marge 12 % ; coût 3 € !", "Marge 12\u00a0%\u00a0; coût 3\u00a0€\u00a0!"),
        ("« Pourquoi ? »", "«\u00a0Pourquoi\u00a0?\u00a0»"),
        ("1 200 000 et 2 500", "1\u202f200\u202f000 et 2\u202f500"),
        # A figure's % or € gains its space; a sign after a letter does not.
        ("Marge 70% et 12€", "Marge 70\u00a0% et 12\u00a0€"),
        ("12,5% de 1 000€", "12,5\u00a0% de 1\u202f000\u00a0€"),
        ("CO2 x%", "CO2 x%"),
        # Only written spaces change, and a year is no digit group.
        ("Note: voir http://x.fr", "Note: voir http://x.fr"),
        ("En 2024 300 sites", "En 2024 300 sites"),
        ("3,5 000", "3,5 000"),
    ],
)
def test_french_typography_turns_written_spaces_into_no_break_ones(sent, typeset):
    assert notes_mod.french_typography(sent) == typeset


def test_french_chart_labels_are_typeset():
    chart = PlanChart.model_validate(
        {
            "title": "Effectif : 2025",
            "categories": ["Plus de 10 000", "Moins"],
            "series": [{"name": "Part (%)", "values": [1, 2]}],
        }
    )
    typeset = notes_mod.french_chart(chart)
    assert typeset.title == "Effectif\u00a0: 2025"
    assert typeset.categories == ["Plus de 10\u202f000", "Moins"]
    assert typeset.series[0].values == [1, 2]


@pytest.mark.asyncio
async def test_a_french_deck_is_built_with_french_spacing(monkeypatch):
    spaced = {**POINTS, "bullets": ["Italie : 40 000 personnes", "Espagne en retrait"]}
    labelled = {
        **CHART,
        "chart": {**CHART["chart"], "categories": ["Italie : 1 200", "Espagne"]},
    }
    text, _, workspace = await _built(monkeypatch, [COVER, spaced, labelled])
    assert text.startswith("Delivered"), text
    _, points, chart = deck(workspace).slides
    assert any("Italie\u00a0: 40\u202f000 personnes" in t for t in texts(points))
    (frame,) = [s for s in chart.shapes if getattr(s, "has_chart", False)]
    assert frame.chart.plots[0].categories[0] == "Italie\u00a0: 1\u202f200"


@pytest.mark.asyncio
async def test_figures_and_a_wide_range_are_built_as_sent(monkeypatch):
    """No spot-check nor spread question: the first call is built, without a note."""
    invented = {
        **CHART,
        "chart": {**CHART["chart"], "series": [{"name": "E", "values": [4321, 2109]}]},
    }
    repro = {
        **CHART,
        "chart": {
            "type": "column",
            "categories": ["Années", "Salariés", "Sites"],
            "series": [{"name": "Groupe", "values": [45, 2800, 9]}],
        },
    }
    text, result, workspace = await _built(
        monkeypatch, [COVER, invented, repro], user="Fais une présentation"
    )
    assert text.startswith("Delivered"), text
    assert summary_codes(result)[2] == summary_codes(result)[3] == []
    assert "Source : rapport RH 2025" in notes(deck(workspace).slides[1])


@pytest.mark.asyncio
async def test_an_edit_of_the_takeaway_changes_the_notes_only(monkeypatch):
    workspace = FakeWorkspace()
    delivered, _, _ = await _built(monkeypatch, DECK, workspace=workspace)
    build = await build_tool(
        monkeypatch,
        answered(delivered) + [HumanMessage(content="Reformule")],
        workspace=workspace,
    )
    new = "L'Espagne reste un relais de croissance à ne pas négliger"
    text, _ = await build(
        changes=[{"op": "edit", "slide": 2, "field": "takeaway", "value": new}]
    )
    assert text.startswith("Delivered"), text
    slide = deck(workspace).slides[1]
    assert notes(slide).startswith(new) and POINTS["title"] in texts(slide)


@pytest.mark.asyncio
async def test_two_written_units_are_refused_through_the_tool(monkeypatch):
    """The call's written units survive the plan's coercion."""
    mixed = {
        **CHART,
        "chart": {
            "type": "column",
            "categories": ["Marge", "CA"],
            "series": [{"name": "2025", "values": ["12 %", "3 M€"]}],
        },
        "source": "user",
    }
    text, _, workspace = await _built(
        monkeypatch, [COVER, mixed], user="Marge 12 %, chiffre d'affaires 3 M€"
    )
    assert "chart mixes units (%, m€)" in text and not workspace.writes


@pytest.mark.asyncio
async def test_k_and_m_euros_in_one_chart_are_drawn_in_one_scale(monkeypatch):
    scaled = {
        **CHART,
        "chart": {
            "type": "column",
            "categories": ["Italie", "Espagne"],
            "series": [{"name": "Budget", "values": ["500 k€", "2 M€"]}],
        },
    }
    text, _, workspace = await _built(monkeypatch, [COVER, scaled])
    assert text.startswith("Delivered"), text
    (frame,) = [s for s in deck(workspace).slides[1].shapes if s.has_chart]
    chart = frame.chart
    assert list(chart.plots[0].series[0].values) == [0.5, 2.0]
    assert chart.value_axis.tick_labels.number_format == '#,##0.0" M€"'
