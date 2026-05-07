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
Agent registry for the standalone Fred agents pod.

Why this module exists:
- `create_agent_app(...)` expects a `dict[str, ReActAgentDefinition]`
- keeping registry assembly here keeps HTTP bootstrap separate from agent code

How to use it:
- import `REGISTRY` from `fred_agents.main`
- add future agent definitions to this module as the pod grows

Example:
- `from fred_agents.agents import REGISTRY`
"""

from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition

from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.rag_expert import RAG_EXPERT_AGENT
from fred_agents.sentinel import SENTINEL_AGENT
from fred_agents.test_assistant.graph_agent import TEST_ASSISTANT_AGENT


def build_registry() -> dict[str, ReActAgentDefinition | GraphAgentDefinition]:
    """
    Build the pod agent registry.

    Agent lineup:
    - fred.github.assistant    General-purpose ReAct agent. Pure LLM baseline,
                               no MCP by default. Admins equip it with catalog
                               MCP servers via the control-plane agent form.
                               First entry → default agent in fred-agents-cli.
    - fred.github.sentinel     Monitoring ReAct agent. Requires OpenSearch MCP.
                               Expected to fail gracefully in standalone mode —
                               useful for validating error detection and handling.
    - fred.github.rag_expert   Document-grounded ReAct agent. Uses the Fred
                               built-in knowledge.search declared_tool_ref (not
                               MCP). Reference for ReAct/built-in-tool pattern.
    - fred.github.test_assistant  No-LLM graph agent. Exercises every SSE event
                               type without any external service. Used for UI
                               validation and integration scenario testing.
    """

    return {
        # First entry is the default agent selected by fred-agents-cli on connect.
        GENERAL_ASSISTANT_AGENT.agent_id: GENERAL_ASSISTANT_AGENT,
        SENTINEL_AGENT.agent_id: SENTINEL_AGENT,
        RAG_EXPERT_AGENT.agent_id: RAG_EXPERT_AGENT,
        TEST_ASSISTANT_AGENT.agent_id: TEST_ASSISTANT_AGENT,
    }


REGISTRY: dict[str, ReActAgentDefinition | GraphAgentDefinition] = build_registry()
