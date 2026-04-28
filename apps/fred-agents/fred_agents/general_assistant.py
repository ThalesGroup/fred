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
General-purpose assistant ReAct agent — zero external dependencies.

Why this module exists:
- all other agents in this pod require external services (MCP, knowledge flow)
- this agent works with only a model configured; it is the minimal smoke-test
  for a running pod and the reference example for the BOOTSTRAP guide

How to use it:
- import `GENERAL_ASSISTANT_AGENT` and add it to a pod registry
- chat with it using `fred-agents-cli` without starting any other service

Example:
- `from fred_agents.general_assistant import GENERAL_ASSISTANT_AGENT`
"""

from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy


class GeneralAssistantDefinition(ReActAgentDefinition):
    """
    Conversational ReAct agent with no tool dependencies.

    Why this class exists:
    - it is the simplest possible Fred agent: a system prompt and nothing else
    - it lets developers verify the pod, the model catalog, and the chat client
      work end-to-end without standing up any supporting service

    How to use it:
    - instantiate once and register it in the pod registry
    - extend with `declared_tool_refs` or `default_mcp_servers` when ready

    Example:
    - `definition = GeneralAssistantDefinition()`
    """

    agent_id: str = "fred.github.assistant"
    role: str = "General-purpose assistant"
    description: str = (
        "A helpful, concise assistant for general questions and conversation. "
        "No external tools or document retrieval required."
    )
    tags: tuple[str, ...] = ("general", "react")
    system_prompt_template: str = """\
You are a helpful, knowledgeable, and concise assistant.
Answer questions clearly and directly. When you are uncertain, say so.
You have no access to external tools or documents — work only from your own knowledge.
"""

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


GENERAL_ASSISTANT_AGENT = GeneralAssistantDefinition()
