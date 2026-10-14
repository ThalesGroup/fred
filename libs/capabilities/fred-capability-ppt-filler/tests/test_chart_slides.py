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

"""Chart slides: the plan's data, the zone the template offers for it, and a
native chart drawn in the theme's colours. A few tests are adapted from
``fred-capability-pptx-generator``, by Shuigami."""

from __future__ import annotations

import io
from typing import Any, Dict, List

import pytest
from builder_decks import (
    add_chart_slide,
    add_main_chart_slide,
    build_layouts_only_template,
    build_slides,
)
from fred_capability_ppt_filler.builder import tools
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.assign import Assignment, assign, infer_kinds
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.changes import SlideChange, apply_changes
from fred_capability_ppt_filler.builder.labelling import kind_fits_slots
from fred_capability_ppt_filler.builder.models import TemplateInventory
from fred_capability_ppt_filler.builder.plan import DeckPlan, PlanChart
from fred_capability_ppt_filler.builder.render import RenderResult, render_deck
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.util import Inches

COVER = {"title": "Quarterly review", "subtitle": "Sales"}
REVENUE = {
    "type": "column",
    "categories": ["Q1", "Q2", "Q3", "Q4"],
    "series": [{"name": "Revenue", "values": [12, 15, 18, 21]}],
}


@pytest.fixture(scope="module")
def builtin():
    return builtin_template()


def _plan(*slides: Dict[str, Any]) -> DeckPlan:
    return DeckPlan.model_validate({"slides": [COVER, *slides]})


