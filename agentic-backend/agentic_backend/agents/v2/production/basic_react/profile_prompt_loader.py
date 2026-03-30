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
Helpers for loading text resources (like prompts) from the agent package.

Why this exists:
    It lets you keep your large system prompts in clean Markdown files
    instead of messy Python strings.
"""

from agentic_backend.core.agents.v2.resources import load_agent_prompt_markdown

_BASIC_REACT_PROFILE_PACKAGE = "agentic_backend.agents.v2.production.basic_react"


def load_basic_react_prompt(file_name: str) -> str:
    """
    Load a system prompt from the basic_react/prompts/ folder.

    Put your .md file in:
        agentic_backend/agents/v2/production/basic_react/prompts/<file_name>

    Example:
        system_prompt_template=load_basic_react_prompt("basic_react_it_support_system_prompt.md")
    """
    return load_agent_prompt_markdown(
        package=_BASIC_REACT_PROFILE_PACKAGE,
        file_name=file_name,
    )
