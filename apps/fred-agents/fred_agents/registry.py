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

from fred_sdk.contracts.models import ReActAgentDefinition

from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT
from fred_agents.rag_expert import RAG_EXPERT_AGENT
from fred_agents.sentinel import SENTINEL_AGENT


def build_registry() -> dict[str, ReActAgentDefinition]:
    """
    Build the pod agent registry.

    Why this function exists:
    - the pod should expose one clear place where agent definitions are
      assembled
    - tests can call the same builder without importing FastAPI startup code

    How to use it:
    - call once at module import for the default registry
    - extend the returned mapping with additional definitions later

    Example:
    - `registry = build_registry()`
    """

    return {
        # First entry is the default agent selected by fred-agent-chat on connect.
        # general_assistant has no external dependencies — works with a model only.
        GENERAL_ASSISTANT_AGENT.agent_id: GENERAL_ASSISTANT_AGENT,
        SENTINEL_AGENT.agent_id: SENTINEL_AGENT,
        RAG_EXPERT_AGENT.agent_id: RAG_EXPERT_AGENT,
    }


REGISTRY: dict[str, ReActAgentDefinition] = build_registry()