def _chart_slide(chart: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    return {"title": "Revenue", "chart": chart, **extra}


def _assigned(inventory: TemplateInventory, *slides: Dict[str, Any]) -> Assignment:
    return assign(inventory, _plan(*slides), "off")


def _render(template: bytes, inventory: TemplateInventory, *slides) -> RenderResult:
    plan = _plan(*slides)
    assignment = assign(inventory, plan, "off")
    assert not assignment.problems, [p.as_dict() for p in assignment.problems]
    return render_deck(template, inventory, plan, assignment.patterns)


def _charts(result: RenderResult, slide: int = 1) -> List[Any]:
    deck = Presentation(io.BytesIO(result.pptx))
    return [s for s in deck.slides[slide].shapes if getattr(s, "has_chart", False)]


def _chart(result: RenderResult, slide: int = 1) -> Any:
    (frame,) = _charts(result, slide)
    return frame.chart


def _problem(assignment: Assignment) -> Dict[str, Any]:
    (problem,) = assignment.problems
    return problem.as_dict()


# --- analysis ---------------------------------------------------------------------


def test_builtin_chart_slides_are_chart_patterns(builtin):
    _, inventory = builtin
    charts = [p for p in inventory.patterns if p.kind == "chart"]
    assert [(p.name, p.included, p.source) for p in charts] == [
        ("Fred Chart", True, "slide"),
        ("Fred Chart Wide", True, "slide"),
    ]
    takeaway, wide = charts
    zone = next(z for z in takeaway.zones if z.role == "chart")
    assert (zone.key, zone.chart_type, zone.max_lines) == ("ph:101", "column", 12)
    assert [z.role for z in wide.zones] == ["title", "chart"]
    assert next(z for z in wide.zones if z.role == "chart").box.w == 910
    assert kind_fits_slots("chart", takeaway)
    assert not kind_fits_slots("bullets", takeaway)


def test_an_example_slides_main_chart_is_its_zone():
    inventory = analyze_template(build_slides([add_main_chart_slide])).inventory
    assert inventory is not None
    (pattern,) = [p for p in inventory.patterns if p.source == "slide"]
    assert (pattern.kind, pattern.included) == ("chart", True)
    zone = next(z for z in pattern.zones if z.role == "chart")
    assert zone.key.startswith("sp:") and zone.chart_type == "pie"


def test_two_charts_or_a_small_chart_keep_the_slide_out():
    def small_chart(presentation):
        slide = add_main_chart_slide(presentation)
        frame = next(s for s in slide.shapes if s.has_chart)
        frame.width, frame.height = Inches(2), Inches(1.5)
        return slide

    inventory = analyze_template(build_slides([add_chart_slide, small_chart])).inventory
    assert inventory is not None
    slides = [p for p in inventory.patterns if p.source == "slide"]
    assert [p.exclusion_reason for p in slides] == ["chart", "unsupported_parts"]


def test_only_a_large_content_placeholder_can_hold_a_chart(builtin):
    inventory = analyze_template(build_layouts_only_template()).inventory
    assert inventory is not None
    content = next(p for p in inventory.patterns if p.name == "Title and Content")
    assert [z.chart_capable for z in content.zones] == [False, True]
    assert not kind_fits_slots("chart", content)
    # The built-in deck types its text bodies as such: only its table layout's
    # content placeholder could host a chart.
    _, fred = builtin
    capable = [p.name for p in fred.patterns if any(z.chart_capable for z in p.zones)]
    assert capable == ["Fred Table"]


# --- the plan -----------------------------------------------------------------------


def test_a_chart_is_read_from_what_small_models_write():
    chart = PlanChart.model_validate(
        {
            "chart_type": "Donut chart",
            "labels": ["Europe", "Asie"],
            "data": [{"label": "Parts", "values": ["45 %", "55,5 %"]}],
        }
    )
    assert (chart.type, chart.categories, chart.unit) == (
        "doughnut",
        ["Europe", "Asie"],
        "%",
    )
    assert chart.series[0].name == "Parts" and chart.series[0].values == [45.0, 55.5]
    pairs = PlanChart.model_validate({"series": {"Q1": "1 200", "Q2": "€3.5"}})
    assert pairs.categories == ["Q1", "Q2"] and pairs.series[0].values == [1200, 3.5]
    # Units that disagree are not a unit; the values are never rescaled.
    assert pairs.unit is None


def test_an_unknown_type_is_built_as_columns_and_said():
    chart = PlanChart.model_validate({**REVENUE, "type": "radar"})
    assert (chart.type, chart.asked_type) == ("column", "radar")
    again = PlanChart.model_validate(chart.model_dump())
    assert again.asked_type == "radar"


def test_design_keys_are_set_aside_and_unknown_keys_are_content():
    chart = PlanChart.model_validate(
        {
            **REVENUE,
            "colors": ["#ff0000"],
            "series": [{"name": "R", "values": [1, 2, 3, 4], "color": "red"}],
            "footnote": "Source: finance",
        }
    )
    assert chart.style_fields == ["colors", "series.color"]
    assert chart.ignored_fields == ["footnote 'Source: finance'"]


def test_a_chart_slide_infers_the_chart_kind_first():
    plan = _plan(_chart_slide(REVENUE)).slides[1]
    assert infer_kinds(plan) == ["chart", "bullets", "two_columns", "image_text"]


# --- validation -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chart", "problem", "option"),
    [
        (
            {**REVENUE, "series": [{"name": "Costs", "values": [1, 2, 3]}]},
            "chart.series[0] 'Costs' has 3 values for 4 categories",
            "give one value per category",
        ),
        (
            {**REVENUE, "series": [{"name": "R", "values": [1, "n/a", 3, 4]}]},
            "chart.series[0].values[1] 'n/a' is not a number",
            "drop that category",
        ),
        (
            {
                **REVENUE,
                "type": "pie",
                "series": [
                    {"name": "A", "values": [1, 2, 3, 4]},
                    {"name": "B", "values": [1, 2, 3, 4]},
                ],
            },
            "a 'pie' chart shows one series, 2 given",
            "use type 'column'",
        ),
        (
            {
                **REVENUE,
                "series": [{"name": f"S{n}", "values": [1, 2, 3, 4]} for n in range(6)],
            },
            "chart: 6 series; at most 4 stay readable",
            "keep the 4 that matter",
        ),
        (
            {
                "type": "pie",
                "categories": [f"C{n}" for n in range(8)],
                "series": [{"name": "Share", "values": [1] * 8}],
            },
            "a 'pie' chart: 8 slices; at most 6 stay readable",
            "group the smallest as 'Other'",
        ),
        (
            {"type": "column", "categories": [], "series": []},
            "chart: no data",
            "give `chart`",
        ),
    ],
)
def test_bad_chart_data_is_a_named_revision(builtin, chart, problem, option):
    _, inventory = builtin
    found = _problem(_assigned(inventory, _chart_slide(chart)))
    assert problem in found["problem"]
    assert any(option in o for o in found["options"]), found["options"]


