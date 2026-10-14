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

"""Charts: the plan's data checked, measured against the zone that will show
it, and drawn as a native python-pptx chart styled by the template's theme.

The type mapping, chart-data construction, legend rule and series-length check
are adapted from ``fred-capability-pptx-generator``, by Shuigami.
"""

from __future__ import annotations

import copy
from typing import Any, List, Optional, Sequence, Tuple, cast

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    XL_TICK_MARK,
)
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from fred_capability_ppt_filler import text_metrics
from fred_capability_ppt_filler.builder.models import Zone
from fred_capability_ppt_filler.builder.plan import (
    MAX_SERIES,
    MAX_SLICES,
    PlanChart,
    capacity_text,
)
from fred_capability_ppt_filler.traversal import PlacedShape

XL_TYPES = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "stacked_column": XL_CHART_TYPE.COLUMN_STACKED,
    "area": XL_CHART_TYPE.AREA,
}
# The example chart's type in the plan's vocabulary (phase B reuses it).
_FROM_XL = {xl: name for name, xl in XL_TYPES.items()} | {
    XL_CHART_TYPE.LINE: "line",
    XL_CHART_TYPE.PIE_EXPLODED: "pie",
    XL_CHART_TYPE.DOUGHNUT_EXPLODED: "doughnut",
}
_ROUND = ("pie", "doughnut")
_ACCENTS = (
    MSO_THEME_COLOR.ACCENT_1,
    MSO_THEME_COLOR.ACCENT_2,
    MSO_THEME_COLOR.ACCENT_3,
    MSO_THEME_COLOR.ACCENT_4,
    MSO_THEME_COLOR.ACCENT_5,
    MSO_THEME_COLOR.ACCENT_6,
)
# Readability caps, and the share of the frame the plot gets beside its axes.
_MAX_CATEGORIES = {"line": 24, "area": 24}
_MAX_CATEGORIES_DEFAULT = 12
_LABELLED_BARS = 8
# The catalogue quotes a label's room among this many categories.
QUOTED_CATEGORIES = 6
_PLOT_W = 0.85
_PLOT_H = 0.75
_CATEGORY_EM = 3.0
_BAR_LINES = 2.2
_EMU_PER_PT = 12700


def type_of(chart: Any) -> Optional[str]:
    """The plan type an existing chart shows, or None for another kind of chart."""
    try:
        return _FROM_XL.get(chart.chart_type)
    except (KeyError, NotImplementedError, ValueError):
        return None


def chart_pt(zone: Zone) -> float:
    """One text size for axes, legend and labels: two thirds of the zone's."""
    return float(min(14, max(10, round((zone.font_pt or 18.0) * 2 / 3))))


def _frame_pt(zone: Zone, size: Tuple[int, int]) -> Tuple[float, float]:
    return (
        zone.box.w / 1000 * size[0] / _EMU_PER_PT,
        zone.box.h / 1000 * size[1] / _EMU_PER_PT,
    )


def max_categories(zone: Zone, kind: str, size: Tuple[int, int]) -> int:
    if kind in _ROUND:
        return MAX_SLICES
    width, height = _frame_pt(zone, size)
    pt = chart_pt(zone)
    if kind == "bar":
        room = height * _PLOT_H / (pt * text_metrics.LINE_HEIGHT * _BAR_LINES)
    else:
        room = width * _PLOT_W / (pt * _CATEGORY_EM)
    cap = _MAX_CATEGORIES.get(kind, _MAX_CATEGORIES_DEFAULT)
    return max(2, min(cap, int(room)))


def label_room(
    zone: Zone, kind: str, size: Tuple[int, int], count: int
) -> Tuple[int, int]:
    """(chars per line, lines) of one category label among ``count``."""
    width, _ = _frame_pt(zone, size)
    plot = width * _PLOT_W
    if kind in _ROUND:
        span, lines = plot / 3, 1
    elif kind == "bar":
        span, lines = plot * 0.4, 2
    else:
        span, lines = plot / max(1, count), 2
    return text_metrics.chars_per_line(span, chart_pt(zone), None, False), lines


def _name_room(zone: Zone, size: Tuple[int, int], count: int) -> int:
    width, _ = _frame_pt(zone, size)
    span = width * _PLOT_W / max(1, min(count, MAX_SERIES))
    return text_metrics.chars_per_line(span, chart_pt(zone), None, False)


def _title_room(zone: Zone, size: Tuple[int, int]) -> int:
    width, _ = _frame_pt(zone, size)
    return text_metrics.chars_per_line(width, chart_pt(zone) * 1.2, None, True)


