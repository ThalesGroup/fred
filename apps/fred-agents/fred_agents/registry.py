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
"""The three agent templates shipped by the Weaver pod."""

from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition

from fred_agents.deep_assistant import DEEP_ASSISTANT_AGENT
from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.test_assistant.graph_agent import TEST_ASSISTANT_AGENT


def build_registry() -> dict[str, ReActAgentDefinition | GraphAgentDefinition]:
    """Expose the configurable ReAct and Deep assistants and the UI test agent."""
    return {
        # First entry is the default agent selected by fred-agents-cli on connect.
        GENERAL_ASSISTANT_AGENT.agent_id: GENERAL_ASSISTANT_AGENT,
        DEEP_ASSISTANT_AGENT.agent_id: DEEP_ASSISTANT_AGENT,
        TEST_ASSISTANT_AGENT.agent_id: TEST_ASSISTANT_AGENT,
    }


REGISTRY: dict[str, ReActAgentDefinition | GraphAgentDefinition] = build_registry()