def test_too_much_for_the_zone_is_measured_never_split(builtin):
    _, inventory = builtin
    many = {
        "type": "column",
        "categories": [f"M{n}" for n in range(20)],
        "series": [{"name": "Sales", "values": list(range(20))}],
    }
    found = _problem(_assigned(inventory, _chart_slide(many)))
    assert "chart: 20 categories; this chart holds 12" in found["problem"]
    label = "Second quarter of the fiscal year, after the reorganisation of all teams"
    long = {**REVENUE, "categories": ["Q1", label, "Q3", "Q4"]}
    found = _problem(_assigned(inventory, _chart_slide(long)))
    assert (
        f"chart.categories[1] is {len(label)} chars; each label holds"
        in found["problem"]
    )
    assert any(o.startswith("shorten every category label") for o in found["options"])


# --- where the chart goes ---------------------------------------------------------------


def _chartless(inventory: TemplateInventory) -> TemplateInventory:
    """The template without its chart slides nor any content area able to host one."""
    patterns = [
        p.model_copy(
            update={
                "zones": [
                    z.model_copy(update={"chart_capable": False}) for z in p.zones
                ]
            }
        )
        for p in inventory.patterns
        if p.kind != "chart"
    ]
    return inventory.model_copy(update={"patterns": patterns})


def test_a_takeaway_goes_beside_the_chart_and_a_bare_chart_spans_the_slide(builtin):
    _, inventory = builtin
    assignment = _assigned(
        inventory,
        _chart_slide(REVENUE, bullets=["Q4 is 75 % above Q1"]),
        _chart_slide(REVENUE),
    )
    assert not assignment.problems
    labels = [p.label for p in assignment.patterns if p is not None]
    assert labels[1:] == [
        "Charts stay native and editable",
        "One chart across the slide",
    ]


def test_a_content_area_hosts_the_chart_when_no_chart_slide_exists():
    template = build_layouts_only_template()
    inventory = analyze_template(template).inventory
    assert inventory is not None
    assignment = _assigned(inventory, _chart_slide(REVENUE))
    assert not assignment.problems
    pattern = assignment.patterns[1]
    assert pattern is not None and pattern.name == "Title and Content"
    assert any(
        "instead of 'chart', the chart in its content area" in n
        for n in assignment.notes
    )
    result = _render(template, inventory, _chart_slide(REVENUE))
    (frame,) = _charts(result)
    zone = next(z for z in pattern.zones if z.chart_capable)
    assert round(frame.left * 1000 / inventory.slide_width) == zone.box.x
    assert round(frame.width * 1000 / inventory.slide_width) == zone.box.w
    built = result.report.built[1]
    assert built.kind == "bullets"
    assert [(n.code, n.kind) for n in built.notes] == [("other_kind", "chart")]
    # The content area holds the chart, not the "Click to add text" prompt.
    deck = Presentation(io.BytesIO(result.pptx))
    assert len(deck.slides[1].shapes) == 2


def test_bullets_in_the_only_content_area_leave_no_place_for_the_chart():
    found_inventory = analyze_template(build_layouts_only_template()).inventory
    assert found_inventory is not None
    kept = ("Title Slide", "Title and Content")
    inventory = found_inventory.model_copy(
        update={"patterns": [p for p in found_inventory.patterns if p.name in kept]}
    )
    found = _problem(_assigned(inventory, _chart_slide(REVENUE, bullets=["Why"])))
    assert "chart: this slide has no place for it" in found["problem"]
    assert "give the chart a slide of its own (title and chart)" in found["options"]


