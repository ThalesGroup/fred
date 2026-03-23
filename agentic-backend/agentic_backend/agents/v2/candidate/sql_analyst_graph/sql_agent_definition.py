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
choose a database, draft SQL, and finalize.
"""

from __future__ import annotations

from agentic_backend.core.agents.v2 import (
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCPServerRef,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    GraphAgent,
    GraphWorkflow,
)

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


class SqlAgentDefinition(GraphAgent):
    """
    SQL agent workflow definition.

    Change this file when the business sequence changes. Keep the input/state
    in `sql_agent_state.py` and the step behavior in `sql_agent_steps.py`.
    """

    agent_id: str = "candidate.sql_agent.graph.v2"
    role: str = "SQL Agent"
    description: str = (
        "Workflow-shaped SQL agent that loads tabular context, resolves the "
        "database scope, drafts one SQL query, and returns it to the user."
    )
    tags: tuple[str, ...] = ("sql", "graph", "candidate", "agent", "v2")
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
    )

    input_schema = SqlAgentInput
    state_schema = SqlAgentState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

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
