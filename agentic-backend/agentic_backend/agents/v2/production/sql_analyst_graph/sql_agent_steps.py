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

"""
Business steps for the SQL agent.

Read this file to understand how the agent discovers datasets, chooses a
database, drafts SQL, and produces the final answer.

Architecture notes:
- SQL drafting uses invoke_structured_model(SqlDraft) — the model fills a
  single typed `query` field. No string parsing, no ambiguity.
- The schema passed to the drafting model intentionally omits the database
  name. Database routing is handled by the execution layer (read_query
  db_name parameter), not by SQL syntax. Showing "Database: X" causes
  models to write "FROM X.table" which is a PostgreSQL schema-qualified
  reference that does not match the actual table location.
- The drafting system prompt is tunable: it is injected into state at
  workflow start from the definition's draft_sql_system_prompt field.
"""

from __future__ import annotations

import json
import re
from typing import Literal, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agentic_backend.core.agents.v2 import (
    GraphNodeContext,
    GraphNodeResult,
    HumanChoiceOption,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    StepResult,
    choice_step,
    finalize_step,
    model_text_step,
    typed_node,
)

from .sql_agent_state import SqlAgentState
from .tabular_capabilities import (
    get_database_context,
    read_query_rows,
    tables_for_database,
)


class SqlDraft(BaseModel):
    """Structured SQL query produced by the drafting model.

    Why a structured model instead of raw text:
    - Explicit contract: the model fills exactly one typed field.
    - No string stripping or markdown fence parsing needed.
    - The Field description reinforces plain table naming at the schema level.
    """

    query: str = Field(
        description=(
            "A single read-only SELECT query. "
            "Use plain table names with no prefix "
            "(e.g. FROM ship_tracks_demo, never FROM data.ship_tracks_demo)."
        )
    )


# ── Step: load_context ─────────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def load_context_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Load the databases currently available to the SQL agent.

    This is the first business step because the agent cannot choose a dataset
    or draft a query before it knows what tabular data exists.

    Use this step at the start of the workflow. It stores the raw context plus
    the sorted database names for the following selection step.
    """
    if state.database_context and state.available_databases:
        return StepResult()

    context.emit_status("load_context", "Loading tabular datasets.")
    database_context = await get_database_context(context)
    return StepResult(
        state_update={
            "database_context": database_context,
            "available_databases": sorted(database_context.keys()),
        }
    )


# ── Step: analyze_intent ───────────────────────────────────────────────────


class IntentDecision(BaseModel):
    intent: Literal["query_data", "show_metadata"] = Field(
        description=(
            "Choose 'show_metadata' when the user asks about capabilities, tools, "
            "available data, schemas, or what the agent can do. "
            "Choose 'query_data' when the user asks a question that requires running a SQL query to retrieve data."
        )
    )
    direct_response: str | None = Field(
        description=(
            "Required when intent is 'show_metadata'. "
            "Describe the agent's capabilities (what it can do, what queries it can run) "
            "and the available datasets it can query. "
            "Do not list raw table names mechanically — explain what the agent helps users accomplish."
        )
    )


@typed_node(SqlAgentState)
async def analyze_intent_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Decide if the user wants to query data or just see metadata.
    """
    summary = _format_database_summary(state.database_context)
    decision = cast(
        IntentDecision,
        await context.invoke_structured_model(
            IntentDecision,
            messages=[
                SystemMessage(
                    content=(
                        "You are a routing assistant for a SQL analyst agent.\n\n"
                        "This agent can:\n"
                        "- Answer questions by running SQL queries on tabular datasets\n"
                        "- Explore data: counts, aggregations, filters, joins, trends\n"
                        "- Describe available datasets and their columns\n"
                        "- Help users understand what data is available and what questions they can ask\n\n"
                        f"Available datasets:\n{summary}\n\n"
                        "Route 'show_metadata' for any question about capabilities, tools, available data, "
                        "or what the agent can do. Route 'query_data' only when data retrieval is needed."
                    )
                ),
                HumanMessage(content=state.latest_user_text),
            ],
            operation="analyze_intent",
        ),
    )

    if decision.intent == "show_metadata":
        return StepResult(
            state_update={
                "final_text": decision.direct_response or "Here is the available data.",
                "done_reason": "metadata_inquiry",
            },
            route_key="info",
        )

    return StepResult(route_key="query")