def test_a_template_without_any_chart_place_asks_for_another_form(builtin):
    inventory = _chartless(builtin[1])
    found = _problem(_assigned(inventory, _chart_slide(REVENUE)))
    assert found["problem"] == "chart: this template has no slide for a chart"
    assert "give the 4 values as items of a 'figures' slide" not in " ".join(
        found["options"]
    )  # the built-in figures slide holds 3
    assert found["options"][-1] == "keep the key numbers as bullets"
    small = {**REVENUE, "categories": ["Q1", "Q2", "Q3"]}
    small["series"] = [{"name": "Revenue", "values": [1, 2, 3]}]
    found = _problem(_assigned(inventory, _chart_slide(small)))
    assert any("as items of a 'figures' slide" in o for o in found["options"])


def test_a_chart_slide_needs_a_chart(builtin):
    _, inventory = builtin
    assignment = _assigned(
        inventory, {"title": "Revenue", "bullets": ["Up"], "kind": "chart"}
    )
    assert all(p is None or p.kind != "chart" for p in assignment.patterns)


def test_chart_slides_are_never_asked_to_become_another_kind(builtin):
    _, inventory = builtin
    slides = [_chart_slide(REVENUE, title=f"Revenue {n}") for n in range(4)]
    assignment = assign(inventory, _plan(*slides), "kind", 2)
    repeats = [r for r in assignment.repeats if r.kind == "chart"]
    assert repeats and all(not r.suggested and not r.others for r in repeats)


# --- the drawing ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "xl_type"),
    [
        ("column", XL_CHART_TYPE.COLUMN_CLUSTERED),
        ("bar", XL_CHART_TYPE.BAR_CLUSTERED),
        ("line", XL_CHART_TYPE.LINE_MARKERS),
        ("pie", XL_CHART_TYPE.PIE),
        ("doughnut", XL_CHART_TYPE.DOUGHNUT),
        ("stacked_column", XL_CHART_TYPE.COLUMN_STACKED),
        ("area", XL_CHART_TYPE.AREA),
    ],
)
def test_each_type_builds_a_native_chart(builtin, kind, xl_type):
    template, inventory = builtin
    result = _render(template, inventory, _chart_slide({**REVENUE, "type": kind}))
    chart = _chart(result)
    assert chart.chart_type == xl_type
    assert list(chart.plots[0].categories) == ["Q1", "Q2", "Q3", "Q4"]
    assert list(chart.plots[0].series[0].values) == [12, 15, 18, 21]


def test_colours_and_fonts_come_from_the_theme(builtin):
    template, inventory = builtin
    three = {
        **REVENUE,
        "series": [{"name": f"S{n}", "values": [1, 2, 3, 4]} for n in range(3)],
    }
    result = _render(template, inventory, _chart_slide(three))
    xml = _chart(result)._chartSpace.xml
    for accent in ("accent1", "accent2", "accent3"):
        assert f'<a:schemeClr val="{accent}"/>' in xml
    assert "srgbClr" not in xml
    assert '<a:latin typeface="+mn-lt"/>' in xml


def test_the_chart_takes_the_zone_and_no_example_frame_is_left(builtin):
    template, inventory = builtin
    result = _render(template, inventory, _chart_slide(REVENUE, bullets=["Up"]))
    (frame,) = _charts(result)
    pattern = next(p for p in inventory.patterns if p.label.startswith("Charts stay"))
    zone = next(z for z in pattern.zones if z.role == "chart")
    assert round(frame.top * 1000 / inventory.slide_height) == zone.box.y
    assert round(frame.width * 1000 / inventory.slide_width) == zone.box.w
    deck = Presentation(io.BytesIO(result.pptx))
    xml = deck.slides[1].shapes._spTree.xml
    assert xml.count("<c:chart ") == 1 and "Charts use theme colours" not in xml


