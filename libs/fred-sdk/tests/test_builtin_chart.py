"""Contract checks for native chart data and validation."""

import pytest
from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union
from fred_sdk.support.builtins import ChartPart, render_chart
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def chart_part_union():
    rebuild_ui_part_union((ChartPart,))
    yield
    rebuild_ui_part_union(())


@pytest.mark.parametrize(
    "chart_type",
    [
        "bar",
        "bar_horizontal",
        "bar_stacked",
        "line",
        "area",
        "area_stacked",
        "pie",
        "donut",
        "scatter",
        "radar",
        "radial_bar",
        "funnel",
        "treemap",
        "composed",
        "table",
    ],
)
def test_render_chart_preserves_rows(chart_type: str) -> None:
    rows = [{"label": "Q1", "value": "12.5"}, {"label": "Q2", "value": None}]
    if chart_type in {"pie", "donut", "radial_bar", "funnel", "treemap"}:
        rows[1]["value"] = "0"
    if chart_type == "scatter":
        rows[0]["label"] = "1"
        rows[1]["label"] = "2"
    if chart_type == "composed":
        rows[0]["other"] = 4
        rows[1]["other"] = 2
    payload = {"chart_type": chart_type, "title": "Revenue", "rows": rows}
    if chart_type != "table":
        payload.update(
            x_key="label",
            y_keys=["value", "other"] if chart_type == "composed" else ["value"],
        )
    result = render_chart(payload)
    part = result.ui_parts[0]
    assert isinstance(part, ChartPart)
    assert part.rows == rows
    assert part.chart_type == chart_type


@pytest.mark.parametrize(
    "patch",
    [
        {"x_key": "missing"},
        {"y_keys": ["missing"]},
        {"rows": [{"label": "Q1", "value": "twelve"}]},
        {"rows": [{"label": "Q1", "value": float("inf")}]},
        {"rows": [{"label": "Q1", "value": True}]},
        {"rows": [{"label": "Q1", "value": {"nested": "bad"}}]},
        {"chart_type": "sunburst"},
        {"rows": [{"label": str(i), "value": i} for i in range(51)]},
        {"rows": [{"label": "x" * 50_001, "value": 1}]},
    ],
)
def test_invalid_chart_has_no_part(patch: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "chart_type": "bar",
        "title": "Revenue",
        "rows": [{"label": "Q1", "value": 12}],
        "x_key": "label",
        "y_keys": ["value"],
    }
    payload.update(patch)
    with pytest.raises(ValidationError):
        render_chart(payload)


@pytest.mark.parametrize("chart_type", ["bar", "table"])
@pytest.mark.parametrize("value", [9_007_199_254_740_992, -9_007_199_254_740_992])
def test_chart_rejects_integers_that_json_would_round(
    chart_type: str, value: int
) -> None:
    payload: dict[str, object] = {
        "chart_type": chart_type,
        "title": "Large values",
        "rows": [{"label": "A", "value": value}],
    }
    if chart_type == "bar":
        payload.update(x_key="label", y_keys=["value"])
    with pytest.raises(ValidationError, match="JavaScript-safe integers"):
        render_chart(payload)


@pytest.mark.parametrize(
    "chart_type", ["pie", "donut", "radial_bar", "funnel", "treemap"]
)
def test_share_views_reject_negative_values(chart_type: str) -> None:
    with pytest.raises(ValidationError, match="nonnegative"):
        render_chart(
            {
                "chart_type": chart_type,
                "title": "Share",
                "rows": [{"label": "A", "value": -1}],
                "x_key": "label",
                "y_keys": ["value"],
            }
        )


@pytest.mark.parametrize("chart_type", ["scatter", "composed", "funnel"])
def test_view_specific_mappings_are_rejected(chart_type: str) -> None:
    with pytest.raises(ValidationError):
        render_chart(
            {
                "chart_type": chart_type,
                "title": "Invalid view",
                "rows": [{"label": "A", "value": 1}],
                "x_key": "label",
                "y_keys": ["value", "value"] if chart_type == "funnel" else ["value"],
            }
        )


def test_long_form_grouped_bars_keep_source_rows() -> None:
    rows = [
        {"district": "A", "kind": "civil", "count": 4},
        {"district": "A", "kind": "military", "count": 5},
    ]
    result = render_chart(
        {
            "chart_type": "bar",
            "title": "Comparison",
            "rows": rows,
            "x_key": "district",
            "y_keys": ["count"],
            "group_key": "kind",
        }
    )
    part = result.ui_parts[0]
    assert isinstance(part, ChartPart)
    assert part.rows == rows
    assert part.group_key == "kind"


@pytest.mark.parametrize(
    "patch",
    [
        {"chart_type": "line"},
        {"group_key": "district"},
        {"group_key": "count"},
        {"y_keys": ["count", "extra"]},
        {
            "rows": [
                {"district": "A", "kind": "civil", "count": 4},
                {"district": "A", "kind": "civil", "count": 5},
            ]
        },
        {"rows": [{"district": "A", "kind": i, "count": i} for i in range(9)]},
        {
            "rows": [
                {"district": "A", "kind": 1, "count": 4},
                {"district": "A", "kind": 1.0, "count": 5},
            ]
        },
        {
            "rows": [
                {"district": "A", "kind": 0, "count": 4},
                {"district": "A", "kind": -0.0, "count": 5},
            ]
        },
        {"rows": [{"district": "A", "kind": 9_007_199_254_740_992, "count": 4}]},
    ],
)
def test_invalid_grouped_bars_are_rejected(patch: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "chart_type": "bar",
        "title": "Comparison",
        "rows": [{"district": "A", "kind": "civil", "count": 4}],
        "x_key": "district",
        "y_keys": ["count"],
        "group_key": "kind",
    }
    payload.update(patch)
    with pytest.raises(ValidationError):
        render_chart(payload)
