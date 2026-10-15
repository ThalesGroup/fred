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

"""The storytelling checks: takeaway, figures in titles, one measure per
chart, sourced figures and the lenient spot-check, each with its
false-positive guards."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fred_capability_ppt_filler.builder import story
from fred_capability_ppt_filler.builder.plan import DeckPlan
from fred_capability_ppt_filler.builder.story import Conversation, StoryResult

pytestmark = pytest.mark.storytelling

COVER = {"title": "Bilan 2025", "subtitle": "Direction"}
TAKEAWAY = "L'Italie pèse deux fois l'Espagne, le recrutement doit commencer là"
REPRO = {
    "type": "column",
    "categories": ["Années", "Salariés", "Sites"],
    "series": [{"name": "Groupe", "values": [45, 2800, 9]}],
}


def _check(
    *slides: Dict[str, Any],
    users: Optional[List[str]] = None,
    tools: Optional[List[str]] = None,
    builds: Optional[List[str]] = None,
    seen: Optional[set] = None,
) -> StoryResult:
    plan = DeckPlan.model_validate({"slides": [COVER, *slides]})
    users = users or []
    talk = Conversation(users=users, sources=users + (tools or []), builds=builds or [])
    return story.check(
        plan, range(1, len(plan.slides) + 1), talk, set() if seen is None else seen
    )


def _problems(result: StoryResult) -> Dict[int, str]:
    return {p.index: p.problem for p in result.problems}


def _slide(**fields: Any) -> Dict[str, Any]:
    return {"takeaway": TAKEAWAY, "title": "Effectifs", "bullets": ["Italie"], **fields}


# --- takeaway ---------------------------------------------------------------------------


def test_a_sentence_passes_whatever_the_title():
    assert _check(_slide(), _slide(title=None)).problems == []


@pytest.mark.parametrize(
    ("takeaway", "problem"),
    [
        (None, "no takeaway"),
        ("Présentation générale", "is a topic, not a conclusion"),
        ("Pourquoi le chiffre d'affaires baisse-t-il ?", "is a question"),
        ("Effectifs par pays en 2025", "repeats the title"),
    ],
)
def test_a_takeaway_that_is_no_conclusion_is_refused(takeaway, problem):
    slide = _slide(takeaway=takeaway, title="Effectifs par pays en 2025")
    result = _check(slide)
    assert problem in _problems(result)[2]
    assert result.hard
    # The option carries the remedy, with an example from the slide's content.
    assert any("takeaway" in o for o in result.problems[0].options)


def test_structural_and_quote_slides_need_no_takeaway():
    result = _check(
        {"title": "Partie 1", "kind": "section"},
        {"title": "Sommaire", "items": [{"heading": "A"}, {"heading": "B"}]},
        {"bullets": ["« Le client d'abord »"], "kind": "quote"},
        {"title": "Merci", "kind": "closing"},
    )
    assert result.problems == []


def test_a_chart_example_is_built_from_its_data():
    result = _check(
        {"title": "Effectifs", "source": "user", "chart": {**REPRO, "unit": "x"}}
    )
    assert "Salariés leads with 2 800, ahead of Années" in str(
        result.problems[0].options
    )


# --- figures in a title -------------------------------------------------------------------


def test_figures_crammed_into_a_subtitle_offer_a_figures_slide():
    result = _check(_slide(subtitle="45 ans, 2 800 salariés, 9 sites"))
    assert "the subtitle holds 3 figures (45, 2 800, 9)" in _problems(result)[2]
    assert "figures slide" in result.problems[0].options[0]
    # The cover is checked too.
    plan = DeckPlan.model_validate(
        {"slides": [{"title": "Groupe", "subtitle": "45 ans, 2 800 salariés, 9 sites"}]}
    )
    assert story.check(plan, [1], Conversation(), set()).problems


def test_years_and_two_figures_stay_in_a_title():
    assert _check(_slide(title="De 2019 à 2025 : 2 sites, 3 pays")).problems == []
    assert _check(_slide(title="2 sites, 3 pays, 40 clients")).problems != []
    assert _check(_slide(subtitle="Q1 2024 – T3 2025")).problems == []


# --- one measure per chart ------------------------------------------------------------------


def test_the_repro_chart_is_refused_once_then_built_with_a_note():
    slide = _slide(chart=REPRO, source="user")
    users = ["45 ans, 2 800 salariés et 9 sites"]
    first = _check(slide, users=users)
    (problem,) = first.problems
    assert "range from 9 to 2 800" in problem.problem
    assert "do they measure the same thing?" in problem.problem
    assert any("unit" in o for o in problem.options)
    assert not first.hard  # a soft refusal: the same call is evaluated again
    again = _check(slide, users=users, seen=first.refused_soft)
    assert again.problems == []
    assert again.accepted == {2: [story.WIDE_RANGE_CHART]}


def test_a_soft_refusal_in_an_earlier_turn_counts():
    slide = _slide(chart=REPRO, source="user")
    users = ["45 ans, 2 800 salariés et 9 sites"]
    (problem,) = _check(slide, users=users).problems
    earlier = '{"status": "needs_revision", "slides": [{"problem": "%s"}]}' % (
        problem.problem
    )
    assert _check(slide, users=users, builds=[earlier]).problems == []


def test_a_unit_or_a_pie_takes_a_wide_range():
    users = ["45 ans, 2 800 salariés et 9 sites"]
    assert (
        _check(
            _slide(chart={**REPRO, "unit": "employees"}, source="u"), users=users
        ).problems
        == []
    )
    pie = {**REPRO, "type": "pie"}
    assert _check(_slide(chart=pie, source="user"), users=users).problems == []


def test_two_written_units_are_refused_on_every_send():
    chart = {
        "type": "column",
        "categories": ["Marge", "CA"],
        "series": [{"name": "2025", "values": ["12 %", "3 M€"]}],
    }
    slide = _slide(chart=chart, source="user")
    users = ["12 % de marge et 3 M€ de CA"]
    first = _check(slide, users=users)
    assert "chart mixes units (%, m€)" in first.problems[0].problem
    assert first.hard
    again = _check(slide, users=users, seen=first.refused_soft | {"anything"})
    assert again.problems and again.hard


def test_bare_numbers_beside_written_units_do_not_conflict():
    chart = {
        "type": "column",
        "categories": ["Q1", "Q2"],
        "series": [{"name": "Marge", "values": ["12 %", 14]}],
    }
    assert _check(_slide(chart=chart, source="user"), users=["12 %"]).problems == []


# --- sources --------------------------------------------------------------------------------


def test_a_slide_with_figures_needs_a_source():
    chart = {**REPRO, "unit": "x"}
    assert "no `source`" in _problems(_check(_slide(chart=chart)))[2]
    table = {"header": ["Pays", "Effectif"], "rows": [["Italie", "1 200"]]}
    assert "no `source`" in _problems(_check(_slide(table=table)))[2]
    figures = [{"number": "1 200", "label": "Italie"}, {"number": "800", "label": "ES"}]
    assert "no `source`" in _problems(_check(_slide(items=figures)))[2]


def test_steps_years_and_text_tables_hold_no_figures():
    steps = [{"number": "01", "heading": "A"}, {"number": "02", "heading": "B"}]
    years = [{"number": "2019", "heading": "A"}, {"number": "2024", "heading": "B"}]
    table = {"header": ["Année", "Pays"], "rows": [["2024", "Italie"]]}
    assert (
        _check(_slide(items=steps), _slide(items=years), _slide(table=table)).problems
        == []
    )


def test_illustrative_figures_need_the_users_allowance():
    pie = {
        "type": "pie",
        "categories": ["A", "B"],
        "series": [{"name": "Parts", "values": [60, 40]}],
    }
    slide = _slide(chart=pie, source="illustratif")
    refused = _check(slide, users=["Fais une présentation sur nos ventes"])
    assert "did not ask for illustrative figures" in _problems(refused)[2]
    allowed = _check(slide, users=["Mets des données fictives"])
    assert allowed.problems == []


# --- the spot-check -------------------------------------------------------------------------


def _figures(*numbers: str, source: str = "rapport 2025") -> Dict[str, Any]:
    items = [{"number": n, "label": f"l{i}"} for i, n in enumerate(numbers)]
    return _slide(items=items, source=source)


@pytest.mark.parametrize(
    ("said", "shown"),
    [
        ("on a 2 800 salariés", "2800"),
        ("on a 2800 salariés", "2 800"),
        ("on a 2,8 k salariés", "2 800"),
        ("croissance de 12,46 %", "12,5 %"),
        ("chiffre d'affaires 2,8 M€", "2 800 000 €"),
        ("chiffre d'affaires 2 784", "2 800"),
        ("revenue 1,234.5", "1234.5"),
        ("12,5 % de croissance et 3,2 M€ de CA", "3 200 000 €"),
    ],
)
def test_formatting_variants_and_rounding_match(said, shown):
    assert _check(_figures(shown, "7"), tools=[said]).problems == []


def test_figures_the_user_typed_count_as_found():
    slide = _figures("12.5 %", "3 200 000 €", source="user")
    said = ["on a fait 12,5 % de croissance et 3,2 M€ de CA"]
    assert _check(slide, users=said).problems == []


def test_derived_values_match():
    pie = {
        "type": "pie",
        "categories": ["Italie", "Autres"],
        "series": [{"name": "Parts", "values": [43, 57]}],
    }
    found = ["Italie 1 200, total 2 800"]
    assert _check(_slide(chart=pie, source="rapport"), tools=found).problems == []
    # A growth rate of two found numbers.
    assert _check(_figures("+25 %"), tools=["2024 : 800, 2025 : 1 000"]).problems == []
    # A total of the slide's own values.
    assert _check(_figures("30", "70", "100"), tools=["rien"]).problems == []
    # A sum of two numbers of one tool result, not of two.
    assert _check(_figures("1 750"), tools=["Lyon 1 000 et Nice 750"]).problems == []
    assert _check(_figures("1 751"), tools=["Lyon 1 000", "Nice 751.5"]).problems != []


def test_figures_related_to_nothing_are_refused_once_then_built_with_a_note():
    slide = _figures("2800", "9")
    first = _check(slide, tools=["4 100 clients et 63 agences"])
    assert "none of the slide's figures (9, 2 800) appears" in _problems(first)[2]
    assert not first.hard
    again = _check(slide, tools=["4 100 clients"], seen=first.refused_soft)
    assert again.problems == []
    assert again.accepted == {2: [story.FIGURES_UNVERIFIED]}


def test_the_build_tools_own_answers_are_no_source(monkeypatch):
    """A refusal quoting the model's figures must not make them found."""
    talk = Conversation(builds=["values from 9 to 2 800"])
    assert story.found_numbers(talk.sources).values == []


def test_the_scan_is_bounded():
    huge = " ".join(str(n) for n in range(200_000))
    found = story.found_numbers([huge] * 30)
    assert len(found.values) <= 4_000
    # Every lookup stays within the budget: an exhausted budget counts as found.
    found.budget = 0
    assert found.derived(43, 0)


def test_an_edit_is_checked_on_the_slides_it_touches_only():
    plan = DeckPlan.model_validate({"slides": [COVER, _slide(), _slide(takeaway=None)]})
    assert story.check(plan, [2], Conversation(), set()).problems == []
    assert [
        p.index for p in story.check(plan, [3], Conversation(), set()).problems
    ] == [3]