def test_native_chart_slide_adds_editable_chart_with_title(builtin):
    # Adapted from fred-capability-pptx-generator.
    template, inventory = builtin
    result = _render(template, inventory, _chart_slide({**REVENUE, "title": "Revenue"}))
    assert _chart(result).chart_title.text_frame.text == "Revenue"
    untitled = _chart(_render(template, inventory, _chart_slide(REVENUE)))
    assert not untitled.has_title


@pytest.mark.parametrize(
    ("kind", "series_count", "expect_legend"),
    [
        ("pie", 1, True),
        ("doughnut", 1, True),
        ("column", 1, False),
        ("column", 2, True),
    ],
)
def test_native_chart_legend_sits_below_when_shown(
    builtin, kind, series_count, expect_legend
):
    # Adapted from fred-capability-pptx-generator.
    template, inventory = builtin
    series = [{"name": f"S{n}", "values": [45, 35, 20]} for n in range(series_count)]
    chart = {"type": kind, "categories": ["Europe", "Intl", "France"], "series": series}
    built = _chart(_render(template, inventory, _chart_slide(chart)))
    assert built.has_legend is expect_legend
    if expect_legend:
        assert built.legend.position == XL_LEGEND_POSITION.BOTTOM
        assert built.legend.include_in_layout is False


def test_values_carry_their_unit_and_pies_their_percentages(builtin):
    template, inventory = builtin
    money = {
        **REVENUE,
        "unit": "M€",
        "series": [{"name": "R", "values": [1.5, 2, 3, 4]}],
    }
    built = _chart(_render(template, inventory, _chart_slide(money)))
    assert built.value_axis.tick_labels.number_format == '#,##0.0" M€"'
    assert built.plots[0].data_labels.number_format == '#,##0.0" M€"'
    pie = _chart(_render(template, inventory, _chart_slide({**REVENUE, "type": "pie"})))
    assert pie.plots[0].data_labels.show_percentage


PIE = {
    "type": "pie",
    "categories": ["Ventes", "R&D", "Support"],
    "series": [{"name": "Effectif", "values": [27, 15, 58]}],
}


@pytest.mark.parametrize(
    "key, raw, mode",
    [
        ("show", "value", "value"),
        ("show", "Values", "value"),
        ("display", "numbers", "value"),
        ("labels_as", "absolute", "value"),
        ("show", "pourcentages", "share"),
        ("show_as", "%", "share"),
        ("show", "both", "both"),
        ("display", "les deux", "both"),
    ],
)
def test_pie_labels_mode_is_read_from_loose_names(key, raw, mode):
    chart = PlanChart.model_validate({**PIE, key: raw})
    assert (chart.show, chart.asked_show, chart.ignored_fields) == (mode, None, [])
    assert PlanChart.model_validate(chart.model_dump()).show == mode


def test_pie_labels_mode_defaults_to_shares_and_keeps_labels_as_categories():
    chart = PlanChart.model_validate(
        {**PIE, "categories": None, "labels": ["A", "B", "C"]}
    )
    assert (chart.show, chart.categories) == (None, ["A", "B", "C"])
    schema = PlanChart.model_json_schema()["properties"]["show"]
    assert "set show: 'value'" in schema["description"]
    assert set(schema["anyOf"][0]["enum"]) == {"share", "value", "both"}


def test_an_unknown_pie_labels_mode_is_a_named_revision(builtin):
    _, inventory = builtin
    chart = PlanChart.model_validate({**PIE, "show": "bubbles"})
    assert (chart.show, chart.asked_show) == (None, "bubbles")
    assert PlanChart.model_validate(chart.model_dump()).asked_show == "bubbles"
    found = _problem(_assigned(inventory, _chart_slide({**PIE, "show": "bubbles"})))
    assert "chart.show 'bubbles' is not a label mode" in found["problem"]