def data_problems(chart: PlanChart) -> List[Tuple[str, str]]:
    """What is wrong with the chart's data whatever slide shows it: (what, fix)."""
    found: List[Tuple[str, str]] = []
    count = len(chart.categories)
    if not count or not chart.series:
        return [
            (
                "chart: no data; give categories and at least one series",
                "give `chart` {type, categories, series [{name, values}]}, or drop it",
            )
        ]
    if chart.type in _ROUND and len(chart.series) > 1:
        found.append(
            (
                f"a '{chart.type}' chart shows one series, {len(chart.series)} given",
                "keep one series, or use type 'column'",
            )
        )
    elif len(chart.series) > MAX_SERIES:
        found.append(
            (
                f"chart: {len(chart.series)} series; at most {MAX_SERIES} stay readable",
                f"keep the {MAX_SERIES} that matter, or split them over two charts",
            )
        )
    if chart.type in _ROUND and count > MAX_SLICES:
        found.append(
            (
                f"a '{chart.type}' chart: {count} slices; at most {MAX_SLICES} stay readable",
                f"keep {MAX_SLICES - 1} and group the smallest as 'Other', or use type 'bar'",
            )
        )
    for j, series in enumerate(chart.series):
        at = f"chart.series[{j}]"
        named = f" '{series.name}'" if series.name else ""
        if len(series.values) != count:
            found.append(
                (
                    f"{at}{named} has {len(series.values)} values for {count} categories",
                    "give one value per category, in the categories' order",
                )
            )
        for i, text in sorted(series.unread.items()):
            found.append(
                (
                    f"{at}.values[{i}] '{text}' is not a number",
                    "write a number, or drop that category",
                )
            )
        if len(chart.series) > 1 and not series.name:
            found.append((f"{at} has no name", "name each series: the legend shows it"))
    if chart.type in _ROUND:
        values = [v for s in chart.series[:1] for v in s.values if v is not None]
        if any(v < 0 for v in values) or (values and not any(values)):
            found.append(
                (
                    f"a '{chart.type}' chart needs shares: positive values, not all 0",
                    "use type 'column' or 'bar' for these values",
                )
            )
    return found


def fit_problems(
    zone: Zone, chart: PlanChart, size: Tuple[int, int]
) -> List[Tuple[str, str]]:
    """What does not fit this zone at a readable size: (what, fix)."""
    found: List[Tuple[str, str]] = []
    count = len(chart.categories)
    most = max_categories(zone, chart.type, size)
    if count > most and chart.type not in _ROUND:
        found.append(
            (
                f"chart: {count} categories; this chart holds {most}",
                f"keep {most} categories (group the rest, or a coarser period)",
            )
        )
    per_line, lines = label_room(zone, chart.type, size, min(count, most))
    room = capacity_text(per_line, lines)
    long = [(i, c) for i, c in enumerate(chart.categories) if len(c) > per_line * lines]
    if long:
        i, label = max(long, key=lambda pair: len(pair[1]))
        found.append(
            (
                f"chart.categories[{i}] is {len(label)} chars; each label holds {room}",
                f"shorten every category label to {room}",
            )
        )
    if len(chart.series) > 1 or chart.type in _ROUND:
        name_room = _name_room(zone, size, len(chart.series))
        for j, series in enumerate(chart.series):
            if len(series.name) > name_room:
                found.append(
                    (
                        f"chart.series[{j}].name is {len(series.name)} chars; the legend "
                        f"holds {capacity_text(name_room, 1)}",
                        f"shorten the series names to {capacity_text(name_room, 1)}",
                    )
                )
                break
    title_room = _title_room(zone, size)
    if chart.title and len(chart.title) > title_room:
        found.append(
            (
                f"chart.title is {len(chart.title)} chars; it holds "
                f"{capacity_text(title_room, 1)}",
                f"shorten chart.title to {capacity_text(title_room, 1)}, or leave it out "
                "(the slide title says it)",
            )
        )
    return found


# --- drawing -------------------------------------------------------------------------


def _decimals(values: Sequence[Optional[float]]) -> int:
    return max(
        (len(f"{v:.2f}".rstrip("0").split(".")[1]) for v in values if v is not None),
        default=0,
    )


def number_format(chart: PlanChart) -> str:
    """``#,##0.0" M€"``: the data's own decimals (at most 2), then its unit."""
    decimals = _decimals([v for s in chart.series for v in s.values])
    base = "#,##0" + ("." + "0" * decimals if decimals else "")
    unit = (chart.unit or "").replace('"', "").strip()
    if not unit:
        return base
    return f'{base}"{unit}"' if unit == "%" else f'{base}" {unit}"'


def _theme_fill(fmt: Any, accent: MSO_THEME_COLOR) -> None:
    fmt.fill.solid()
    fmt.fill.fore_color.theme_color = accent


def _text(font: Any, pt: float, bold: bool = False) -> None:
    font.size = Pt(pt)
    font.bold = bold
    font.color.theme_color = MSO_THEME_COLOR.TEXT_1
    font.color.brightness = 0.25


