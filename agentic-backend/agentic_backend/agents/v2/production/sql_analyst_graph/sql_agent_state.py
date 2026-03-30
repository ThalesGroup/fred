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
Input and state for the SQL agent.

This file shows what starts a SQL run and what the workflow remembers while it
loads available databases, selects one scope, and drafts a query.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SqlAgentInput(BaseModel):
    """
    User request that starts one SQL analysis run.

    Example:
    ```python
    request = SqlAgentInput(
        message="Which customers placed the largest orders last month?",
    )
    ```
    """

    message: str = Field(..., min_length=1)


class SqlAgentState(BaseModel):
    """
    Business state carried through the SQL workflow.

    Use this model to see what the agent already knows after each step: the
    user question, discovered databases, selected database, selected tables,
    drafted SQL, and final message.

    Example:
    ```python
    state = SqlAgentState(
        latest_user_text="Show sample rows from sales",
        selected_db="analytics",
        draft_sql='SELECT * FROM "sales" LIMIT 20',
    )
    ```
    """

    latest_user_text: str
    database_context: dict[str, object] = Field(default_factory=dict)
    available_databases: list[str] = Field(default_factory=list)
    selected_db: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    draft_sql: str | None = None

    # Execution results
    query_results: list[dict[str, object]] | None = None
    execution_error: str | None = None

    # Injected at workflow start from the tunable definition field
    draft_sql_system_prompt: str = ""

    final_text: str | None = None
    done_reason: str | None = None
