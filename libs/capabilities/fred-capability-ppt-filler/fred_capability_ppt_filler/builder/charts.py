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
from fred_capability_ppt_filler.builder import lexicon
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
ROUND = ("pie", "doughnut")
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
    if kind in ROUND:
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
    if kind in ROUND:
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
    if chart.type in ROUND and chart.asked_show:
        found.append(
            (
                f"chart.show '{chart.asked_show}' is not a label mode",
                "use 'share' (percentages), 'value' (the numbers) or 'both'",
            )
        )
    if chart.type in ROUND and len(chart.series) > 1:
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
    if chart.type in ROUND and count > MAX_SLICES:
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
    if chart.type in ROUND:
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
    if count > most and chart.type not in ROUND:
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
    if len(chart.series) > 1 or chart.type in ROUND:
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


# --- intents ---------------------------------------------------------------------------

# Categories in time order: a sort would scramble them, and one point of their
# single line or area cannot be coloured apart (LibreOffice ignores point markers).
_ORDERED = ("line", "area")
# Opacity of muted text-colour points or series: below the accent on a light or
# a dark background alike; neighbours alternate so a legend still tells them apart.
_MUTED = (35000, 55000)


def _a(kind: str) -> str:
    return f"an {kind}" if kind == "area" else f"a {kind}"


def _names(values: Sequence[str]) -> List[str]:
    return [lexicon.normalize(v) for v in values]


def emphasis(chart: PlanChart) -> Optional[Tuple[str, int]]:
    """("series" | "category", index) of what ``highlight`` names, if it can show."""
    name = lexicon.normalize(chart.highlight or "")
    if not name:
        return None
    if len(chart.series) > 1 and chart.type not in ROUND:
        names = _names([s.name for s in chart.series])
        return ("series", names.index(name)) if name in names else None
    categories = _names(chart.categories)
    if chart.type in _ORDERED or name not in categories:
        return None
    return "category", categories.index(name)


def _highlight_note(chart: PlanChart) -> Optional[str]:
    asked = chart.asked_intents.get("highlight")
    if asked:
        return (
            f"chart.highlight '{asked}' names more than one; built without highlight. "
            "To set it, edit chart.highlight to the one name that matters."
        )
    if not chart.highlight or emphasis(chart) is not None:
        return None
    name = chart.highlight
    series = [s.name for s in chart.series]
    if len(series) > 1 and chart.type not in ROUND:
        if lexicon.normalize(name) in _names(chart.categories):
            return (
                f"chart.highlight '{name}' is a category, and this chart has "
                f"{len(series)} series: only a series can be emphasised. Built without "
                f"highlight; edit chart.highlight to one of the series "
                f"({', '.join(series)}), or keep one series."
            )
        return (
            f"chart.highlight '{name}' matches no series ({', '.join(series)}); built "
            "without highlight. To set it, edit chart.highlight to one of those (a "
            "name, never a colour)."
        )
    if chart.type in _ORDERED and lexicon.normalize(name) in _names(chart.categories):
        return (
            f"chart.highlight '{name}' was not applied: {_a(chart.type)} chart cannot "
            "emphasise one category. Nothing to do; drop chart.highlight, or use type "
            "'column' to emphasise it."
        )
    return (
        f"chart.highlight '{name}' matches no category ({', '.join(chart.categories)}); "
        "built without highlight. To set it, edit chart.highlight to one of those (a "
        "name, never a colour)."
    )


def intent_notes(chart: PlanChart) -> List[Tuple[str, str]]:
    """(field, note) for each intent the chart is built without."""
    found: List[Tuple[str, str]] = []
    highlight = _highlight_note(chart)
    if highlight:
        found.append(("highlight", highlight))
    asked = chart.asked_intents.get("sort")
    if asked:
        found.append(
            (
                "sort",
                f"chart.sort '{asked}' is not an order; built in the order given. To "
                "sort, edit chart.sort to 'desc' (largest first) or 'asc'.",
            )
        )
    elif chart.sort in ("desc", "asc") and chart.type in _ORDERED:
        found.append(
            (
                "sort",
                f"chart.sort '{chart.sort}' was not applied: {_a(chart.type)} chart keeps "
                "its categories in the order given (usually time). Nothing to do; drop "
                "chart.sort, or use type 'column' or 'bar' to sort.",
            )
        )
    asked = chart.asked_intents.get("stacked_as")
    if asked:
        found.append(
            (
                "stacked_as",
                f"chart.stacked_as '{asked}' is not a stacking; built with the values. "
                "Use 'percent' for stacked columns that each fill 100 %, or drop it.",
            )
        )
    elif chart.stacked_as == "percent" and chart.type != "stacked_column":
        found.append(
            (
                "stacked_as",
                f"chart.stacked_as 'percent' was not applied: it needs type "
                f"'stacked_column'; a '{chart.type}' chart was built. Nothing to do; drop "
                "chart.stacked_as, or set chart.type to 'stacked_column'.",
            )
        )
    return found


