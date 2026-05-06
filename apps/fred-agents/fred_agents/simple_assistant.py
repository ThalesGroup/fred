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
LLM-only generalist assistant — no tools, no MCP servers.

Why this module exists:
- the general_assistant carries all KF MCP server defaults; this agent
  intentionally has none, making it both the minimal LLM smoke-test and a
  production-ready general chat assistant that works with a model alone
- use it to validate that the LLM path, streaming, and SSE pipeline are
  healthy before troubleshooting tool bindings

How to use it:
- import `SIMPLE_ASSISTANT_AGENT` and add it to a pod registry
- chat with it using `fred-agents-cli`; no external service is required

Example:
- `from fred_agents.simple_assistant import SIMPLE_ASSISTANT_AGENT`
"""

from fred_sdk import FieldSpec, UIHints
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

_SYSTEM_PROMPT = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.
"""


class SimpleAssistantDefinition(ReActAgentDefinition):
    """
    LLM-only general-purpose assistant with no tool or MCP bindings.

    Why this class exists:
    - provides a zero-external-dependency agent that serves two purposes:
      (1) smoke-test: verifies the LLM call, streaming, and SSE pipeline
          work before any tool or MCP configuration is involved;
      (2) production: a general chat assistant for users who need conversation
          without search or data tools.
    - keeping it tool-free means it degrades gracefully in any environment
      where MCP servers or KF services are not yet reachable.

    Key design choices:
    - no `default_mcp_servers` and no `declared_tool_refs` — pure LLM
    - one optional field: `prompts.system`, so team admins can specialise the
      role without creating a new agent template

    How to use it:
    - instantiate once and register it first in the pod registry so that
      `fred-agents-cli` selects it as the default agent on connect
    - team admins create instances via the control-plane agent form

    Example:
    - `definition = SimpleAssistantDefinition()`
    """

    agent_id: str = "fred.github.simple_assistant"
    role: str = "Generalist assistant"
    description: str = (
        "A helpful, concise assistant that answers directly from the model. "
        "No tools or external services required."
    )
    tags: tuple[str, ...] = ("general", "llm-only")
    system_prompt_template: str = _SYSTEM_PROMPT

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Instructions that define the assistant's role and focus. "
                "Leave blank to use the default general-purpose prompt."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


SIMPLE_ASSISTANT_AGENT = SimpleAssistantDefinition()
