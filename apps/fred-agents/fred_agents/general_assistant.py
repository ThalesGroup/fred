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
General-purpose assistant ReAct agent — configurable with any Knowledge Flow tool.

Why this module exists:
- all other agents in this pod are scoped to a specific task (monitoring, RAG)
- this agent is the generic configurable template: team admins equip it with the
  Knowledge Flow MCP tools their use case needs and guide it via a system prompt
- it is also the minimal smoke-test for a running pod (no external service required
  if mcp servers are not reachable — the agent falls back gracefully)

How to use it:
- import `GENERAL_ASSISTANT_AGENT` and add it to a pod registry
- chat with it using `fred-agents-cli`; add KF tools via the control-plane form

Example:
- `from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS,
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

_SYSTEM_PROMPT = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.
If tools are available, use them to ground your answers in real data before responding.
"""


class GeneralAssistantDefinition(ReActAgentDefinition):
    """
    Configurable general-purpose ReAct agent served by the standalone agents pod.

    Why this class exists:
    - it is the generic Fred agent: team admins configure it with any combination
      of Knowledge Flow MCP tools and a custom system prompt for their use case
    - it works with zero external services (the model alone is enough) and scales
      up to the full Knowledge Flow toolkit without code changes

    Key design choices:
    - all Knowledge Flow MCP servers are declared in `default_mcp_servers` so the
      control-plane enrolls them when a team creates an instance; team admins
      can review which tools are active from the agent form
    - `prompts.system` field lets team admins specialise the agent role (search
      assistant, monitoring assistant, data analyst …) without creating a new
      template
    - `chat_options.*` fields are frontend configuration hints — they are read by
      the chat UI to show or hide file attachments and library selection

    How to use it:
    - instantiate once and register it in the pod registry
    - team admins then create instances via the control-plane form

    Example:
    - `definition = GeneralAssistantDefinition()`
    """

    agent_id: str = "fred.github.assistant"
    role: str = "General-purpose assistant"
    description: str = (
        "A helpful, concise assistant configurable with any Knowledge Flow tool. "
        "Equip it with search, monitoring, or data tools and guide it via its system prompt."
    )
    tags: tuple[str, ...] = ("general", "react")
    system_prompt_template: str = _SYSTEM_PROMPT

    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_FS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_CORPUS),
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS),
    )

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


GENERAL_ASSISTANT_AGENT = GeneralAssistantDefinition()
