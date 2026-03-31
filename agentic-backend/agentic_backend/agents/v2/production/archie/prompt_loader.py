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

"""Prompt loading helpers for the Archie v2 RAG agent."""

from agentic_backend.core.agents.v2.resources import load_agent_prompt_markdown

_ARCHIE_PACKAGE = "agentic_backend.agents.v2.production.archie"


def load_archie_prompt(file_name: str) -> str:
    """
    Load one packaged markdown prompt from this agent package.

    Why this exists:
    - keeps prompt text in versioned markdown files instead of inline Python strings
    - keeps step files focused on business logic

    How to use:
    - place prompt files under `prompts/`
    - call this helper with the file name

    Example:
    ```python
    SYSTEM_PROMPT = load_archie_prompt("archie_system_prompt.md")
    ```
    """
    return load_agent_prompt_markdown(
        package=_ARCHIE_PACKAGE,
        file_name=file_name,
    )
