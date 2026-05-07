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
General-purpose assistant ReAct agent — the default Fred agent.

Why this module exists:
- provides the single general-purpose agent that covers the full range of use
  cases: pure LLM conversation when no tools are active, document search when
  Knowledge Flow MCP servers are equipped, and anything in between
- replaces the former split between `simple_assistant` (no MCP) and the old
  `general_assistant` (all KF MCP servers by default), which was confusing

Key design:
- no `default_mcp_servers`: starts as a pure-LLM agent that works standalone
  without any external service
- admins equip it with catalog MCP servers via the control-plane agent form;
  the system prompt handles both the tool-equipped and no-tool cases
- one `prompts.system` field lets admins specialise the role without creating a
  new agent template

How to use it:
- import `GENERAL_ASSISTANT_AGENT` and register it first in the pod registry
  so that `fred-agents-cli` selects it as the default agent on connect
- equip with Knowledge Flow MCP servers via the control-plane form to enable
  search, tabular, or monitoring capabilities

Example:
- `from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT`
"""

from fred_sdk import FieldSpec, UIHints
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

_SYSTEM_PROMPT = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.

If search or data tools are available, use them to ground your answers in real \
data before responding.
If no tools are available, answer from your training knowledge and say so clearly \
— do not pretend to have access to a document corpus or live data you cannot reach.
"""


class GeneralAssistantDefinition(ReActAgentDefinition):
    """
    General-purpose ReAct agent — the default Fred open-source agent.

    Why this class exists:
    - single entry point for general conversation, document search, and data
      analysis depending on which MCP servers the admin activates
    - works standalone with zero external dependencies (pure LLM baseline)
    - scales up to the full Knowledge Flow toolkit without any code change

    Key design choices:
    - no `default_mcp_servers`: admins choose which catalog servers to activate
      from the control-plane agent form; this makes the standalone baseline
      unambiguous and prevents silent failures when MCP services are unreachable
    - system prompt explicitly handles both the tool-equipped and no-tool cases
      so the agent never claims capabilities it does not have
    - one `prompts.system` field lets admins specialise the role without a new
      template

    How to use it:
    - instantiate once and register it first in the pod registry (CLI default)
    - team admins create instances and pick MCP tools via the control-plane form

    Example:
    - `definition = GeneralAssistantDefinition()`
    """

    agent_id: str = "fred.github.assistant"
    role: str = "General-purpose assistant"
    description: str = (
        "A helpful, concise assistant. Works standalone from model knowledge. "
        "Equip it with Knowledge Flow search or data tools via the agent form "
        "to ground answers in your documents and live data."
    )
    tags: tuple[str, ...] = ("general", "react")
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


GENERAL_ASSISTANT_AGENT = GeneralAssistantDefinition()
