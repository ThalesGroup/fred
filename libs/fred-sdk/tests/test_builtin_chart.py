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


@pytest.mark.parametrize("chart_type", ["bar", "line", "area", "pie", "table"])
def test_render_chart_preserves_rows(chart_type: str) -> None:
    rows = [{"label": "Q1", "value": "12.5"}, {"label": "Q2", "value": None}]
    if chart_type == "pie":
        rows[1]["value"] = "0"
    payload = {"chart_type": chart_type, "title": "Revenue", "rows": rows}
    if chart_type != "table":
        payload.update(x_key="label", y_keys=["value"])
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
        {"chart_type": "scatter"},
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


def test_pie_rejects_negative_values() -> None:
    with pytest.raises(ValidationError, match="nonnegative"):
        render_chart(
            {
                "chart_type": "pie",
                "title": "Share",
                "rows": [{"label": "A", "value": -1}],
                "x_key": "label",
                "y_keys": ["value"],
            }
        )