# ── Step: choose_database ──────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def choose_database_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Choose the database the SQL agent should use for this request.

    The step finishes immediately when no data is available or when there is
    only one possible database. It asks the user only when several databases
    are present.

    Use this step after context loading. It tries to infer the right database
    from the user request before falling back to an explicit choice.
    """
    if not state.available_databases:
        return StepResult(
            state_update={
                "final_text": "No tabular datasets are available for this request.",
                "done_reason": "no_tabular_data",
            },
            route_key="finish",
        )

    selected_db = _choose_database_from_request(
        user_text=state.latest_user_text,
        database_context=state.database_context,
        available_databases=state.available_databases,
    )
    if selected_db is not None:
        return StepResult(
            state_update={
                "selected_db": selected_db,
                "selected_tables": tables_for_database(
                    state.database_context, selected_db
                ),
            },
            route_key="selected",
        )

    options = tuple(
        HumanChoiceOption(id=f"db:{db_name}", label=db_name, default=index == 0)
        for index, db_name in enumerate(state.available_databases)
    )
    choice_id = await choice_step(
        context,
        stage="scope_selection",
        title="Choose database",
        question="Which database should the SQL agent use?",
        choices=options,
        metadata={"agent_family": "sql_agent"},
    )
    if choice_id is None or not choice_id.startswith("db:"):
        return StepResult(
            state_update={
                "final_text": "Database selection was cancelled.",
                "done_reason": "scope_selection_cancelled",
            },
            route_key="finish",
        )
    selected_db = choice_id.split(":", 1)[1]
    return StepResult(
        state_update={
            "selected_db": selected_db,
            "selected_tables": tables_for_database(state.database_context, selected_db),
        },
        route_key="selected",
    )


# ── Step: draft_sql ────────────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def draft_sql_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Draft one SQL query for the selected database.

    Uses invoke_structured_model(SqlDraft) so the model fills a single typed
    query field — no string parsing, no ambiguity about output format.

    The schema context passed to the model omits the database name on purpose:
    database routing is handled at execution time by read_query's db_name
    parameter, not by SQL syntax. Showing "Database: X" here would cause the
    model to write "FROM X.table_name" (a PostgreSQL schema prefix) which
    would fail at execution time.

    Use this step after database selection. The drafted SQL is stored in state
    for execute_sql_step.
    """
    if state.selected_db is None:
        return StepResult(
            state_update={
                "final_text": "No database scope is selected.",
                "done_reason": "missing_scope",
            }
        )

    tables = state.selected_tables or tables_for_database(
        state.database_context, state.selected_db
    )
    if not tables:
        return StepResult(
            state_update={
                "final_text": (
                    f"Database `{state.selected_db}` is available but no tables "
                    "were found for this request."
                ),
                "done_reason": "no_tables_in_selected_database",
            }
        )

    schema = _tables_schema_for_drafting(
        state.database_context, state.selected_db, tables
    )
    prompt = f"{state.draft_sql_system_prompt}\n\n{schema}"

    context.emit_status("draft_sql", f"Drafting SQL for {state.selected_db}.")
    draft = cast(
        SqlDraft,
        await context.invoke_structured_model(
            SqlDraft,
            messages=[
                SystemMessage(content=prompt),
                HumanMessage(content=state.latest_user_text),
            ],
            operation="draft_sql",
        ),
    )
    return StepResult(state_update={"draft_sql": draft.query.strip()})


# ── Step: execute_sql ──────────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def execute_sql_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Execute the drafted SQL query.
    """
    if not state.selected_db or not state.draft_sql:
        return StepResult(
            state_update={"execution_error": "Missing database or SQL query."}
        )

    context.emit_status("execute_sql", "Running query...")
    try:
        rows = await read_query_rows(
            context,
            db_name=state.selected_db,
            query=state.draft_sql,
            maximum=50,
        )
        return StepResult(state_update={"query_results": rows, "execution_error": None})
    except Exception as e:
        return StepResult(state_update={"execution_error": str(e)})


# ── Step: synthesize_answer ────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def synthesize_answer_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Generate the final answer based on the SQL results.
    """
    tables = state.selected_tables or tables_for_database(
        state.database_context, state.selected_db or ""
    )
    schema_context = _format_execution_context_for_synthesis(
        database_context=state.database_context,
        selected_db=state.selected_db,
        selected_tables=tables,
    )
    content = (
        f"{schema_context}\n\n"
        f"User Question: {state.latest_user_text}\n\n"
        f"SQL Query Used: {state.draft_sql}\n\n"
    )
    if state.execution_error:
        content += f"Execution Error: {state.execution_error}"
    else:
        results_json = json.dumps(state.query_results, indent=2, ensure_ascii=False)
        content += f"Query Results:\n{results_json}"

    answer = await model_text_step(
        context,
        operation="synthesize_answer",
        system_prompt=content,
        user_prompt="Summarize the answer for the user.",
    )

    return StepResult(
        state_update={
            "final_text": answer,
            "done_reason": "completed",
        }
    )


# ── Step: finalize ─────────────────────────────────────────────────────────


@typed_node(SqlAgentState)
async def finalize_sql_agent_step(
    state: SqlAgentState,
    context: GraphNodeContext,
) -> GraphNodeResult:
    """
    Finalize the SQL agent response.

    This step turns the accumulated business state into the final user-facing
    message.

    Use this as the terminal node when the workflow has already built the final
    text in state.
    """
    del context
    return finalize_step(
        final_text=state.final_text,
        fallback_text="The SQL agent finished without a final message.",
        done_reason=state.done_reason,
    )


# ── Private helpers ────────────────────────────────────────────────────────


