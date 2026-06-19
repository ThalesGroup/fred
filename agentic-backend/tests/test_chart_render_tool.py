from __future__ import annotations

import pytest

from agentic_backend.core.agents.v2 import ToolInvocationRequest
from agentic_backend.core.agents.v2.support.builtins import (
    TOOL_REF_CHART_RENDER,
    BuiltinToolBackend,
    get_builtin_tool_spec,
)
from agentic_backend.core.agents.v2.support.builtins.catalog import ChartRenderToolArgs
from agentic_backend.core.chatbot.chat_schema import ChartPart
from agentic_backend.integrations.v2_runtime.adapters import (
    FredKnowledgeSearchToolInvoker,
    _build_chart_render_result,
)


def _portable_context():
    from agentic_backend.core.agents.v2 import PortableContext, PortableEnvironment

    return PortableContext.model_construct(
        request_id="req-chart",
        correlation_id="corr-chart",
        actor="test-user",
        tenant="test-tenant",
        environment=PortableEnvironment.DEV,
        session_id="chart-session",
    )


# ── Catalog registration ─────────────────────────────────────────────────────


def test_chart_render_is_registered_in_builtin_catalog() -> None:
    spec = get_builtin_tool_spec(TOOL_REF_CHART_RENDER)
    assert spec is not None
    assert spec.tool_ref == "chart.render"
    assert spec.backend == BuiltinToolBackend.TOOL_INVOKER
    assert spec.args_schema is ChartRenderToolArgs


def test_chart_render_args_schema_validates() -> None:
    args = ChartRenderToolArgs(
        chart_type="bar",
        x_key="country",
        y_keys=["amount"],
        rows=[{"country": "FR", "amount": 120}],
    )
    assert args.chart_type == "bar"
    assert args.x_key == "country"


# ── Chart-building helper ─────────────────────────────────────────────────────


def test_build_chart_render_result_builds_chart_part() -> None:
    rows = [{"country": "FR", "amount": 120}, {"country": "DE", "amount": 80}]
    part, summary = _build_chart_render_result(
        {
            "title": "Spend by country",
            "chart_type": "bar",
            "x_key": "country",
            "y_keys": ["amount"],
            "rows": rows,
        }
    )
    assert isinstance(part, ChartPart)
    assert part.type == "chart"
    assert part.chart_type.value == "bar"
    assert part.x_key == "country"
    assert part.y_keys == ["amount"]
    assert part.rows == rows
    assert "Spend by country" in summary


def test_build_chart_render_result_caps_rows_at_50() -> None:
    rows = [{"k": str(i), "v": i} for i in range(120)]
    part, _ = _build_chart_render_result({"x_key": "k", "y_keys": ["v"], "rows": rows})
    assert len(part.rows) == 50


def test_build_chart_render_result_defaults_unknown_chart_type_to_bar() -> None:
    part, _ = _build_chart_render_result(
        {
            "chart_type": "donut",
            "x_key": "k",
            "y_keys": ["v"],
            "rows": [{"k": "a", "v": 1}],
        }
    )
    assert part.chart_type.value == "bar"


@pytest.mark.parametrize(
    "payload",
    [
        {"y_keys": ["v"], "rows": [{"k": "a", "v": 1}]},  # missing x_key
        {"x_key": "k", "rows": [{"k": "a", "v": 1}]},  # missing y_keys
        {"x_key": "k", "y_keys": ["v"], "rows": []},  # empty rows
    ],
)
def test_build_chart_render_result_rejects_invalid_payloads(payload: dict) -> None:
    with pytest.raises(RuntimeError):
        _build_chart_render_result(payload)


# ── Invoker dispatch ──────────────────────────────────────────────────────────


def test_invoker_dispatches_chart_render() -> None:
    # Bypass __init__ (which builds network clients) — _invoke_chart_render is pure.
    invoker = object.__new__(FredKnowledgeSearchToolInvoker)
    request = ToolInvocationRequest(
        tool_ref=TOOL_REF_CHART_RENDER,
        payload={
            "chart_type": "line",
            "x_key": "month",
            "y_keys": ["sales"],
            "rows": [{"month": "Jan", "sales": 10}, {"month": "Feb", "sales": 20}],
        },
        context=_portable_context(),
    )

    result = invoker._invoke_chart_render(request)

    assert result.tool_ref == "chart.render"
    assert len(result.ui_parts) == 1
    assert isinstance(result.ui_parts[0], ChartPart)
    assert result.ui_parts[0].chart_type.value == "line"
    assert len(result.blocks) == 1
