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
Prompt loading for the SQL agent package.

This file keeps prompt loading in one place so the step files stay focused on
dataset selection, SQL drafting, and result handling.
"""

from agentic_backend.core.agents.v2.resources import load_agent_prompt_markdown

_SQL_ANALYST_GRAPH_PACKAGE = "agentic_backend.agents.v2.production.sql_analyst_graph"


def load_sql_analyst_graph_prompt(file_name: str) -> str:
    """
    Load a Markdown prompt file from this package's `prompts/` directory.

    Keep prompt text in Markdown and load it by file name from the SQL agent
    package. Add new prompt files under `prompts/` and load them here so the
    package keeps one convention.

    Example:
    ```python
    DRAFT_SQL_PROMPT = load_sql_analyst_graph_prompt(
        "sql_agent_draft_sql_system_prompt.md",
    )

    SUMMARIZE_PROMPT = load_sql_analyst_graph_prompt(
        "sql_agent_summarize_result_system_prompt.md",
    )
    ```
    """

    return load_agent_prompt_markdown(
        package=_SQL_ANALYST_GRAPH_PACKAGE,
        file_name=file_name,
    )
