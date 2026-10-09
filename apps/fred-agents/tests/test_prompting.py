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

from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.platform_ops import PLATFORM_OPS_AGENT
from fred_agents.rag_expert import RAG_EXPERT_AGENT
from fred_agents.react_rag_mcp import REACT_RAG_MCP_AGENT
from fred_agents.sentinel import SENTINEL_AGENT
from fred_agents.sql_expert import SQL_EXPERT_AGENT

_EXPECTED_FRAGMENT = "When you include Mermaid diagrams, follow these rules strictly so the diagram always parses:"
_EXPECTED_FALLBACK_RULE = (
    "If you are unsure the diagram will parse, return a Markdown list or "
    "table instead of Mermaid."
)


def test_base_agents_do_not_bake_global_base_prompt_contract() -> None:
    """Platform Mermaid instructions are loaded as a skill, not baked into templates."""

    prompts = (
        GENERAL_ASSISTANT_AGENT.system_prompt_template,
        RAG_EXPERT_AGENT.system_prompt_template,
        REACT_RAG_MCP_AGENT.system_prompt_template,
        SENTINEL_AGENT.system_prompt_template,
        SQL_EXPERT_AGENT.system_prompt_template,
        PLATFORM_OPS_AGENT.system_prompt_template,
    )

    for prompt in prompts:
        assert _EXPECTED_FRAGMENT not in prompt
        assert _EXPECTED_FALLBACK_RULE not in prompt


def test_general_assistant_prompt_field_default_excludes_global_base_prompt() -> None:
    """The editor default mirrors the raw template without platform skill bodies."""

    prompt_field = next(
        field
        for field in GENERAL_ASSISTANT_AGENT.fields
        if field.key == "prompts.system"
    )

    assert prompt_field.default == GENERAL_ASSISTANT_AGENT.system_prompt_template
    assert _EXPECTED_FRAGMENT not in str(prompt_field.default)
    assert _EXPECTED_FALLBACK_RULE not in str(prompt_field.default)
