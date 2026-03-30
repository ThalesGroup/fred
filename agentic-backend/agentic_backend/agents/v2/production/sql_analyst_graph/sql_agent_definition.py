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
Author-facing graph definition for the SQL agent.

This file declares the business journey of the agent: load tabular context,
choose a database, draft SQL, execute, synthesize the answer, and finalize.

Tunable fields:
- draft_sql_system_prompt: the instructions given to the model when generating
  SQL. Editable in the agent settings UI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2 import (
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCPServerRef,
)
from agentic_backend.core.agents.v2.contracts.context import BoundRuntimeContext
from agentic_backend.core.agents.v2.graph.authoring import (
    GraphAgent,
    GraphWorkflow,
)

from .prompt_loader import load_sql_analyst_graph_prompt
from .sql_agent_state import (
    SqlAgentInput,
    SqlAgentState,
)
from .sql_agent_steps import (
    analyze_intent_step,
    choose_database_step,
    draft_sql_step,
    execute_sql_step,
    finalize_sql_agent_step,
    load_context_step,
    synthesize_answer_step,
)

_DEFAULT_DRAFT_SQL_SYSTEM_PROMPT = load_sql_analyst_graph_prompt(
    "sql_agent_draft_sql_system_prompt.md"
)


class SqlAgentDefinition(GraphAgent):
    """
    SQL agent workflow definition.

    Change this file when the business sequence changes. Keep the input/state
    in sql_agent_state.py and the step behaviour in sql_agent_steps.py.

    The draft_sql_system_prompt field is tunable via the agent settings UI:
    operators can adjust the SQL drafting instructions without touching code.
    """

    agent_id: str = "production.sql_analyst.graph.v2"
    role: str = "SQL Agent"
    description: str = (
        "Workflow-shaped SQL agent that loads tabular context, resolves the "
        "database scope, drafts and executes one SQL query, and returns a "
        "synthesised answer to the user."
    )
    tags: tuple[str, ...] = ("sql", "graph", "production", "agent", "v2")
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
    )

    # ── Tunable field ────────────────────────────────────────────────────────
    draft_sql_system_prompt: str = Field(default=_DEFAULT_DRAFT_SQL_SYSTEM_PROMPT)

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="draft_sql_system_prompt",
            type="prompt",
            title="SQL Drafting Prompt",
            description=(
                "Instructions given to the model when generating SQL queries. "
                "The available table schema is appended automatically."
            ),
            required=True,
            default=_DEFAULT_DRAFT_SQL_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    )

    # ── State contract ───────────────────────────────────────────────────────
    input_schema = SqlAgentInput
    state_schema = SqlAgentState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> SqlAgentState:
        """Inject tunable fields into the workflow state at run start."""
        base = super().build_initial_state(input_model, binding)
        return SqlAgentState.model_validate(
            base.model_dump()
            | {"draft_sql_system_prompt": self.draft_sql_system_prompt}
        )

    # ── Workflow ─────────────────────────────────────────────────────────────
    workflow = GraphWorkflow(
        entry="load_context",
        nodes={
            "load_context": load_context_step,
            "analyze_intent": analyze_intent_step,
            "choose_database": choose_database_step,
            "draft_sql": draft_sql_step,
            "execute_sql": execute_sql_step,
            "synthesize": synthesize_answer_step,
            "finalize": finalize_sql_agent_step,
        },
        edges={
            "load_context": "analyze_intent",
            "draft_sql": "execute_sql",
            "execute_sql": "synthesize",
            "synthesize": "finalize",
        },
        routes={
            "analyze_intent": {
                "query": "choose_database",
                "info": "finalize",
            },
            "choose_database": {
                "selected": "draft_sql",
                "finish": "finalize",
            },
        },
    )
