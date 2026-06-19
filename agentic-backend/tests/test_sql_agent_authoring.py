from agentic_backend.agents.v2.production.sql_analyst_graph import (
    SqlAgentDefinition,
)
from agentic_backend.agents.v2.production.sql_analyst_graph.sql_agent_state import (
    SqlAgentInput,
    SqlAgentState,
)
from agentic_backend.agents.v2.production.sql_analyst_graph.sql_agent_steps import (
    _choose_database_from_request,
    _is_graphable,
    _valid_numeric_keys,
)
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.core.chatbot.chat_schema import ChartPart
from agentic_backend.core.chatbot.message_part import hydrate_fred_parts


def _binding() -> BoundRuntimeContext:
    portable_context = PortableContext.model_construct(
        request_id="req-sql-agent",
        correlation_id="corr-sql-agent",
        actor="test-user",
        tenant="test-tenant",
        environment=PortableEnvironment.DEV,
        session_id="sql-agent-session",
        agent_id="production.sql_analyst.graph.v2",
    )
    return BoundRuntimeContext.model_construct(
        portable_context=portable_context,
        runtime_context=None,
    )


def test_sql_agent_builds_expected_topology() -> None:
    definition = SqlAgentDefinition()

    graph = definition.build_graph()
    mermaid = definition.preview().content

    assert graph.entry_node == "load_context"
    assert "load_context" in mermaid
    assert "choose_database" in mermaid
    assert "draft_sql" in mermaid
    assert "build_chart" in mermaid
    assert "finalize" in mermaid


def test_sql_agent_routes_synthesize_through_build_chart() -> None:
    definition = SqlAgentDefinition()

    edges = definition.workflow.edges
    assert edges["synthesize"] == "build_chart"
    assert edges["build_chart"] == "finalize"


def test_sql_agent_builds_initial_state() -> None:
    definition = SqlAgentDefinition()

    state = definition.build_initial_state(
        SqlAgentInput(message="Show me a sample query for sales."),
        _binding(),
    )

    typed_state = SqlAgentState.model_validate(state)
    assert typed_state.latest_user_text == "Show me a sample query for sales."
    assert typed_state.available_databases == []
    assert typed_state.selected_db is None
    assert typed_state.selected_tables == []
    # Tunable prompt is injected from the definition into state at run start
    assert typed_state.draft_sql_system_prompt == definition.draft_sql_system_prompt
    assert len(typed_state.draft_sql_system_prompt) > 0


def test_sql_agent_definition_has_expected_agent_id() -> None:
    definition = SqlAgentDefinition()

    assert definition.agent_id == "production.sql_analyst.graph.v2"


def test_sql_agent_auto_selects_database_from_table_name() -> None:
    selected_db = _choose_database_from_request(
        user_text="Show me recent orders from the sales table.",
        database_context={
            "warehouse": [{"table_name": "inventory"}],
            "analytics": [{"table_name": "sales"}],
        },
        available_databases=["warehouse", "analytics"],
    )

    assert selected_db == "analytics"


# ── Chart heuristics ───────────────────────────────────────────────────────


def test_is_graphable_accepts_category_plus_numeric() -> None:
    rows = [
        {"country": "FR", "amount": 120.0},
        {"country": "DE", "amount": 80.0},
        {"country": "US", "amount": 200.0},
    ]
    assert _is_graphable(rows) is True


def test_is_graphable_accepts_numeric_strings() -> None:
    rows = [
        {"country": "FR", "amount": "120.0"},
        {"country": "DE", "amount": "80.0"},
    ]
    assert _is_graphable(rows) is True


def test_is_graphable_rejects_non_graphable_shapes() -> None:
    # single row
    assert _is_graphable([{"country": "FR", "amount": 1}]) is False
    # only a categorical column, no numeric measure
    assert _is_graphable([{"a": "x"}, {"a": "y"}]) is False
    # only numeric columns, no categorical/temporal axis
    assert _is_graphable([{"a": 1, "b": 2}, {"a": 3, "b": 4}]) is False
    # empty
    assert _is_graphable([]) is False
    # too many rows
    assert _is_graphable([{"c": str(i), "v": i} for i in range(60)]) is False


def test_valid_numeric_keys_filters_unknown_and_non_numeric() -> None:
    rows = [{"country": "FR", "amount": 1, "note": "x"}]
    assert _valid_numeric_keys(rows, ["amount", "note", "missing"]) == ["amount"]


# ── build_output / ChartPart ─────────────────────────────────────────────────


def test_build_output_emits_chart_part() -> None:
    definition = SqlAgentDefinition()
    rows = [{"country": "FR", "amount": 120.0}, {"country": "DE", "amount": 80.0}]
    state = SqlAgentState(
        latest_user_text="spend by country",
        query_results=rows,
        chart_type="bar",
        chart_x_key="country",
        chart_y_keys=["amount"],
        chart_title="Spend by country",
        draft_sql="SELECT country, amount FROM concur",
        final_text="Here is the spend by country.",
    )

    output = definition.build_output(state)

    assert len(output.ui_parts) == 1
    part = output.ui_parts[0]
    assert isinstance(part, ChartPart)
    assert part.type == "chart"
    assert part.chart_type == "bar"
    assert part.x_key == "country"
    assert part.y_keys == ["amount"]
    assert part.rows == rows
    assert output.content == "Here is the spend by country."


def test_build_output_caps_rows_at_50() -> None:
    definition = SqlAgentDefinition()
    rows = [{"country": str(i), "amount": i} for i in range(120)]
    state = SqlAgentState(
        latest_user_text="spend",
        query_results=rows,
        chart_type="bar",
        chart_x_key="country",
        chart_y_keys=["amount"],
    )

    output = definition.build_output(state)

    assert len(output.ui_parts) == 1
    assert len(output.ui_parts[0].rows) == 50


def test_build_output_no_chart_when_table() -> None:
    definition = SqlAgentDefinition()
    state = SqlAgentState(
        latest_user_text="explain",
        query_results=[{"country": "FR", "amount": 1}],
        chart_type="table",
        final_text="A short textual answer.",
    )

    output = definition.build_output(state)

    assert output.ui_parts == ()
    assert output.content == "A short textual answer."


def test_hydrate_fred_parts_builds_chart_part() -> None:
    parts = hydrate_fred_parts(
        {
            "fred_parts": [
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "rows": [{"country": "FR", "amount": 1}],
                    "x_key": "country",
                    "y_keys": ["amount"],
                }
            ]
        }
    )

    assert len(parts) == 1
    assert isinstance(parts[0], ChartPart)
    assert parts[0].x_key == "country"
