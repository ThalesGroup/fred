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
notes, never on the slide; illustrative and unverified figures said; the notes
of the checks accepted on a resend."""

from __future__ import annotations

import pytest
from fred_capability_ppt_filler.builder import notes as notes_mod
from fred_capability_ppt_filler.builder import story
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

pytestmark = pytest.mark.storytelling


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
        user="Fais un deck sur nos ventes, avec des données fictives",
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


@pytest.mark.asyncio
async def test_unverified_figures_are_built_on_the_resend_and_said(monkeypatch):
    invented = {
        **CHART,
        "chart": {**CHART["chart"], "series": [{"name": "E", "values": [4321, 2109]}]},
    }
    workspace = FakeWorkspace()
    build = await build_tool(
        monkeypatch,
        [HumanMessage(content="Fais une présentation de nos effectifs")],
        workspace=workspace,
    )
    refused, _ = await build(slides=[COVER, invented])
    assert "none of the slide's figures" in refused and not workspace.writes
    text, result = await build(slides=[COVER, invented])
    assert text.startswith("Delivered"), text
    assert summary_codes(result)[2] == ["figures_unverified"]
    assert "Chiffres non retrouvés dans les documents lus." in notes(
        deck(workspace).slides[1]
    )


@pytest.mark.asyncio
async def test_a_wide_range_chart_is_built_on_the_resend_with_a_note(monkeypatch):
    repro = {
        **CHART,
        "chart": {
            "type": "column",
            "categories": ["Années", "Salariés", "Sites"],
            "series": [{"name": "Groupe", "values": [45, 2800, 9]}],
        },
        "source": "user",
    }
    workspace = FakeWorkspace()
    build = await build_tool(
        monkeypatch,
        [HumanMessage(content="45 ans, 2 800 salariés, 9 sites")],
        workspace=workspace,
    )
    refused, _ = await build(slides=[COVER, repro])
    assert "do they measure the same thing?" in refused
    text, result = await build(slides=[COVER, repro])
    assert text.startswith("Delivered"), text
    assert summary_codes(result)[2] == ["wide_range_chart"]


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
async def test_an_edit_is_not_refused_over_a_slide_it_does_not_touch(monkeypatch):
    """A deck stored before takeaways existed still takes an edit elsewhere."""
    workspace = FakeWorkspace()
    old = {k: v for k, v in POINTS.items() if k != "takeaway"}
    with monkeypatch.context() as earlier:  # the earlier deck, unchecked
        earlier.setattr(story, "check", lambda *_a: story.StoryResult())
        delivered, _, _ = await _built(
            monkeypatch, [COVER, old, CHART], workspace=workspace
        )
    build = await build_tool(
        monkeypatch,
        answered(delivered) + [HumanMessage(content="Change le titre")],
        workspace=workspace,
    )
    text, _ = await build(
        changes=[{"op": "edit", "slide": 3, "field": "title", "value": "Effectifs"}]
    )
    assert text.startswith("Delivered"), text
