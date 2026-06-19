from __future__ import annotations

from agentic_backend.agents.v2.definition_refs import (
    EXPENSE_ANALYST_DEFINITION_REF,
    all_v2_definition_refs,
    class_path_for_definition_ref,
)
from agentic_backend.agents.v2.production.expense_analyst_graph import (
    ExpenseAgentDefinition,
)
from agentic_backend.agents.v2.production.expense_analyst_graph.expense_agent_state import (
    ChartSpecModel,
    ExpenseAgentInput,
    ExpenseAgentState,
    PeriodSpec,
)
from agentic_backend.agents.v2.production.expense_analyst_graph.expense_agent_steps import (
    _default_chart_spec,
    _is_graphable,
    _normalize_breakdowns,
    _parse_period,
    _year_predicate,
    build_planned_queries,
)
from agentic_backend.agents.v2.production.expense_analyst_graph.expense_agent_state import (
    AnalysisResult,
)
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.core.chatbot.chat_schema import ChartPart


def _binding() -> BoundRuntimeContext:
    portable_context = PortableContext.model_construct(
        request_id="req-expense",
        correlation_id="corr-expense",
        actor="test-user",
        tenant="test-tenant",
        environment=PortableEnvironment.DEV,
        session_id="expense-session",
        agent_id="production.expense_analyst.graph.v2",
    )
    return BoundRuntimeContext.model_construct(
        portable_context=portable_context,
        runtime_context=None,
    )


# ── Topology / wiring ────────────────────────────────────────────────────────


def test_expense_agent_topology() -> None:
    definition = ExpenseAgentDefinition()
    graph = definition.build_graph()
    mermaid = definition.preview().content

    assert graph.entry_node == "load_context"
    for node in (
        "choose_database",
        "understand_request",
        "clarify",
        "plan_analysis",
        "run_analysis",
        "build_charts",
        "synthesize",
        "finalize",
    ):
        assert node in mermaid


def test_expense_agent_routes_and_edges() -> None:
    definition = ExpenseAgentDefinition()
    edges = definition.workflow.edges
    routes = definition.workflow.routes

    assert edges["run_analysis"] == "build_charts"
    assert edges["build_charts"] == "synthesize"
    assert edges["synthesize"] == "finalize"

    assert routes["understand_request"]["clarify"] == "clarify"
    assert routes["understand_request"]["ready"] == "plan_analysis"
    assert routes["clarify"]["continue"] == "understand_request"
    assert routes["clarify"]["cancel"] == "finalize"


def test_expense_agent_initial_state_injects_tunables() -> None:
    definition = ExpenseAgentDefinition()
    state = definition.build_initial_state(
        ExpenseAgentInput(message="compare 2024 vs 2025"),
        _binding(),
    )
    typed = ExpenseAgentState.model_validate(state)
    assert typed.latest_user_text == "compare 2024 vs 2025"
    assert len(typed.chart_selection_prompt) > 0
    assert len(typed.synthesis_system_prompt) > 0
    assert typed.max_clarification_rounds == 3
    assert typed.period_a.year is None


def test_expense_agent_id() -> None:
    assert ExpenseAgentDefinition().agent_id == "production.expense_analyst.graph.v2"


# ── Registration ─────────────────────────────────────────────────────────────


def test_expense_agent_is_registered() -> None:
    assert EXPENSE_ANALYST_DEFINITION_REF == "v2.production.expense_analyst"
    assert EXPENSE_ANALYST_DEFINITION_REF in all_v2_definition_refs()
    assert class_path_for_definition_ref(EXPENSE_ANALYST_DEFINITION_REF) == (
        "agentic_backend.agents.v2.production.expense_analyst_graph."
        "expense_agent_definition.ExpenseAgentDefinition"
    )


# ── build_output: multiple, varied ChartParts ────────────────────────────────


def test_build_output_emits_multiple_varied_chart_parts() -> None:
    definition = ExpenseAgentDefinition()
    state = ExpenseAgentState(
        latest_user_text="compare",
        final_text="Spend rose 12%.",
        chart_specs=[
            ChartSpecModel(
                chart_type="line",
                x_key="month",
                y_keys=["total"],
                title="Trend",
                rows=[
                    {"month": "2024-01", "total": 10.0},
                    {"month": "2024-02", "total": 12.0},
                ],
            ),
            ChartSpecModel(
                chart_type="bar",
                x_key="label",
                y_keys=["total_a", "total_b"],
                title="By GBU",
                rows=[{"label": "CIS", "total_a": 100.0, "total_b": 140.0}],
            ),
            ChartSpecModel(
                chart_type="table",
                x_key="label",
                y_keys=["total"],
                rows=[{"label": "x", "total": 1.0}],
            ),
        ],
    )

    output = definition.build_output(state)

    assert len(output.ui_parts) == 2  # the "table" spec is skipped
    assert all(isinstance(p, ChartPart) for p in output.ui_parts)
    assert {p.chart_type.value for p in output.ui_parts} == {"line", "bar"}
    assert output.content == "Spend rose 12%."


