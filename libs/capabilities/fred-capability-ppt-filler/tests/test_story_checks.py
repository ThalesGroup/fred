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

"""The one-measure chart check, and what the builder no longer refuses:
whether a slide makes a point or cites its figures is the model's call (owner
decision 2026-10-18: judgement moves to the LLM)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fred_capability_ppt_filler.builder import story
from fred_capability_ppt_filler.builder.assign import SlideProblem
from fred_capability_ppt_filler.builder.plan import DeckPlan

COVER = {"title": "Bilan 2025", "subtitle": "Direction"}
TAKEAWAY = "L'Italie pèse deux fois l'Espagne, le recrutement doit commencer là"
REPRO = {
    "type": "column",
    "categories": ["Années", "Salariés", "Sites"],
    "series": [{"name": "Groupe", "values": [45, 2800, 9]}],
}
SCATTER = {
    "type": "scatter",
    "x_title": "Price",
    "y_title": "Units sold",
    "series": [{"name": "Products", "points": [[10, 120], [15, 90], [2200, 6]]}],
}


def _check(*slides: Dict[str, Any]) -> List[SlideProblem]:
    plan = DeckPlan.model_validate({"slides": [COVER, *slides]})
    return story.check(plan, range(1, len(plan.slides) + 1))


def _slide(**fields: Any) -> Dict[str, Any]:
    return {"takeaway": TAKEAWAY, "title": "Effectifs", "bullets": ["Italie"], **fields}


# --- one measure per chart ------------------------------------------------------------------


def test_two_written_units_are_refused():
    chart = {
        "type": "column",
        "categories": ["Marge", "CA"],
        "series": [{"name": "2025", "values": ["12 %", "3 M€"]}],
    }
    (problem,) = _check(_slide(chart=chart))
    assert "chart mixes units (%, m€)" in problem.problem


def test_bare_numbers_beside_written_units_do_not_conflict():
    chart = {
        "type": "column",
        "categories": ["Q1", "Q2"],
        "series": [{"name": "Marge", "values": ["12 %", 14]}],
    }
    assert _check(_slide(chart=chart)) == []


SCATTER = {
    "type": "scatter",
    "x_title": "Price",
    "y_title": "Units sold",
    "series": [{"name": "Products", "points": [[10, 120], [15, 90], [2200, 6]]}],
}


def test_a_scatter_axis_mixing_units_is_refused():
    chart = {
        **SCATTER,
        "series": [
            {
                "name": "P",
                "points": [
                    {"x": "10 €", "y": 1},
                    {"x": "12 %", "y": 2},
                    {"x": "15 €", "y": 3},
                ],
            }
        ],
    }
    (problem,) = _check(_slide(chart=chart))
    assert (
        "x values mix units (%, €): a chart axis shows one measure" in problem.problem
    )
    # Units differing between axes are the point of a scatter.
    apart = {
        **SCATTER,
        "series": [
            {"name": "P", "points": [["10 €", "1 %"], ["12 €", "2 %"], ["9 €", 3]]}
        ],
    }
    assert _check(_slide(chart=apart)) == []


def test_an_edit_is_checked_on_the_slides_it_touches_only():
    mixed = {
        "type": "column",
        "categories": ["Marge", "CA"],
        "series": [{"name": "2025", "values": ["12 %", "3 M€"]}],
    }
    plan = DeckPlan.model_validate({"slides": [COVER, _slide(), _slide(chart=mixed)]})
    assert story.check(plan, [2]) == []
    assert [p.index for p in story.check(plan, [3])] == [3]


# --- judgement left to the model ----------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Comité du 18/10 : 3 décisions",
        "Top 10 risks for 5G and ISO 27001",
        "Release 2.1 vs 3.0 vs 4.0",
    ],
)
def test_dates_versions_and_standards_stay_in_a_title(title):
    assert _check(_slide(title=title), _slide(subtitle=title)) == []


@pytest.mark.parametrize(
    "takeaway",
    [
        None,
        "Présentation générale",
        "Pourquoi le CA baisse-t-il ?",
        "Effectifs",
        "意大利员工最多",
    ],
)
def test_the_takeaway_is_never_refused(takeaway):
    assert _check(_slide(takeaway=takeaway)) == []


def test_figures_need_no_source_nor_a_match_in_the_conversation():
    roadmap = {
        "header": ["Phase", "Quand", "Livrable"],
        "rows": [["Phase 1", "T3", "Lot 3"], ["Phase 2", "T4", "ISO 9001"]],
    }
    figures = [{"number": "2800", "label": "a"}, {"number": "9", "label": "b"}]
    assert _check(_slide(table=roadmap), _slide(items=figures)) == []
    assert (
        _check(_slide(chart=SCATTER), _slide(chart=REPRO, source="illustratif")) == []
    )


def test_a_wide_range_and_untitled_charts_are_built_as_sent():
    pie = {
        "type": "pie",
        "categories": ["A", "B"],
        "series": [{"name": "P", "values": [6, 4]}],
    }
    assert _check(_slide(chart=REPRO), _slide(charts=[REPRO, pie])) == []
