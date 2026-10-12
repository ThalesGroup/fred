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
"""Document-grounded ReAct template using the native document_access capability."""

from fred_sdk import (
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ReActPolicy

from fred_agents.tool_pacing import REASONING_SAFE_TOOL_SELECTION

_BASE_SYSTEM_PROMPT = """\
You are a document-grounded assistant. Your answers must be grounded in \
retrieved documents, not in your training knowledge.

## MANDATORY: search before answering

Before answering any factual question, call the search tool. Do NOT answer \
from memory when a corpus is available.

## Language and context

- Always respond in {response_language}.
- Today is {today}.
"""

_SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT


class ReactRagMcpDefinition(ReActAgentDefinition):
    """Keep the existing template identity while using native document search."""

    agent_id: str = "fred.github.react_rag_mcp"
    role: str = "Document search assistant"
    description: str = (
        "A document-grounded ReAct assistant backed by native document search. "
        "Configure library selection, search policy, and RAG scope from the Tools tab."
    )
    tags: tuple[str, ...] = ("rag", "documents", "react")
    system_prompt_template: str = _SYSTEM_PROMPT
    default_mcp_servers: tuple[MCPServerRef, ...] = (
        MCPServerRef(id="document_access"),
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
    )

    def policy(self) -> ReActPolicy:
        return ReActPolicy(
            system_prompt_template=self.system_prompt_template,
            # REASON-01 §9 precondition 1 — see fred_agents.tool_pacing.
            tool_selection=REASONING_SAFE_TOOL_SELECTION,
        )


REACT_RAG_MCP_AGENT = ReactRagMcpDefinition()