def _tables_schema_for_drafting(
    database_context: dict[str, object],
    selected_db: str,
    selected_tables: list[str],
) -> str:
    """
    Format table names and columns for the SQL drafting model.

    Deliberately omits the database name. The database is already selected and
    will be passed as `db_name` to read_query at execution time — it must NOT
    appear as a schema prefix inside the SQL text. Showing "Database: X" here
    causes models to write "FROM X.table_name" which fails as a PostgreSQL
    schema-qualified reference.

    Use this helper in draft_sql_step. For user-facing context (answer
    synthesis), use _format_execution_context_for_synthesis instead.
    """
    selected_table_names = set(selected_tables)
    raw_tables = database_context.get(selected_db)
    if not isinstance(raw_tables, list):
        return f"Tables: {', '.join(selected_tables) or '(none)'}"

    lines: list[str] = []
    for table in raw_tables:
        if not isinstance(table, dict):
            continue
        table_name = table.get("table_name")
        if not isinstance(table_name, str) or table_name not in selected_table_names:
            continue
        row_count = table.get("row_count")
        row_count_text = f" ({row_count} rows)" if isinstance(row_count, int) else ""
        column_text = _format_column_list(table.get("columns"))
        lines.append(f"  • {table_name}{row_count_text}: {column_text}")

    if not lines:
        lines = [f"  • {t}" for t in selected_tables]

    return "Tables available for this query:\n" + "\n".join(lines)


def _format_execution_context_for_synthesis(
    database_context: dict[str, object],
    selected_db: str | None,
    selected_tables: list[str],
) -> str:
    """
    Format the full execution context for the answer synthesis model.

    Unlike _tables_schema_for_drafting, this includes the database name
    because the synthesis model needs it to produce an accurate user-facing
    answer (e.g. "I queried the `data` database").

    Use this helper in synthesize_answer_step only.
    """
    if not selected_db:
        return ""

    selected_table_names = set(selected_tables)
    raw_tables = database_context.get(selected_db)

    table_lines: list[str] = []
    if isinstance(raw_tables, list):
        for table in raw_tables:
            if not isinstance(table, dict):
                continue
            table_name = table.get("table_name")
            if (
                not isinstance(table_name, str)
                or table_name not in selected_table_names
            ):
                continue
            row_count = table.get("row_count")
            row_count_text = (
                f" ({row_count} rows)" if isinstance(row_count, int) else ""
            )
            column_text = _format_column_list(table.get("columns"))
            table_lines.append(
                f"  • Table: {table_name}{row_count_text}\n    Columns: {column_text}"
            )

    if not table_lines:
        table_lines.append(f"  • Tables: {', '.join(selected_tables)}")

    return "You have access to:\n- Database: {db}\n{tables}".format(
        db=selected_db,
        tables="\n".join(table_lines),
    )


def _format_database_summary(database_context: dict[str, object]) -> str:
    """
    Short summary for the intent router.
    """
    lines = ["Available Databases:"]
    for db_name, raw_tables in database_context.items():
        if isinstance(raw_tables, list):
            lines.append(f"- Database: {db_name}")
            for t in raw_tables:
                if isinstance(t, dict):
                    t_name = t.get("table_name")
                    if t_name:
                        cols = _format_column_list(t.get("columns"))
                        lines.append(f"  • Table {t_name}: {cols}")
    return "\n".join(lines)


def _format_column_list(raw_columns: object) -> str:
    """
    Turn raw column metadata into one short prompt-friendly line.

    Use this helper when building the schema section of the SQL drafting
    prompt.
    """
    if isinstance(raw_columns, int):
        return f"{raw_columns} columns"
    if not isinstance(raw_columns, list):
        return "columns unknown"

    columns: list[str] = []
    for column in raw_columns:
        if not isinstance(column, dict):
            continue
        name = column.get("name")
        dtype = column.get("dtype")
        if isinstance(name, str) and isinstance(dtype, str):
            columns.append(f"{name} ({dtype})")
        elif isinstance(name, str):
            columns.append(name)
    return ", ".join(columns) if columns else "columns unknown"


def _choose_database_from_request(
    *,
    user_text: str,
    database_context: dict[str, object],
    available_databases: list[str],
) -> str | None:
    """
    Infer one database directly from the user's wording when possible.

    Use this helper before asking the user to choose a database. It prefers one
    clear match on database names or table names and returns `None` when the
    request stays ambiguous.
    """
    if len(available_databases) == 1:
        return available_databases[0]

    normalized_request = _normalize_match_text(user_text)
    if not normalized_request:
        return None

    database_matches = [
        db_name
        for db_name in available_databases
        if _normalize_match_text(db_name) in normalized_request
    ]
    if len(database_matches) == 1:
        return database_matches[0]

    table_matches: list[str] = []
    for db_name in available_databases:
        table_names = tables_for_database(database_context, db_name)
        if any(
            _normalize_match_text(table_name) in normalized_request
            for table_name in table_names
        ):
            table_matches.append(db_name)
    if len(table_matches) == 1:
        return table_matches[0]
    return None


def _normalize_match_text(value: str) -> str:
    """
    Normalize a database or table name for simple request matching.

    Use this helper when comparing the user request with database and table
    names during scope inference.
    """
    return re.sub(r"[^a-z0-9_]+", " ", value.lower()).strip()