def _labels_xml(built: Any) -> Any:
    (labels,) = built._chartSpace.iter(qn("c:dLbls"))
    return labels


@pytest.mark.parametrize(
    "show, value, percent, fmt, linked, separator",
    [
        (None, "0", "1", "0%", "0", None),
        ("share", "0", "1", "0%", "0", None),
        ("value", "1", "0", '#,##0" collaborateurs"', "0", None),
        ("both", "1", "1", '#,##0" collaborateurs"', "1", "\n"),
    ],
)
def test_pie_labels_show_what_the_plan_asks(
    builtin, show, value, percent, fmt, linked, separator
):
    template, inventory = builtin
    chart = {**PIE, "unit": "collaborateurs", **({"show": show} if show else {})}
    built = _chart(_render(template, inventory, _chart_slide(chart)))
    labels = _labels_xml(built)
    assert labels.find(qn("c:showVal")).get("val") == value
    assert labels.find(qn("c:showPercent")).get("val") == percent
    number = labels.find(qn("c:numFmt"))
    assert (number.get("formatCode"), number.get("sourceLinked")) == (fmt, linked)
    found = labels.find(qn("c:separator"))
    assert (found.text if found is not None else None) == separator
    # Linked, the value takes the series' own format: the unit, never "0%".
    (cache,) = built._chartSpace.iter(qn("c:formatCode"))
    assert cache.text == '#,##0" collaborateurs"'


def test_a_unit_hidden_by_percentages_is_told(builtin):
    template, inventory = builtin
    result = _render(
        template, inventory, _chart_slide({**PIE, "unit": "collaborateurs"})
    )
    assert (
        "Slide 2: the pie's labels show percentages, so unit 'collaborateurs' is not "
        "shown. To show the numbers with their unit, set chart.show to 'value' "
        "('both' for the number and its percentage)." in result.report.notes
    )
    built = result.report.built[1]
    assert [n.code for n in built.notes] == ["chart_shows_shares"]
    shares = _render(template, inventory, _chart_slide({**PIE, "unit": "%"}))
    assert not any("chart.show" in n for n in shares.report.notes)
    values = _render(
        template,
        inventory,
        _chart_slide({**PIE, "unit": "collaborateurs", "show": "value"}),
    )
    assert not any("chart.show" in n for n in values.report.notes)
    assert values.report.built[1].notes == []


def test_a_labels_mode_on_another_chart_type_is_told(builtin):
    template, inventory = builtin
    result = _render(template, inventory, _chart_slide({**REVENUE, "show": "share"}))
    assert (
        "Slide 2: chart.show 'share' was not applied: it sets the slice labels of a "
        "pie or doughnut only; a 'column' chart shows its values. Nothing to do; drop "
        "chart.show, or set chart.type to 'pie' or 'doughnut'." in result.report.notes
    )
    assert result.report.built[1].notes == []
    plain = _render(template, inventory, _chart_slide(REVENUE))
    assert not any("chart.show" in n for n in plain.report.notes)


def test_a_type_fallback_and_design_keys_are_told(builtin):
    template, inventory = builtin
    result = _render(
        template, inventory, _chart_slide({**REVENUE, "type": "radar", "color": "red"})
    )
    assert _chart(result).chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED
    notes = " ".join(result.report.notes)
    assert "chart type 'radar' is not offered; built as 'column'" in notes
    assert "the chart's color were ignored" in notes
    built = result.report.built[1]
    assert [(n.code, n.kind) for n in built.notes] == [("chart_type_changed", "radar")]


# --- changes and the tool ---------------------------------------------------------------


def _delivered(inventory: TemplateInventory, *slides: Dict[str, Any]) -> DeckPlan:
    plan = _plan(*slides)
    assignment = assign(inventory, plan, "off")
    deck, patterns, _ = assignment.deck(plan)
    return deck.model_copy(
        update={
            "delivered": True,
            "slides": [
                s.model_copy(update={"built_on": p.id if p else None})
                for s, p in zip(deck.slides, patterns)
            ],
        }
    )


