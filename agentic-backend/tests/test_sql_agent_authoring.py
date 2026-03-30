from agentic_backend.agents.v2.production.sql_analyst_graph import (
    SqlAgentDefinition,
)
from agentic_backend.agents.v2.production.sql_analyst_graph.sql_agent_state import (
    SqlAgentInput,
    SqlAgentState,
)
from agentic_backend.agents.v2.production.sql_analyst_graph.sql_agent_steps import (
    _choose_database_from_request,
)
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
)


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
    assert "finalize" in mermaid


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