def _arranged(chart: PlanChart) -> PlanChart:
    """The chart in the order ``sort`` asks; the plan itself keeps the order written."""
    if chart.sort not in ("desc", "asc") or chart.type in _ORDERED:
        return chart
    count = len(chart.categories)
    if chart.type == "stacked_column":
        keys = [sum(s.values[i] or 0 for s in chart.series) for i in range(count)]
    else:
        keys = [v or 0 for v in chart.series[0].values]
    order = sorted(range(count), key=keys.__getitem__, reverse=chart.sort == "desc")
    if chart.type == "bar":
        # A bar chart draws its first category at the bottom: the first in order goes last.
        order.reverse()
    return chart.model_copy(
        update={
            "categories": [chart.categories[i] for i in order],
            "series": [
                s.model_copy(update={"values": [s.values[i] for i in order]})
                for s in chart.series
            ],
        }
    )


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


def _alpha(fmt: Any, path: str, alpha: Optional[int]) -> None:
    """``a:alpha`` on the colour at ``path`` under the format's ``c:spPr``."""
    if alpha is None:
        return
    colour = fmt._element.find(f"{qn('c:spPr')}/{path}/{qn('a:schemeClr')}")
    if colour is not None:
        colour.append(colour.makeelement(qn("a:alpha"), {"val": str(alpha)}))


def _theme_fill(fmt: Any, accent: MSO_THEME_COLOR, alpha: Optional[int] = None) -> None:
    fmt.fill.solid()
    fmt.fill.fore_color.theme_color = accent
    _alpha(fmt, qn("a:solidFill"), alpha)


def _theme_line(
    fmt: Any,
    accent: MSO_THEME_COLOR,
    width: Optional[float],
    alpha: Optional[int] = None,
) -> None:
    fmt.line.color.theme_color = accent
    if width is not None:
        fmt.line.width = Pt(width)
    _alpha(fmt, f"{qn('a:ln')}/{qn('a:solidFill')}", alpha)


def _tone(
    index: int, chosen: Optional[int], alternate: bool = True
) -> Tuple[MSO_THEME_COLOR, Optional[int]]:
    """Theme colour and opacity of point or series ``index``: its own accent, or
    with one ``chosen``, the first accent for it and muted text for the rest."""
    if chosen is None:
        return _ACCENTS[index % len(_ACCENTS)], None
    if index == chosen:
        return MSO_THEME_COLOR.ACCENT_1, None
    rank = index - (index > chosen) if alternate else 0
    return MSO_THEME_COLOR.TEXT_1, _MUTED[rank % 2]


def _text(font: Any, pt: float, bold: bool = False) -> None:
    font.size = Pt(pt)
    font.bold = bold
    font.color.theme_color = MSO_THEME_COLOR.TEXT_1
    font.color.brightness = 0.25


def _marker(
    owner: Any, colour: MSO_THEME_COLOR, alpha: Optional[int], size: int
) -> None:
    owner.marker.style = XL_MARKER_STYLE.CIRCLE
    owner.marker.size = size
    _theme_fill(owner.marker.format, colour, alpha)
    _theme_line(owner.marker.format, colour, None, alpha)


def _colour(built: Any, chart: PlanChart, target: Optional[Tuple[str, int]]) -> None:
    plot = built.plots[0]
    chosen = target[1] if target else None
    if chart.type in ROUND:
        plot.vary_by_categories = True
        for i, point in enumerate(plot.series[0].points):
            _theme_fill(point.format, *_tone(i, chosen))
            # A thin background-coloured edge keeps neighbouring slices apart.
            point.format.line.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1
            point.format.line.width = Pt(1.5)
        return
    if target and target[0] == "category":
        # Each bar coloured on its own: LibreOffice lays a series' opacity over its points.
        for i, point in enumerate(plot.series[0].points):
            _theme_fill(point.format, *_tone(i, chosen, alternate=False))
        return
    for i, series in enumerate(plot.series):
        colour, alpha = _tone(i, chosen)
        if chart.type == "line":
            stressed = chosen is None or i == chosen
            width = 2.25 if chosen is None else 3.0 if stressed else 1.5
            _theme_line(series.format, colour, width, alpha)
            series.smooth = False
            if stressed:
                _marker(series, colour, alpha, 7)
            else:
                series.marker.style = XL_MARKER_STYLE.NONE
        else:
            _theme_fill(series.format, colour, alpha)