def _changed(base: DeckPlan, *changes: Dict[str, Any], unplaced=None, cleared=None):
    return apply_changes(
        base, [SlideChange.model_validate(c) for c in changes], unplaced, cleared
    )


def test_a_chart_value_is_edited_on_the_same_template_slide(builtin):
    template, inventory = builtin
    base = _delivered(inventory, _chart_slide(REVENUE))
    edit = {"op": "edit", "slide": 2, "field": "chart.series[0].values[2]", "value": 30}
    plan = _changed(base, edit)
    assignment = assign(inventory, plan, "off")
    assert not assignment.problems
    pattern = assignment.patterns[1]
    assert pattern is not None and pattern.id == base.slides[1].built_on
    result = render_deck(template, inventory, plan, assignment.patterns)
    assert list(_chart(result).plots[0].series[0].values) == [12, 15, 30, 21]


def test_a_pie_is_edited_to_show_its_numbers(builtin):
    template, inventory = builtin
    base = _delivered(inventory, _chart_slide({**PIE, "unit": "collaborateurs"}))
    edit = {"op": "edit", "slide": 2, "field": "chart.show", "value": "value"}
    plan = _changed(base, edit)
    assert plan.slides[1].chart is not None and plan.slides[1].chart.show == "value"
    assignment = assign(inventory, plan, "off")
    assert not assignment.problems
    result = render_deck(template, inventory, plan, assignment.patterns)
    labels = _chart(result).plots[0].data_labels
    assert (labels.show_value, labels.show_percentage) == (True, False)
    assert labels.number_format == '#,##0" collaborateurs"'
    assert not any("chart.show" in n for n in result.report.notes)


def test_a_category_added_without_its_values_is_named(builtin):
    _, inventory = builtin
    base = _delivered(inventory, _chart_slide(REVENUE))
    plan = _changed(
        base, {"op": "edit", "slide": 2, "field": "chart.categories[4]", "value": "Q5"}
    )
    found = _problem(assign(inventory, plan, "off"))
    assert "chart.series[0] 'Revenue' has 4 values for 5 categories" in found["problem"]


def test_a_kind_edit_clears_the_chart_the_new_kind_cannot_show(builtin):
    _, inventory = builtin
    base = _delivered(inventory, _chart_slide(REVENUE, bullets=["Up"]))
    cleared: Dict[int, List[str]] = {}

    def unplaced(slide):
        from fred_capability_ppt_filler.builder.assign import unplaced as found

        return found(inventory, slide, slide.kind)

    plan = _changed(
        base,
        {"op": "edit", "slide": 2, "field": "kind", "value": "bullets"},
        unplaced=unplaced,
        cleared=cleared,
    )
    assert plan.slides[1].chart is None and cleared == {2: ["chart"]}
    plan = _changed(base, {"op": "edit", "slide": 2, "field": "chart", "value": None})
    assert plan.slides[1].chart is None


def test_the_tool_offers_charts_only_where_the_template_has_a_place(builtin):
    _, fred = builtin
    schema = tools._args_schema(fred).model_json_schema()
    assert "chart" in schema["$defs"]["BuildSlide"]["properties"]
    description = tools._description(fred, "template_slide", 2)
    assert (
        "chart {type, categories, series [{name, values}], title, unit, show}"
        in description
    )
    assert "to display numbers instead of percentages on a pie, set show: 'value'" in (
        description
    )
    assert '"chart.show"' in description
    assert "categories max 12" in tools.catalogue(fred)
    none = _chartless(fred)
    schema = tools._args_schema(none).model_json_schema()
    assert "chart" not in schema["$defs"]["BuildSlide"]["properties"]
    assert "chart {" not in tools._description(none, "template_slide", 2)
    content = analyze_template(build_layouts_only_template()).inventory
    assert content is not None
    assert "or a chart in place of the bullets" in tools.catalogue(content)