def test_build_output_caps_chart_rows() -> None:
    definition = ExpenseAgentDefinition()
    state = ExpenseAgentState(
        latest_user_text="x",
        chart_specs=[
            ChartSpecModel(
                chart_type="bar",
                x_key="label",
                y_keys=["total"],
                rows=[{"label": str(i), "total": float(i)} for i in range(120)],
            )
        ],
    )
    output = definition.build_output(state)
    assert len(output.ui_parts) == 1
    assert len(output.ui_parts[0].rows) == 50


# ── Query building / French-format SQL ───────────────────────────────────────


def test_build_planned_queries_shapes() -> None:
    queries = build_planned_queries(
        table="concur",
        period_a=PeriodSpec(label="2024", year=2024),
        period_b=PeriodSpec(label="2025", year=2025),
        breakdowns=["Domain", "Type de frais"],
    )
    keys = {q.key for q in queries}
    assert keys == {"totals", "monthly_trend", "by_domain", "by_type_de_frais"}

    by_key = {q.key: q for q in queries}
    # Amounts are parsed from French comma decimals.
    assert "REPLACE(\"Montant approuvé\", ',', '.')" in by_key["by_domain"].sql
    # Comparison shape: one row per category with total_a and total_b.
    assert "total_a" in by_key["by_domain"].sql and "total_b" in by_key["by_domain"].sql
    # Year derived from the French 2-digit-year token.
    assert (
        "'20' || split_part(\"Date de la transaction\", ' ', 3)"
        in by_key["by_domain"].sql
    )
    # No LIMIT imposed on aggregations.
    assert "limit" not in by_key["by_domain"].sql.lower()
    assert "limit" not in by_key["monthly_trend"].sql.lower()
    # Trend is a monthly time series.
    assert by_key["monthly_trend"].intent == "trend"


def test_year_predicate_uses_derived_year() -> None:
    pred = _year_predicate(PeriodSpec(year=2024))
    assert pred == "('20' || split_part(\"Date de la transaction\", ' ', 3)) = '2024'"


def test_parse_period_extracts_year() -> None:
    assert _parse_period("2024").year == 2024
    assert _parse_period("en 2025 svp").year == 2025
    assert _parse_period("") is None


def test_normalize_breakdowns_maps_synonyms() -> None:
    assert _normalize_breakdowns(["GBU", "mode de transport"]) == [
        "Domain",
        "Type de frais",
    ]
    assert _normalize_breakdowns(["Domain", "Domain"]) == ["Domain"]
    assert _normalize_breakdowns(["unknown"]) == []


# ── Chart heuristics ─────────────────────────────────────────────────────────


def test_is_graphable() -> None:
    assert (
        _is_graphable([{"label": "FR", "total": 1.0}, {"label": "DE", "total": 2.0}])
        is True
    )
    assert _is_graphable([{"a": 1, "b": 2}]) is False  # only numeric columns
    assert _is_graphable([]) is False


def test_default_chart_spec_picks_line_for_trend() -> None:
    result = AnalysisResult(
        key="monthly_trend",
        title="Trend",
        intent="trend",
        rows=[{"month": "2024-01", "total": 10.0}, {"month": "2024-02", "total": 12.0}],
    )
    spec = _default_chart_spec(result)
    assert spec is not None
    assert spec.chart_type == "line"
    assert spec.x_key == "month"
    assert spec.y_keys == ["total"]


def test_default_chart_spec_picks_grouped_bar_for_comparison() -> None:
    result = AnalysisResult(
        key="by_domain",
        title="By GBU",
        intent="comparison",
        rows=[{"label": "CIS", "total_a": 100.0, "total_b": 140.0}],
    )
    spec = _default_chart_spec(result)
    assert spec is not None
    assert spec.chart_type == "bar"
    assert spec.x_key == "label"
    assert spec.y_keys == ["total_a", "total_b"]