def _labels(
    built: Any, chart: PlanChart, pt: float, fmt: str, target: Optional[Tuple[str, int]]
) -> None:
    plot = built.plots[0]
    point = target[1] if target and target[0] == "category" else None
    single_bars = (
        chart.type in ("column", "bar")
        and len(chart.series) == 1
        and len(chart.categories) <= _LABELLED_BARS
    )
    if chart.type not in ROUND and not single_bars:
        return
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format_is_linked = False
    _text(labels.font, pt)
    if chart.type in ROUND:
        _round_labels(labels, chart.show or "share", fmt)
        if chart.type == "pie":
            labels.position = XL_LABEL_POSITION.OUTSIDE_END
        elif point is None:
            # A doughnut's labels sit on the ring: the background colour reads on accents.
            labels.font.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1
            labels.font.bold = True
        if point is not None:
            _stress_label(plot, point, light=chart.type == "doughnut")
        return
    labels.number_format = fmt
    labels.show_value = True
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    if point is not None:
        _stress_label(plot, point)


def _stress_label(plot: Any, index: int, light: bool = False) -> None:
    """The emphasised point's label in bold, otherwise as the plot's shared labels
    (a series-level ``c:dLbls`` replaces them, so it repeats them)."""
    shared = plot._element.find(qn("c:dLbls"))
    if shared is None:
        return
    own = plot._element.find(qn("c:ser")).get_or_add_dLbls()
    for child in list(own):
        own.remove(child)
    label = own.makeelement(qn("c:dLbl"), {})
    label.append(label.makeelement(qn("c:idx"), {"val": str(index)}))
    skipped = (qn("c:showLeaderLines"), qn("c:leaderLines"), qn("c:extLst"))
    for child in shared:
        own.append(copy.deepcopy(child))
        if child.tag not in skipped:
            label.append(copy.deepcopy(child))
    own.insert(0, label)
    for run in label.iter(qn("a:defRPr")):
        run.set("b", "1")
        if light:
            # On the doughnut's accent ring, the label reads in the background colour.
            for colour in run.iter(qn("a:schemeClr")):
                colour.set("val", "bg1")
                for child in list(colour):
                    colour.remove(child)


def _round_labels(labels: Any, show: str, fmt: str) -> None:
    labels.show_percentage = show != "value"
    labels.show_value = show != "share"
    labels.number_format = "0%" if show == "share" else fmt
    if show == "both":
        # One label format applies to every field: linked, the value keeps the
        # series' format (its unit) and the percentage its own, on the next line.
        labels.number_format_is_linked = True
        _separator(labels._element, "\n")


def _separator(dlbls: Any, text: str) -> None:
    """``c:separator`` in its schema place: python-pptx has no accessor for it."""
    node = dlbls.find(qn("c:separator"))
    if node is None:
        node = dlbls.makeelement(qn("c:separator"), {})
        after = ("c:showLeaderLines", "c:leaderLines", "c:extLst")
        anchor = next((n for t in after for n in dlbls.iterchildren(qn(t))), None)
        if anchor is None:
            dlbls.append(node)
        else:
            anchor.addprevious(node)
    node.text = text


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
    for series in chart.series:
        if len(series.values) != len(chart.categories):
            raise ValueError(
                f"chart series '{series.name}' has {len(series.values)} value(s) for "
                f"{len(chart.categories)} categories"
            )
    chart = _arranged(chart)
    data = CategoryChartData(number_format=number_format(chart))
    data.categories = chart.categories
    for series in chart.series:
        data.add_series(series.name, [v if v is not None else 0 for v in series.values])
    percent = chart.type == "stacked_column" and chart.stacked_as == "percent"
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_STACKED_100 if percent else XL_TYPES[chart.type],
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
    built.has_legend = chart.type in ROUND or len(chart.series) > 1
    if built.has_legend:
        built.legend.position = XL_LEGEND_POSITION.BOTTOM
        built.legend.include_in_layout = False
        _text(built.legend.font, pt)
    target = emphasis(chart)
    _colour(built, chart, target)
    _labels(built, chart, pt, fmt, target)
    if chart.type in ROUND:
        _hole(built)
    else:
        _axes(built, "0%" if percent else fmt)
        if chart.type in ("column", "bar", "stacked_column"):
            built.plots[0].gap_width = 60 if chart.type == "stacked_column" else 80
    return frame