def _colour(built: Any, chart: PlanChart) -> None:
    plot = built.plots[0]
    if chart.type in _ROUND:
        plot.vary_by_categories = True
        for i, point in enumerate(plot.series[0].points):
            _theme_fill(point.format, _ACCENTS[i % len(_ACCENTS)])
            # A thin background-coloured edge keeps neighbouring slices apart.
            point.format.line.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1
            point.format.line.width = Pt(1.5)
        return
    for i, series in enumerate(plot.series):
        accent = _ACCENTS[i % len(_ACCENTS)]
        if chart.type == "line":
            series.format.line.color.theme_color = accent
            series.format.line.width = Pt(2.25)
            series.smooth = False
            series.marker.style = XL_MARKER_STYLE.CIRCLE
            series.marker.size = 7
            _theme_fill(series.marker.format, accent)
            series.marker.format.line.color.theme_color = accent
        else:
            _theme_fill(series.format, accent)


def _labels(built: Any, chart: PlanChart, pt: float, fmt: str) -> None:
    plot = built.plots[0]
    single_bars = (
        chart.type in ("column", "bar")
        and len(chart.series) == 1
        and len(chart.categories) <= _LABELLED_BARS
    )
    if chart.type not in _ROUND and not single_bars:
        return
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format_is_linked = False
    _text(labels.font, pt)
    if chart.type in _ROUND:
        labels.number_format = "0%"
        labels.show_percentage = True
        labels.show_value = False
        if chart.type == "pie":
            labels.position = XL_LABEL_POSITION.OUTSIDE_END
        else:
            # A doughnut's labels sit on the ring: the background colour reads on accents.
            labels.font.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1
            labels.font.bold = True
        return
    labels.number_format = fmt
    labels.show_value = True
    labels.position = XL_LABEL_POSITION.OUTSIDE_END


def _axes(built: Any, fmt: str) -> None:
    category, value = built.category_axis, built.value_axis
    value.has_major_gridlines = True
    gridlines = value.major_gridlines.format.line
    gridlines.color.theme_color = MSO_THEME_COLOR.TEXT_1
    gridlines.color.brightness = 0.85
    gridlines.width = Pt(0.75)
    value.format.line.fill.background()
    value.major_tick_mark = XL_TICK_MARK.NONE
    value.tick_labels.number_format = fmt
    value.tick_labels.number_format_is_linked = False
    category.major_tick_mark = XL_TICK_MARK.NONE
    category.format.line.color.theme_color = MSO_THEME_COLOR.TEXT_1
    category.format.line.color.brightness = 0.6


def _hole(built: Any) -> None:
    for node in built._chartSpace.iter(qn("c:holeSize")):
        node.set("val", "55")


def draw(slide: Any, host: PlacedShape, zone: Zone, chart: PlanChart) -> Any:
    """Replace ``host`` (a chart or content placeholder, or a duplicated chart
    frame) with a native chart at its box and drawing-order place."""
    data = CategoryChartData(number_format=number_format(chart))
    data.categories = chart.categories
    for series in chart.series:
        if len(series.values) != len(chart.categories):
            raise ValueError(
                f"chart series '{series.name}' has {len(series.values)} value(s) for "
                f"{len(chart.categories)} categories"
            )
        data.add_series(series.name, [v if v is not None else 0 for v in series.values])
    frame = slide.shapes.add_chart(
        XL_TYPES[chart.type],
        Emu(host.left),
        Emu(host.top),
        Emu(host.width),
        Emu(host.height),
        data,
    )
    old = cast(Any, host.shape)._element
    # In a placeholder the chart keeps its link, as PowerPoint's "insert chart" does.
    placeholder = old.find(f".//{qn('p:nvPr')}/{qn('p:ph')}")
    if placeholder is not None:
        props = frame._element.find(f"{qn('p:nvGraphicFramePr')}/{qn('p:nvPr')}")
        props.insert(0, copy.deepcopy(placeholder))
    tree = old.getparent()
    if tree is not None:
        tree.replace(old, frame._element)

    built = frame.chart
    pt = chart_pt(zone)
    fmt = number_format(chart)
    _text(built.font, pt)
    built.font.name = "+mn-lt"  # the theme's body font, never a literal face
    if chart.title:
        built.has_title = True
        built.chart_title.text_frame.text = chart.title
        _text(built.chart_title.text_frame.paragraphs[0].runs[0].font, pt * 1.2, True)
    else:
        # Untitled, a one-series chart would show its series name as a title.
        built.has_title = False
    # A pie's slices are its categories: without a legend nothing says which is which.
    built.has_legend = chart.type in _ROUND or len(chart.series) > 1
    if built.has_legend:
        built.legend.position = XL_LEGEND_POSITION.BOTTOM
        built.legend.include_in_layout = False
        _text(built.legend.font, pt)
    _colour(built, chart)
    _labels(built, chart, pt, fmt)
    if chart.type in _ROUND:
        _hole(built)
    else:
        _axes(built, fmt)
        if chart.type in ("column", "bar", "stacked_column"):
            built.plots[0].gap_width = 60 if chart.type == "stacked_column" else 80
    return frame
