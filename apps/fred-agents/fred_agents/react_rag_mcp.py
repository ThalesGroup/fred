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
ReAct RAG MCP template — document-grounded agent via Knowledge Flow MCP search.

Why this module exists:
- complements rico (rag_expert) which uses the fred built-in knowledge.search
  tool ref; this template wires document retrieval through the MCP layer instead
- allows admins to configure library selection, search policy, and RAG scope
  directly from the Tools tab in the agent creation form
- serves as the canonical template when an operator wants a user-named,
  MCP-backed document search agent

Key design:
- declares MCP_SERVER_KNOWLEDGE_FLOW_TEXT in default_mcp_servers so the runtime
  and control-plane surface the server in the Tools tab with its config_fields
  (library picker, search policy, RAG scope)
- the agent name is set by the operator at enrollment time via the form's
  displayName field — no FieldSpec needed for that
- system prompt is the same grounding contract as rico: evidence-first,
  explicit uncertainty, language-aware

How to use it:
- import REACT_RAG_MCP_AGENT and add it to the pod registry
- operators create a named instance from the control-plane team agents page,
  pick a name, and configure the Tools tab

Example:
- `from fred_agents.react_rag_mcp import REACT_RAG_MCP_AGENT`
"""

from fred_sdk import (
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

_SYSTEM_PROMPT = """\
You are a document-grounded assistant. Your answers must be grounded in \
retrieved documents, not in your training knowledge.

## MANDATORY: search before answering

Before answering any factual question, call the search tool. Do NOT answer \
from memory when a corpus is available.

## Language and context

- Always respond in {response_language}.
- Today is {today}.
"""


class ReactRagMcpDefinition(ReActAgentDefinition):
    """
    Document-grounded ReAct agent template backed by Knowledge Flow MCP search.

    Why this class exists:
    - provides a user-nameable template for operators who want document search
      via the MCP layer rather than the fred built-in knowledge.search tool ref
    - the Tools tab exposes library selection, search policy, and RAG scope
      because the MCP server declares those config_fields in mcp_catalog.yaml
    - keeps grounding behaviour identical to rico: evidence-first, explicit
      uncertainty, language-aware

    Key design choices:
    - default_mcp_servers points to the text-search Knowledge Flow endpoint;
      the control-plane enriches the template summary with the server's
      config_fields so they appear in the Tools tab at enrollment time
    - one prompts.system FieldSpec lets operators specialise the instructions
      without forking the template

    How to use it:
    - instantiate once and register in the pod registry
    - operators create a named instance via the control-plane team agents page

    Example:
    - `definition = ReactRagMcpDefinition()`
    """

    agent_id: str = "fred.github.react_rag_mcp"
    role: str = "Document search assistant"
    description: str = (
        "A document-grounded ReAct assistant backed by Knowledge Flow MCP search. "
        "Configure library selection, search policy, and RAG scope from the Tools tab."
    )
    tags: tuple[str, ...] = ("rag", "documents", "react", "mcp")
    system_prompt_template: str = _SYSTEM_PROMPT
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id=MCP_SERVER_KNOWLEDGE_FLOW_TEXT),
    )

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            description=(
                "Override the default document-grounded instructions. "
                "Leave blank to use the built-in evidence-first RAG prompt."
            ),
            required=False,
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description=(
                "Persist the conversation-attachment capability so the chat composer "
                "can restore the toggle state after saving and reopening the agent."
            ),
            required=False,
            default=False,
            ui=UIHints(group="Chat", hide=True),
        ),
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template=self.system_prompt_template)


REACT_RAG_MCP_AGENT = ReactRagMcpDefinition()
